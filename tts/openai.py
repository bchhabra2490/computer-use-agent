"""OpenAI text-to-speech (gpt-4o-mini-tts, with tts-1-hd fallback)."""

from __future__ import annotations

from openai import OpenAI

TTS_MODEL = "gpt-4o-mini-tts"
TTS_FALLBACK_MODEL = "tts-1-hd"
TTS_FALLBACK_VOICE = "onyx"
TTS_INSTRUCTIONS = (
    "Voice: adult male, warm and human, slightly British, like a composed "
    "personal AI butler (Jarvis-like). Speak naturally and conversationally—"
    "not robotic, not overly dramatic. Calm confidence, clear diction, "
    "moderate pace. Keep confirmations brief and polite."
)


def synthesize_wav(client: OpenAI, text: str, voice: str) -> bytes:
    """Return WAV bytes from OpenAI speech synthesis."""
    try:
        speech = client.audio.speech.create(
            model=TTS_MODEL,
            voice=voice,
            input=text,
            instructions=TTS_INSTRUCTIONS,
            response_format="wav",
        )
    except Exception:
        speech = client.audio.speech.create(
            model=TTS_FALLBACK_MODEL,
            voice=TTS_FALLBACK_VOICE,
            input=text,
            response_format="wav",
        )
    return speech.content
