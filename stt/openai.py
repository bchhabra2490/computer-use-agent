"""OpenAI speech-to-text (Realtime live capture + file transcribe).

Live mic streaming stays in ``stt.listen_realtime``; this module owns the
one-shot file API used by ``stt.transcribe`` and phone-gateway clips.
"""

from __future__ import annotations

import io

from openai import OpenAI


def transcribe_wav(
    client: OpenAI,
    wav_bytes: bytes,
    *,
    model: str,
) -> str:
    """Transcribe a WAV clip with OpenAI ``audio.transcriptions``."""
    bio = io.BytesIO(wav_bytes)
    bio.name = "audio.wav"
    kwargs: dict = {
        "model": model,
        "file": bio,
    }
    # File models accept language; live-only models may not be used here.
    if model not in {"gpt-live-transcribe"}:
        kwargs["language"] = "en"
    result = client.audio.transcriptions.create(**kwargs)
    return (getattr(result, "text", None) or str(result) or "").strip()
