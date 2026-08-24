"""Local WhisperFlow speech-to-text (on-device Whisper).

Record-then-transcribe, same shape as Sarvam. Backends, in order:

  1. ``WHISPERFLOW_URL`` — OpenAI-compatible local HTTP
     (``POST /v1/audio/transcriptions``).
  2. ``mlx-whisper`` — Apple Silicon, only if the HF snapshot is complete.
  3. ``whisper`` (openai-whisper) — local ``~/.cache/whisper/*.pt``.
  4. ``faster-whisper`` — CPU / CUDA fallback.

A half-downloaded MLX model must not be selected: that retries Hugging Face
and surfaces as ``Connection error.``.
"""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path
from typing import Any

from .timing import timed

WHISPERFLOW_URL = (os.environ.get("WHISPERFLOW_URL") or "").strip().rstrip("/")
WHISPERFLOW_API_KEY = (os.environ.get("WHISPERFLOW_API_KEY") or "local").strip() or "local"
WHISPERFLOW_MODEL = (
    os.environ.get("WHISPERFLOW_MODEL")
    or os.environ.get("STT_WHISPER_MODEL")
    or "mlx-community/whisper-large-v3-turbo"
).strip()
WHISPERFLOW_LANGUAGE = (os.environ.get("WHISPERFLOW_LANGUAGE") or "en").strip()
WHISPERFLOW_BACKEND = (os.environ.get("WHISPERFLOW_BACKEND") or "auto").strip().lower()
WHISPERFLOW_FASTER_MODEL = (os.environ.get("WHISPERFLOW_FASTER_MODEL") or "small.en").strip() or "small.en"
WHISPERFLOW_WHISPER_MODEL = (os.environ.get("WHISPERFLOW_WHISPER_MODEL") or "small.en").strip() or "small.en"

_OPENAI_WHISPER_NAMES = frozenset(
    {
        "tiny.en",
        "tiny",
        "base.en",
        "base",
        "small.en",
        "small",
        "medium.en",
        "medium",
        "large-v1",
        "large-v2",
        "large-v3",
        "large",
        "large-v3-turbo",
        "turbo",
    }
)

_faster_model: tuple[str, Any] | None = None
_whisper_model: tuple[str, Any] | None = None


def _language() -> str | None:
    lang = WHISPERFLOW_LANGUAGE.lower()
    if lang in {"", "auto", "unknown"}:
        return None
    return WHISPERFLOW_LANGUAGE


def _openai_base_url(url: str) -> str:
    if url.endswith("/v1"):
        return url
    return url + "/v1"


def _model_looks_mlx(model: str) -> bool:
    return "mlx-community/" in model or model.startswith("mlx-")


def _hf_hub_dir(repo: str) -> Path:
    return Path.home() / ".cache/huggingface/hub" / ("models--" + repo.replace("/", "--"))


def mlx_model_ready(repo: str) -> bool:
    """True when the Hugging Face snapshot has real weights (no incomplete blobs)."""
    root = _hf_hub_dir(repo)
    blobs = root / "blobs"
    snapshots = root / "snapshots"
    if not blobs.is_dir() or not snapshots.is_dir():
        return False
    sizes: list[int] = []
    for path in blobs.iterdir():
        if not path.is_file():
            continue
        if path.name.endswith(".incomplete"):
            return False
        try:
            sizes.append(path.stat().st_size)
        except OSError:
            return False
    # Config/tokenizer blobs are tiny; weights are hundreds of MB.
    return bool(sizes) and max(sizes) > 10_000_000


def whisper_model_name(model: str) -> str:
    """Map an MLX repo id to a local openai-whisper checkpoint name."""
    raw = (model or "").strip()
    if raw in _OPENAI_WHISPER_NAMES:
        return raw
    return WHISPERFLOW_WHISPER_MODEL


def _transcribe_http(wav_bytes: bytes, *, model: str) -> str:
    from openai import OpenAI

    with timed("transcribe_http", model=model, bytes=len(wav_bytes)):
        bio = io.BytesIO(wav_bytes)
        bio.name = "audio.wav"
        client = OpenAI(base_url=_openai_base_url(WHISPERFLOW_URL), api_key=WHISPERFLOW_API_KEY)
        kwargs: dict[str, Any] = {"model": model, "file": bio}
        lang = _language()
        if lang:
            kwargs["language"] = lang
        result = client.audio.transcriptions.create(**kwargs)
    return (getattr(result, "text", None) or str(result) or "").strip()


def _write_temp_wav(wav_bytes: bytes) -> str:
    with timed("write_temp_wav", bytes=len(wav_bytes)):
        fd, path = tempfile.mkstemp(suffix=".wav")
        try:
            os.write(fd, wav_bytes)
        finally:
            os.close(fd)
        return path


def _transcribe_mlx(wav_bytes: bytes, *, model: str) -> str:
    import mlx_whisper

    lang = _language()
    path = _write_temp_wav(wav_bytes)
    try:
        kwargs: dict[str, Any] = {
            "path_or_hf_repo": model,
            "verbose": False,
        }
        if lang:
            kwargs["language"] = lang
        with timed("transcribe_mlx", model=model, bytes=len(wav_bytes)):
            result = mlx_whisper.transcribe(path, **kwargs)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    if isinstance(result, dict):
        return str(result.get("text") or "").strip()
    return str(getattr(result, "text", None) or result or "").strip()


def _transcribe_whisper(wav_bytes: bytes, *, model: str) -> str:
    global _whisper_model
    import whisper

    name = whisper_model_name(model)
    cold = _whisper_model is None or _whisper_model[0] != name
    if cold:
        with timed("load_model", backend="whisper", model=name, cold=1):
            _whisper_model = (name, whisper.load_model(name))
    engine = _whisper_model[1]
    path = _write_temp_wav(wav_bytes)
    try:
        kwargs: dict[str, Any] = {}
        lang = _language()
        if lang:
            kwargs["language"] = lang
        with timed("transcribe_whisper", model=name, bytes=len(wav_bytes), cold=int(cold)):
            result = engine.transcribe(path, **kwargs)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    if isinstance(result, dict):
        return str(result.get("text") or "").strip()
    return str(result or "").strip()


def _transcribe_faster(wav_bytes: bytes, *, model: str) -> str:
    global _faster_model
    from faster_whisper import WhisperModel

    name = model
    if _model_looks_mlx(name) or name not in _OPENAI_WHISPER_NAMES:
        name = WHISPERFLOW_FASTER_MODEL
    cold = _faster_model is None or _faster_model[0] != name
    if cold:
        with timed("load_model", backend="faster-whisper", model=name, cold=1):
            _faster_model = (name, WhisperModel(name))
    engine = _faster_model[1]
    path = _write_temp_wav(wav_bytes)
    try:
        kwargs: dict[str, Any] = {}
        lang = _language()
        if lang:
            kwargs["language"] = lang
        with timed("transcribe_faster", model=name, bytes=len(wav_bytes), cold=int(cold)):
            segments, _info = engine.transcribe(path, **kwargs)
            text = "".join(seg.text for seg in segments)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    return text.strip()


def _mlx_importable() -> bool:
    try:
        import mlx_whisper  # noqa: F401

        return True
    except ImportError:
        return False


def _whisper_importable() -> bool:
    try:
        import whisper  # noqa: F401

        return True
    except ImportError:
        return False


def _faster_importable() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


def resolve_backend() -> str:
    """Which engine ``transcribe_wav`` will use."""
    with timed("resolve_backend"):
        return _resolve_backend()


def _resolve_backend() -> str:
    forced = WHISPERFLOW_BACKEND
    if forced in {"http", "url", "server"} or (forced == "auto" and WHISPERFLOW_URL):
        if not WHISPERFLOW_URL:
            raise RuntimeError("WHISPERFLOW_BACKEND=http requires WHISPERFLOW_URL")
        return "http"
    if forced in {"mlx", "mlx-whisper"}:
        return "mlx"
    if forced in {"whisper", "openai-whisper", "whisper-cpp"}:
        return "whisper"
    if forced in {"faster", "faster-whisper", "ctranslate2"}:
        return "faster-whisper"

    model = WHISPERFLOW_MODEL
    if _mlx_importable() and _model_looks_mlx(model) and mlx_model_ready(model):
        return "mlx"
    if model in _OPENAI_WHISPER_NAMES and _whisper_importable():
        return "whisper"
    if _whisper_importable():
        return "whisper"
    if _faster_importable():
        return "faster-whisper"
    if _mlx_importable():
        return "mlx"
    raise RuntimeError(
        "Local WhisperFlow STT needs a backend. On Apple Silicon: pip install mlx-whisper. "
        "Or: pip install openai-whisper  (uses ~/.cache/whisper). "
        "Or set WHISPERFLOW_URL to an OpenAI-compatible local server."
    )


def _run_backend(backend: str, wav_bytes: bytes, model: str) -> tuple[str, str]:
    if backend == "http":
        return _transcribe_http(wav_bytes, model=model), model
    if backend == "mlx":
        return _transcribe_mlx(wav_bytes, model=model), model
    if backend == "faster-whisper":
        return _transcribe_faster(wav_bytes, model=model), model
    used = whisper_model_name(model)
    return _transcribe_whisper(wav_bytes, model=used), used


def transcribe_wav(wav_bytes: bytes, *, model: str | None = None) -> str:
    """Transcribe a WAV clip with local Whisper. May return empty (caller decides)."""
    if not wav_bytes:
        raise ValueError("No audio to transcribe.")
    model = (model or WHISPERFLOW_MODEL).strip() or WHISPERFLOW_MODEL
    with timed("transcribe_wav", bytes=len(wav_bytes), model=model):
        backend = resolve_backend()
        try:
            text, used_model = _run_backend(backend, wav_bytes, model)
        except Exception as exc:
            auto = WHISPERFLOW_BACKEND in {"", "auto"}
            if auto and backend != "whisper" and _whisper_importable():
                fallback = whisper_model_name(model)
                print(
                    f"[stt] whisperflow {backend} failed ({exc}) — "
                    f"falling back to local whisper {fallback}",
                    flush=True,
                )
                text, used_model = _run_backend("whisper", wav_bytes, fallback)
                backend = "whisper"
            else:
                raise
        print(f"[stt] provider=whisperflow backend={backend} model={used_model}", flush=True)
        return text
