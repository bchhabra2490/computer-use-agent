"""Local Phonon-1 speech-to-text (Fermion English ASR).

Record-then-transcribe, same shape as WhisperFlow / Sarvam. Backends:

  1. ``PHONON_URL`` — OpenAI-compatible ``fermion serve``
     (``POST /v1/audio/transcriptions``).
  2. In-process ``fermion-research`` — Apple Silicon MLX (or CPU when that
     engine is the one Fermion selects). Model stays loaded on one worker
     thread; MLX streams are thread-local.

Default model is ``FermionResearch/Phonon-1`` (415 MB). Aliases: ``phonon``,
``phonon-1``, ``micro`` / ``FermionResearch/Phonon-1-Micro``, ``big`` /
``FermionResearch/Phonon-1-Big``.
"""

from __future__ import annotations

import io
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .timing import timed

PHONON_URL = (os.environ.get("PHONON_URL") or "").strip().rstrip("/")
PHONON_API_KEY = (os.environ.get("PHONON_API_KEY") or "local").strip() or "local"
PHONON_MODEL = (
    os.environ.get("PHONON_MODEL") or "FermionResearch/Phonon-1"
).strip() or "FermionResearch/Phonon-1"
PHONON_BACKEND = (os.environ.get("PHONON_BACKEND") or "auto").strip().lower()

_INSTALL = (
    "Local Phonon-1 STT needs fermion-research and the speech runtime. "
    "This repo pins transformers 4, so skip Fermion's Neutrino LLM extras: "
    "pip install 'fermion-research>=0.1.24' --no-deps && "
    "pip install mlx mlx-audio mlx-lm soundfile scipy zstandard. "
    "Or run `fermion serve --model phonon` and set "
    "PHONON_URL=http://127.0.0.1:8000/v1"
)

_SPEECH_MODULES = ("mlx", "mlx_audio", "mlx_lm", "soundfile", "scipy")

_pool: ThreadPoolExecutor | None = None
_local: tuple[str, Any] | None = None  # (model spec, SpeechModel)


def _openai_base_url(url: str) -> str:
    if url.endswith("/v1"):
        return url
    return url + "/v1"


def _fermion_importable() -> bool:
    try:
        import fermion.transcribe  # noqa: F401
        import fermion._speech.backends  # noqa: F401

        return True
    except ImportError:
        return False


def _speech_runtime_ready() -> bool:
    import importlib.util

    return all(importlib.util.find_spec(name) is not None for name in _SPEECH_MODULES)


def resolve_backend() -> str:
    """Which engine ``transcribe_wav`` will use."""
    with timed("resolve_backend"):
        return _resolve_backend()


def _resolve_backend() -> str:
    forced = PHONON_BACKEND
    if forced in {"http", "url", "server"} or (forced == "auto" and PHONON_URL):
        if not PHONON_URL:
            raise RuntimeError("PHONON_BACKEND=http requires PHONON_URL")
        return "http"
    if forced in {"fermion", "local", "mlx", "inprocess", "in-process"}:
        if not _fermion_importable():
            raise RuntimeError(_INSTALL)
        return "local"
    if _fermion_importable() and _speech_runtime_ready():
        return "local"
    if _fermion_importable():
        raise RuntimeError(
            "fermion-research is installed but the Phonon speech extras are not. "
            "On Apple Silicon: pip install mlx mlx-audio mlx-lm soundfile scipy zstandard"
        )
    raise RuntimeError(_INSTALL)


def _pool_worker() -> ThreadPoolExecutor:
    global _pool
    if _pool is None:
        # MLX default streams are thread-local; load + decode must share one
        # worker for the process lifetime (same constraint as `fermion serve`).
        _pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="phonon-stt")
    return _pool


def _load_local_on_worker(model: str) -> Any:
    global _local
    if _local is not None and _local[0] == model:
        return _local[1]
    from fermion._speech import backends, fetch
    from fermion.transcribe import _resolve

    try:
        repo, key, pin, local_dir = _resolve(model)
    except SystemExit as exc:
        raise RuntimeError(str(exc) or f"unknown Phonon model {model!r}") from exc
    try:
        engine_kind = backends.resolve("Phonon STT")
    except SystemExit as exc:
        raise RuntimeError(str(exc) or _INSTALL) from exc
    model_dir = local_dir if local_dir is not None else fetch.ensure(repo, key, pin)
    speech = backends.load(
        engine_kind,
        model_dir,
        profile=key,
        backend=pin["backend"],
        quiet=True,
    )
    _local = (model, speech)
    return speech


def _transcribe_local_on_worker(wav_bytes: bytes, model: str) -> str:
    from fermion._speech.engine import read_audio_bytes

    speech = _load_local_on_worker(model)
    audio = read_audio_bytes(wav_bytes, filename="clip.wav")
    text, _decode_s, _audio_s = speech.transcribe_array(audio)
    return (text or "").strip()


def _transcribe_http(wav_bytes: bytes, *, model: str) -> str:
    from openai import OpenAI

    with timed("transcribe_http", model=model, bytes=len(wav_bytes)):
        bio = io.BytesIO(wav_bytes)
        bio.name = "audio.wav"
        client = OpenAI(base_url=_openai_base_url(PHONON_URL), api_key=PHONON_API_KEY)
        result = client.audio.transcriptions.create(model=model, file=bio)
    return (getattr(result, "text", None) or str(result) or "").strip()


def _transcribe_local(wav_bytes: bytes, *, model: str) -> str:
    with timed("transcribe_local", model=model, bytes=len(wav_bytes)):
        return _pool_worker().submit(_transcribe_local_on_worker, wav_bytes, model).result()


def transcribe_wav(wav_bytes: bytes, *, model: str | None = None) -> str:
    """Transcribe a WAV clip with Phonon-1. May return empty (caller decides)."""
    if not wav_bytes:
        raise ValueError("No audio to transcribe.")
    model = (model or PHONON_MODEL).strip() or PHONON_MODEL
    with timed("transcribe_wav", bytes=len(wav_bytes), model=model):
        backend = resolve_backend()
        if backend == "http":
            text = _transcribe_http(wav_bytes, model=model)
        else:
            text = _transcribe_local(wav_bytes, model=model)
        print(f"[stt] provider=phonon backend={backend} model={model}", flush=True)
        return text
