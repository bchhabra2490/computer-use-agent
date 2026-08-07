"""
Text-to-speech for agent prompts via OpenAI audio.speech + sounddevice playback.

Uses gpt-4o-mini-tts with a deep male voice and steerable delivery aimed at a
calm, Jarvis-like desktop assistant (natural speech, not robotic).

Supports wake-word barge-in: while speaking, a background monitor listens for
"Hey Jarvis"; if heard, playback stops immediately.
"""

from __future__ import annotations

import io
import os
import time
import wave

import numpy as np
import sounddevice as sd
from openai import OpenAI

TTS_MODEL = "gpt-4o-mini-tts"
TTS_FALLBACK_MODEL = "tts-1-hd"
# Deep, authoritative male — closest built-in fit for a Jarvis-like assistant.
TTS_VOICE = "onyx"
TTS_FALLBACK_VOICE = "onyx"
# Steer tone/accent/pacing (supported by gpt-4o-mini-tts only).
TTS_INSTRUCTIONS = (
    "Voice: adult male, warm and human, slightly British, like a composed "
    "personal AI butler (Jarvis-like). Speak naturally and conversationally—"
    "not robotic, not overly dramatic. Calm confidence, clear diction, "
    "moderate pace. Keep confirmations brief and polite."
)

# Default on — set TTS_BARGE_IN=0 to disable wake-word interrupt during speech.
BARGE_IN_DEFAULT = os.environ.get("TTS_BARGE_IN", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}


def synthesize(client: OpenAI, text: str, voice: str = TTS_VOICE) -> bytes:
    """Return WAV bytes for `text`."""
    text = text.strip()
    if not text:
        raise ValueError("Nothing to speak.")

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


def play_wav(
    wav_bytes: bytes,
    *,
    interrupt_event=None,
) -> bool:
    """
    Play a WAV byte string through the default output device.

    If `interrupt_event` is set while playing, stops immediately.
    Returns True if interrupted, False if playback finished normally.
    """
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        channels = wf.getnchannels()
        rate = wf.getframerate()
        sampwidth = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())

    if sampwidth != 2:
        raise RuntimeError(f"Unsupported sample width: {sampwidth}")

    audio = np.frombuffer(frames, dtype=np.int16)
    if channels > 1:
        audio = audio.reshape(-1, channels)

    if interrupt_event is None:
        sd.play(audio, rate)
        sd.wait()
        return False

    if interrupt_event.is_set():
        return True

    n_frames = audio.shape[0] if getattr(audio, "ndim", 1) >= 1 else len(audio)
    duration = float(n_frames) / float(rate)
    sd.play(audio, rate, blocking=False)
    interrupted = False
    deadline = time.monotonic() + duration + 0.05
    try:
        while time.monotonic() < deadline:
            if interrupt_event.is_set():
                interrupted = True
                sd.stop()
                break
            time.sleep(0.04)
        else:
            sd.wait()
    finally:
        if interrupted:
            try:
                sd.stop()
            except Exception:
                pass
    return interrupted or interrupt_event.is_set()


def speak(
    client: OpenAI,
    text: str,
    voice: str = TTS_VOICE,
    *,
    barge_in: bool | None = None,
) -> bool:
    """
    Synthesize and play `text` aloud.

    Returns True if the user interrupted with the wake word (barge-in).
    Barge-in is auto-disabled when the spoken text contains the wake phrase,
    so speaker echo cannot false-trigger (e.g. "Say Hey Jarvis…").
    """
    print(f"[tts] {text}")
    enable = BARGE_IN_DEFAULT if barge_in is None else bool(barge_in)
    if enable:
        try:
            from wake import text_mentions_wake_phrase

            if text_mentions_wake_phrase(text):
                print(
                    "[tts] barge-in off for this line (contains wake phrase — avoids echo)",
                    flush=True,
                )
                enable = False
        except Exception:
            pass

    if not enable:
        play_wav(synthesize(client, text, voice=voice))
        return False

    from wake import WakeMonitor

    monitor = WakeMonitor()
    monitor.start()
    try:
        interrupted = play_wav(
            synthesize(client, text, voice=voice),
            interrupt_event=monitor.woken,
        )
    finally:
        monitor.stop()

    if interrupted or monitor.woken.is_set():
        print("[tts] interrupted by wake word", flush=True)
        return True
    return False
