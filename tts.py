"""
Text-to-speech for agent prompts via OpenAI or Sarvam + local playback.

Providers (TTS_PROVIDER):
  - openai — gpt-4o-mini-tts (default voice onyx) with steerable delivery
  - sarvam — Bulbul streaming TTS (default bulbul:v3 / shubh)

Playback on macOS uses `afplay` (system audio path) to avoid PortAudio duplex
crackle. Wake-word barge-in ("Hey Jarvis") is on by default for sync and
streaming TTS; set TTS_BARGE_IN=0 if an open mic during speech causes hiss.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

from openai import OpenAI

# numpy / sounddevice are loaded lazily so afplay-only paths (and streaming TTS
# workers) do not import PortAudio at module import time.

# openai | sarvam
TTS_PROVIDER = os.environ.get("TTS_PROVIDER", "openai").strip().lower()

TTS_MODEL = "gpt-4o-mini-tts"
TTS_FALLBACK_MODEL = "tts-1-hd"
TTS_FALLBACK_VOICE = "onyx"
TTS_INSTRUCTIONS = (
    "Voice: adult male, warm and human, slightly British, like a composed "
    "personal AI butler (Jarvis-like). Speak naturally and conversationally—"
    "not robotic, not overly dramatic. Calm confidence, clear diction, "
    "moderate pace. Keep confirmations brief and polite."
)

if TTS_PROVIDER in {"sarvam", "sarvamai", "bulbul"}:
    TTS_VOICE = (
        os.environ.get("TTS_VOICE")
        or os.environ.get("SARVAM_TTS_VOICE")
        or "shubh"
    ).strip().lower() or "shubh"
else:
    TTS_VOICE = (os.environ.get("TTS_VOICE") or "onyx").strip() or "onyx"

# Default ON — interrupt sync/streaming TTS with the wake word.
# Set TTS_BARGE_IN=0 if an open mic during speech causes speaker hiss.
BARGE_IN_DEFAULT = os.environ.get("TTS_BARGE_IN", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Prefer afplay on macOS (cleaner than PortAudio output). Set TTS_PLAYER=sounddevice to force.
_TTS_PLAYER = (
    (os.environ.get("TTS_PLAYER") or ("afplay" if sys.platform == "darwin" else "sounddevice")).strip().lower()
)
_FADE_MS = float(os.environ.get("TTS_FADE_MS", "8"))


def _use_sarvam() -> bool:
    return TTS_PROVIDER in {"sarvam", "sarvamai", "bulbul"}


def _numpy():
    import numpy as np

    return np


def _sounddevice():
    import sounddevice as sd

    return sd


def _try_sd_stop() -> None:
    try:
        _sounddevice().stop()
    except Exception:
        pass


def synthesize(client: OpenAI, text: str, voice: str = TTS_VOICE) -> bytes:
    """Return WAV bytes for `text`."""
    text = text.strip()
    if not text:
        raise ValueError("Nothing to speak.")

    if _use_sarvam():
        from sarvam_tts import synthesize_wav

        return synthesize_wav(text, speaker=voice)

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


def _wav_to_float_audio(wav_bytes: bytes):
    np = _numpy()
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        channels = wf.getnchannels()
        rate = wf.getframerate()
        sampwidth = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())

    if sampwidth == 2:
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        audio = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise RuntimeError(f"Unsupported sample width: {sampwidth}")

    if channels > 1:
        audio = audio.reshape(-1, channels)
    return audio, int(rate)


def _apply_fade(audio, rate: int, fade_ms: float = _FADE_MS):
    np = _numpy()
    if fade_ms <= 0 or audio.size == 0:
        return audio
    n = int(rate * (fade_ms / 1000.0))
    if n <= 0:
        return audio
    out = audio.copy()
    fade_n = min(n, out.shape[0] // 2)
    if fade_n <= 0:
        return out
    ramp_up = np.linspace(0.0, 1.0, fade_n, dtype=np.float32)
    ramp_down = np.linspace(1.0, 0.0, fade_n, dtype=np.float32)
    if out.ndim == 1:
        out[:fade_n] *= ramp_up
        out[-fade_n:] *= ramp_down
    else:
        out[:fade_n, :] *= ramp_up[:, None]
        out[-fade_n:, :] *= ramp_down[:, None]
    return out


def _write_temp_wav(wav_bytes: bytes) -> Path:
    fd, name = tempfile.mkstemp(prefix="cua-tts-", suffix=".wav")
    os.close(fd)
    path = Path(name)
    path.write_bytes(wav_bytes)
    return path


def _play_afplay(wav_bytes: bytes, *, interrupt_event=None) -> bool:
    """Play via macOS afplay; kill the process if interrupt_event is set."""
    if interrupt_event is not None and interrupt_event.is_set():
        return True
    path = _write_temp_wav(wav_bytes)
    proc: subprocess.Popen | None = None
    interrupted = False
    try:
        # Stop any PortAudio output that might still be holding the device.
        _try_sd_stop()
        proc = subprocess.Popen(
            ["afplay", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        while proc.poll() is None:
            if interrupt_event is not None and interrupt_event.is_set():
                interrupted = True
                proc.terminate()
                try:
                    proc.wait(timeout=1.0)
                except Exception:
                    proc.kill()
                break
            time.sleep(0.04)
        if proc.returncode not in (0, None) and not interrupted:
            # afplay failed — fall back to sounddevice once.
            return _play_sounddevice(wav_bytes, interrupt_event=interrupt_event)
        return interrupted or (interrupt_event is not None and interrupt_event.is_set())
    finally:
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


def _play_sounddevice(wav_bytes: bytes, *, interrupt_event=None) -> bool:
    sd = _sounddevice()
    audio, rate = _wav_to_float_audio(wav_bytes)
    audio = _apply_fade(audio, rate)
    _try_sd_stop()

    if interrupt_event is None:
        sd.play(audio, rate, blocking=True)
        return False

    if interrupt_event.is_set():
        return True

    n_frames = audio.shape[0]
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


def play_wav(
    wav_bytes: bytes,
    *,
    interrupt_event=None,
    force_rate: int | None = None,
) -> bool:
    """
    Play WAV bytes. On macOS defaults to afplay (ignores force_rate).

    Returns True if interrupted via interrupt_event.
    """
    del force_rate  # afplay plays native WAV rate; kept for call-site compat
    if _TTS_PLAYER in {"afplay", "system"} and sys.platform == "darwin":
        return _play_afplay(wav_bytes, interrupt_event=interrupt_event)
    return _play_sounddevice(wav_bytes, interrupt_event=interrupt_event)


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
    Uses the persistent wake monitor when barge-in is enabled (armed before
    synthesis so listening covers the full speak path).
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

    monitor = None
    if enable:
        try:
            from wake import ensure_persistent_wake

            # Arm before synthesize so wake covers API latency + playback.
            monitor = ensure_persistent_wake()
            if monitor is not None:
                monitor.clear()
        except Exception as exc:
            print(f"[tts] persistent wake unavailable ({exc})", flush=True)
            monitor = None

    wav_bytes = synthesize(client, text, voice=voice)

    if not enable or monitor is None:
        play_wav(wav_bytes)
        return False

    interrupted = play_wav(wav_bytes, interrupt_event=monitor.woken)
    if interrupted or monitor.woken.is_set():
        print("[tts] interrupted by wake word", flush=True)
        return True
    return False
