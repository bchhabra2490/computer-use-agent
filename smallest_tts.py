"""Smallest AI Lightning text-to-speech (HTTP → WAV)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

SMALLEST_API_KEY = (os.environ.get("SMALLEST_API_KEY") or "").strip()
SMALLEST_BASE_URL = (
    os.environ.get("SMALLEST_BASE_URL") or "https://api.smallest.ai/waves/v1"
).strip().rstrip("/")
# lightning_v3.1 | lightning_v3.1_pro
SMALLEST_TTS_MODEL = (
    os.environ.get("SMALLEST_TTS_MODEL") or "lightning_v3.1"
).strip() or "lightning_v3.1"
SMALLEST_TTS_VOICE = (
    os.environ.get("SMALLEST_TTS_VOICE") or os.environ.get("TTS_VOICE") or "magnus"
).strip() or "magnus"
SMALLEST_TTS_LANGUAGE = (os.environ.get("SMALLEST_TTS_LANGUAGE") or "en").strip() or "en"
SMALLEST_TTS_SAMPLE_RATE = int(os.environ.get("SMALLEST_TTS_SAMPLE_RATE") or "24000")
SMALLEST_TTS_TIMEOUT = float(os.environ.get("SMALLEST_TTS_TIMEOUT") or "30")


def synthesize_wav(text: str, *, voice_id: str | None = None) -> bytes:
    """Synthesize ``text`` via Lightning and return WAV bytes."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Nothing to speak.")
    if not SMALLEST_API_KEY:
        raise RuntimeError("SMALLEST_API_KEY is not set")

    voice = (voice_id or SMALLEST_TTS_VOICE).strip() or SMALLEST_TTS_VOICE
    body: dict = {
        "text": text,
        "voice_id": voice,
        "model": SMALLEST_TTS_MODEL,
        "sample_rate": SMALLEST_TTS_SAMPLE_RATE,
        "output_format": "wav",
        "language": SMALLEST_TTS_LANGUAGE,
    }
    req = urllib.request.Request(
        f"{SMALLEST_BASE_URL}/tts",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {SMALLEST_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "audio/wav",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=SMALLEST_TTS_TIMEOUT) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"Smallest TTS HTTP {e.code}: {detail}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f"Smallest TTS request failed: {e}") from e

    if not data or len(data) < 44:
        raise RuntimeError("Smallest TTS returned empty or invalid audio")
    return data
