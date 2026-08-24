"""Sarvam AI Bulbul text-to-speech (HTTP streaming → WAV)."""

from __future__ import annotations

import io
import os
import wave

SARVAM_TTS_MODEL = os.environ.get("SARVAM_TTS_MODEL", "bulbul:v3").strip() or "bulbul:v3"
SARVAM_TTS_VOICE = os.environ.get("SARVAM_TTS_VOICE", "shubh").strip().lower() or "shubh"
SARVAM_TTS_LANGUAGE = os.environ.get("SARVAM_TTS_LANGUAGE", "en-IN").strip() or "en-IN"
SARVAM_TTS_SAMPLE_RATE = int(os.environ.get("SARVAM_TTS_SAMPLE_RATE", "24000"))
# HTTP stream accepts up to 3500 chars; keep a margin for safety.
SARVAM_TTS_MAX_CHARS = int(os.environ.get("SARVAM_TTS_MAX_CHARS", "3400"))


def _pcm_to_wav(pcm: bytes, *, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def _split_text(text: str, max_chars: int) -> list[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    parts: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chars:
            parts.append(remaining)
            break
        window = remaining[:max_chars]
        cut = max(window.rfind(". "), window.rfind("? "), window.rfind("! "), window.rfind(" "))
        if cut < max_chars // 4:
            cut = max_chars
        else:
            cut = cut + 1
        piece = remaining[:cut].strip()
        if piece:
            parts.append(piece)
        remaining = remaining[cut:].strip()
    return parts


def synthesize_wav(text: str, *, speaker: str | None = None) -> bytes:
    """
    Stream speech via Sarvam ``convert_stream`` (linear16) and return a WAV.

    Uses model ``bulbul:v3`` and speaker ``shubh`` by default.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("Nothing to speak.")

    from stt.sarvam import get_client

    client = get_client()
    model = SARVAM_TTS_MODEL
    voice = (speaker or SARVAM_TTS_VOICE).strip().lower() or "shubh"
    language = SARVAM_TTS_LANGUAGE
    rate = SARVAM_TTS_SAMPLE_RATE

    pcm_parts: list[bytes] = []
    for piece in _split_text(text, SARVAM_TTS_MAX_CHARS):
        for chunk in client.text_to_speech.convert_stream(
            text=piece,
            model=model,
            speaker=voice,
            language_code=language,
            output_audio_codec="linear16",
            speech_sample_rate=rate,
        ):
            if chunk:
                pcm_parts.append(chunk)

    pcm = b"".join(pcm_parts)
    if not pcm:
        raise RuntimeError("Sarvam TTS returned empty audio.")

    try:
        from tts import tts_print

        tts_print(
            f"[tts] provider=sarvam model={model} voice={voice} lang={language}",
        )
    except Exception:
        pass
    return _pcm_to_wav(pcm, sample_rate=rate)
