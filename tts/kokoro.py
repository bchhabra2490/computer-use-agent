"""Kokoro local TTS.

Backends:
  1. ``mlx-audio`` on Apple Silicon (``KOKORO_MODEL``, default Kokoro-82M-bf16)
  2. ``kokoro-onnx`` if ``KOKORO_ONNX_MODEL`` (+ optional voices file) is set
"""

from __future__ import annotations

import io
import os
import threading
import wave
from pathlib import Path

KOKORO_VOICE = (
    os.environ.get("KOKORO_VOICE") or os.environ.get("TTS_VOICE") or "bm_george"
).strip() or "bm_george"
KOKORO_MODEL = (
    os.environ.get("KOKORO_MODEL") or "mlx-community/Kokoro-82M-bf16"
).strip() or "mlx-community/Kokoro-82M-bf16"
KOKORO_SPEED = float(os.environ.get("KOKORO_SPEED", "1.0"))
KOKORO_LANG = (os.environ.get("KOKORO_LANG") or "").strip()
KOKORO_ONNX_MODEL = (os.environ.get("KOKORO_ONNX_MODEL") or "").strip()
KOKORO_ONNX_VOICES = (os.environ.get("KOKORO_ONNX_VOICES") or "").strip()
KOKORO_SAMPLE_RATE = int(os.environ.get("KOKORO_SAMPLE_RATE", "24000"))

_lock = threading.Lock()
_mlx_model = None
_onnx_engine = None
_logged = False


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm)
    return buf.getvalue()


def _float_to_wav(audio, sample_rate: int) -> bytes:
    import numpy as np

    arr = np.asarray(audio, dtype=np.float32).reshape(-1)
    arr = np.clip(arr, -1.0, 1.0)
    pcm = (arr * 32767.0).astype("<i2").tobytes()
    return _pcm_to_wav(pcm, sample_rate)


def _lang_code(voice: str) -> str:
    if KOKORO_LANG:
        return KOKORO_LANG
    prefix = (voice or "").strip().lower()[:3]
    return {
        "bf_": "b",
        "bm_": "b",
        "jf_": "j",
        "jm_": "j",
        "zf_": "z",
        "zm_": "z",
        "hf_": "h",
        "hm_": "h",
        "ff_": "f",
        "if_": "i",
        "ef_": "e",
        "pf_": "p",
    }.get(prefix, "a")


def _mlx_available() -> bool:
    try:
        import mlx_audio.tts.utils  # noqa: F401

        return True
    except ImportError:
        return False


def _ensure_misaki_en() -> None:
    """mlx-audio hides the real G2P ImportError behind 'pip install misaki'."""
    try:
        import misaki.en  # noqa: F401
    except ImportError as e:
        missing = getattr(e, "name", None) or str(e)
        raise RuntimeError(
            "Kokoro English G2P needs misaki plus num2words and spaCy 3.8 "
            f"(failed to import {missing!r}). On Python 3.14 run: "
            "pip install num2words 'spacy==3.8.16' phonemizer"
        ) from e


def _load_mlx():
    global _mlx_model, _logged
    if _mlx_model is not None:
        return _mlx_model
    _ensure_misaki_en()
    try:
        from mlx_audio.tts.utils import load_model
    except ImportError as e:
        raise RuntimeError(
            "Kokoro MLX backend needs mlx-audio. Run: pip install mlx-audio"
        ) from e
    _mlx_model = load_model(KOKORO_MODEL)
    if not _logged:
        print(f"[tts] provider=kokoro backend=mlx model={KOKORO_MODEL}", flush=True)
        _logged = True
    return _mlx_model


def _load_onnx():
    global _onnx_engine, _logged
    if _onnx_engine is not None:
        return _onnx_engine
    model = Path(KOKORO_ONNX_MODEL).expanduser()
    if not model.is_file():
        raise RuntimeError(f"KOKORO_ONNX_MODEL is not a file: {model}")
    try:
        from kokoro_onnx import Kokoro
    except ImportError as e:
        raise RuntimeError(
            "kokoro-onnx is not installed. Run: pip install kokoro-onnx"
        ) from e
    voices = Path(KOKORO_ONNX_VOICES).expanduser() if KOKORO_ONNX_VOICES else None
    if voices is not None and voices.is_file():
        _onnx_engine = Kokoro(str(model), str(voices))
    else:
        _onnx_engine = Kokoro(str(model))
    if not _logged:
        print(f"[tts] provider=kokoro backend=onnx model={model.name}", flush=True)
        _logged = True
    return _onnx_engine


def _audio_from_result(result) -> object:
    audio = getattr(result, "audio", None)
    if audio is not None:
        return audio
    if isinstance(result, (tuple, list)) and result:
        last = result[-1]
        return getattr(last, "audio", last)
    return result


def _synthesize_mlx(text: str, voice: str) -> bytes:
    model = _load_mlx()
    pieces = []
    rate = KOKORO_SAMPLE_RATE
    kwargs = {
        "text": text,
        "voice": voice,
        "speed": KOKORO_SPEED,
        "lang_code": _lang_code(voice),
    }
    for result in model.generate(**kwargs):
        audio = _audio_from_result(result)
        rate = int(getattr(result, "sample_rate", rate) or rate)
        pieces.append(audio)
    if not pieces:
        raise RuntimeError("Kokoro MLX returned no audio.")
    import numpy as np

    arrays = [np.asarray(p, dtype=np.float32).reshape(-1) for p in pieces]
    return _float_to_wav(np.concatenate(arrays), rate)


def _synthesize_onnx(text: str, voice: str) -> bytes:
    engine = _load_onnx()
    samples, rate = engine.create(
        text,
        voice=voice,
        speed=KOKORO_SPEED,
        lang=_lang_code(voice),
    )
    return _float_to_wav(samples, int(rate or KOKORO_SAMPLE_RATE))


def synthesize_wav(text: str, *, voice: str | None = None) -> bytes:
    """Synthesize ``text`` with Kokoro and return WAV bytes."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Nothing to speak.")
    used = (voice or KOKORO_VOICE).strip() or KOKORO_VOICE
    with _lock:
        if KOKORO_ONNX_MODEL:
            return _synthesize_onnx(text, used)
        if _mlx_available():
            return _synthesize_mlx(text, used)
        raise RuntimeError(
            "Kokoro TTS needs mlx-audio (Apple Silicon: pip install mlx-audio) "
            "or KOKORO_ONNX_MODEL pointing at a kokoro-onnx .onnx file."
        )
