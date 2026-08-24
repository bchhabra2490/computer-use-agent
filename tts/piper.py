"""Piper local TTS (ONNX, CPU). ``synthesize_wav`` → WAV bytes."""

from __future__ import annotations

import io
import os
import threading
import urllib.request
import wave
from pathlib import Path

PIPER_VOICE = (
    os.environ.get("PIPER_VOICE") or os.environ.get("TTS_VOICE") or "en_GB-alan-medium"
).strip() or "en_GB-alan-medium"
PIPER_MODEL = (os.environ.get("PIPER_MODEL") or "").strip()
PIPER_DIR = Path(
    os.environ.get("PIPER_DIR") or (Path(__file__).resolve().parent.parent / "models" / "piper")
)
PIPER_LENGTH_SCALE = float(os.environ.get("PIPER_LENGTH_SCALE", "1.0"))
_HF_VOICES = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
_QUALITIES = ("x_low", "low", "medium", "high")

_lock = threading.Lock()
_voices: dict[str, object] = {}


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm)
    return buf.getvalue()


def _voice_hf_path(voice: str) -> str:
    """en_US-lessac-medium → en/en_US/lessac/medium/en_US-lessac-medium.onnx"""
    name = voice.strip()
    if name.endswith(".onnx"):
        name = name[: -len(".onnx")]
    quality = "medium"
    stem = name
    for q in _QUALITIES:
        suffix = f"-{q}"
        if name.endswith(suffix):
            quality = q
            stem = name[: -len(suffix)]
            break
    if "_" not in stem[:5]:
        raise ValueError(
            f"Piper voice {voice!r} should look like en_US-lessac-medium "
            "(or set PIPER_MODEL to a .onnx path)."
        )
    lang_region, speaker = stem.split("-", 1)
    lang = lang_region.split("_", 1)[0]
    return f"{lang}/{lang_region}/{speaker}/{quality}/{name}.onnx"


def _onnx_path(voice: str) -> Path:
    if PIPER_MODEL:
        return Path(PIPER_MODEL).expanduser()
    raw = Path(voice).expanduser()
    if raw.suffix == ".onnx" and raw.is_file():
        return raw
    name = voice if voice.endswith(".onnx") else f"{voice}.onnx"
    return PIPER_DIR / Path(name).name


def _ensure_voice_files(voice: str) -> Path:
    path = _onnx_path(voice)
    cfg = Path(str(path) + ".json")
    if path.is_file() and cfg.is_file():
        return path
    rel = _voice_hf_path(voice)
    path.parent.mkdir(parents=True, exist_ok=True)
    onnx_url = f"{_HF_VOICES}/{rel}"
    json_url = f"{onnx_url}.json"
    if not path.is_file():
        print(f"[tts] downloading piper voice {path.name}…", flush=True)
        urllib.request.urlretrieve(onnx_url, path)
    if not cfg.is_file():
        urllib.request.urlretrieve(json_url, cfg)
    return path


def _load_piper():
    try:
        from piper import PiperVoice  # type: ignore

        return PiperVoice
    except ImportError:
        try:
            from piper.voice import PiperVoice  # type: ignore

            return PiperVoice
        except ImportError as e:
            raise RuntimeError(
                "Piper TTS is not installed. Run: pip install piper-tts"
            ) from e


def _load(voice: str):
    key = (PIPER_MODEL or voice).strip() or PIPER_VOICE
    with _lock:
        cached = _voices.get(key)
        if cached is not None:
            return cached
        PiperVoice = _load_piper()
        path = _ensure_voice_files(key)
        loaded = PiperVoice.load(str(path))
        _voices[key] = loaded
        print(f"[tts] provider=piper voice={path.stem}", flush=True)
        return loaded


def _syn_config():
    if abs(PIPER_LENGTH_SCALE - 1.0) < 1e-6:
        return None
    try:
        from piper.config import SynthesisConfig  # type: ignore
    except ImportError:
        try:
            from piper import SynthesisConfig  # type: ignore
        except ImportError:
            return None
    return SynthesisConfig(length_scale=PIPER_LENGTH_SCALE)


def synthesize_wav(text: str, *, voice: str | None = None) -> bytes:
    """Synthesize ``text`` with Piper and return WAV bytes."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Nothing to speak.")
    engine = _load((voice or PIPER_VOICE).strip() or PIPER_VOICE)
    cfg = _syn_config()
    if hasattr(engine, "synthesize_wav"):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            if cfg is not None:
                engine.synthesize_wav(text, wf, syn_config=cfg)
            else:
                engine.synthesize_wav(text, wf)
        return buf.getvalue()
    if hasattr(engine, "synthesize"):
        pcm = bytearray()
        rate = 22050
        kwargs = {}
        if cfg is not None:
            kwargs["syn_config"] = cfg
        stream = engine.synthesize(text, **kwargs)
        if hasattr(stream, "__iter__") and not isinstance(stream, (bytes, str)):
            for chunk in stream:
                rate = int(getattr(chunk, "sample_rate", rate) or rate)
                raw = getattr(chunk, "audio_int16_bytes", None)
                if raw:
                    pcm.extend(raw)
            if pcm:
                return _pcm_to_wav(bytes(pcm), rate)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            engine.synthesize(text, wf)
        return buf.getvalue()
    raise RuntimeError("Piper voice has no synthesize / synthesize_wav method.")
