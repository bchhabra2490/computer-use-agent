"""Sarvam AI Saaras speech-to-text (file / REST transcription)."""

from __future__ import annotations

import io
import os
from typing import Any

SARVAM_API_KEY = (os.environ.get("SARVAM_API_KEY") or os.environ.get("SARVAM_API_SUBSCRIPTION_KEY") or "").strip()
SARVAM_STT_MODEL = os.environ.get("SARVAM_STT_MODEL", "saaras:v3").strip() or "saaras:v3"
SARVAM_STT_MODE = os.environ.get("SARVAM_STT_MODE", "transcribe").strip() or "transcribe"
# unknown = auto-detect (recommended unless clips are < ~3s).
SARVAM_LANGUAGE = os.environ.get("SARVAM_STT_LANGUAGE", "unknown").strip() or "unknown"

# REST sync API rejects clips longer than ~30s.
SARVAM_MAX_SECONDS = float(os.environ.get("SARVAM_STT_MAX_SECONDS", "28"))

_client: Any | None = None


def sarvam_configured() -> bool:
    return bool(SARVAM_API_KEY)


def get_client():
    """Shared SarvamAI client (STT + TTS)."""
    global _client
    if _client is not None:
        return _client
    if not SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY is not set. Add it to .env or export SARVAM_API_KEY=…")
    try:
        from sarvamai import SarvamAI
    except ImportError as e:
        raise RuntimeError("sarvamai is not installed. Run: pip install sarvamai") from e
    _client = SarvamAI(api_subscription_key=SARVAM_API_KEY)
    return _client


def transcribe_wav(wav_bytes: bytes, *, model: str | None = None, mode: str | None = None) -> str:
    """
    Transcribe a WAV clip with Sarvam Saaras (REST, ≤ ~30s).

    Returns the transcript string (may be empty — caller decides).
    """
    if not wav_bytes:
        raise ValueError("No audio to transcribe.")

    model = (model or SARVAM_STT_MODEL).strip() or "saaras:v3"
    mode = (mode or SARVAM_STT_MODE).strip() or "transcribe"
    client = get_client()

    bio = io.BytesIO(wav_bytes)
    bio.name = "audio.wav"

    kwargs: dict[str, Any] = {
        "file": bio,
        "model": model,
        "mode": mode,
    }
    # Only pass language when explicitly set (unknown / empty → model auto-detect).
    lang = SARVAM_LANGUAGE
    if lang and lang.lower() not in {"unknown", "auto", ""}:
        kwargs["language_code"] = lang

    response = client.speech_to_text.transcribe(**kwargs)
    text = (getattr(response, "transcript", None) or "").strip()
    if not text and isinstance(response, dict):
        text = str(response.get("transcript") or "").strip()
    print(f"[stt] provider=sarvam model={model} mode={mode}", flush=True)
    return text
