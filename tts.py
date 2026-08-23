"""
Text-to-speech for agent prompts via OpenAI or Sarvam + local playback.

Providers (TTS_PROVIDER):
  - openai — gpt-4o-mini-tts (default voice onyx) with steerable delivery
  - sarvam — Bulbul streaming TTS (default bulbul:v3 / shubh)

Playback on macOS uses `afplay` (system audio path) to avoid PortAudio duplex
crackle. Wake-word barge-in ("Hey Jarvis") and keyboard barge-in (Space / Esc /
Enter in the terminal) are on by default for sync and streaming TTS. Set
``TTS_BARGE_IN=0`` if an open mic during speech causes hiss; set
``TTS_KEYBOARD_BARGE=0`` to disable key interrupts.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import threading
import time
import wave
from collections import deque
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
        os.environ.get("TTS_VOICE") or os.environ.get("SARVAM_TTS_VOICE") or "shubh"
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
_PLAYBACK_LOCK = threading.Lock()
_SPEAK_LATER_Q: deque[tuple] = deque()
_SPEAK_LATER_CV = threading.Condition()
_SPEAK_LATER_THREAD: threading.Thread | None = None

_OFF = {"0", "false", "no", "off"}
# Console chatter ([tts] text / provider / barge). Default off — set TTS_LOG=1 to show.
TTS_LOG = os.environ.get("TTS_LOG", "0").strip().lower() not in _OFF
# Console [tts-latency] lines. File log under logs/ still written when path is set.
TTS_LATENCY_LOG = os.environ.get("TTS_LATENCY_LOG", "0").strip().lower() not in _OFF


def tts_print(message: str, *, force: bool = False) -> None:
    """Print a ``[tts] …`` line when TTS_LOG=1 (or ``force`` for real errors)."""
    if force or TTS_LOG:
        print(message, flush=True)


def tts_latency_print(message: str) -> None:
    """Print a ``[tts-latency] …`` line when TTS_LATENCY_LOG=1."""
    if TTS_LATENCY_LOG:
        print(message, flush=True)


def _use_sarvam() -> bool:
    return TTS_PROVIDER in {"sarvam", "sarvamai", "bulbul"}


def _wake_blob() -> str:
    try:
        from wake import get_last_wake

        hit = get_last_wake()
    except Exception:
        return ""
    if hit is None:
        return ""
    return f"{hit.label or ''} {hit.key or ''}".lower()


def active_tts_voice() -> str:
    """
    Voice for this turn: Rekha → Priya, Jarvis → Shubh (Sarvam).

    Override with TTS_VOICE_REKHA / TTS_VOICE_JARVIS (or SARVAM_TTS_VOICE_*).
    Falls back to TTS_VOICE when no wake has fired yet.
    """
    blob = _wake_blob()
    if _use_sarvam():
        rekha = (
            os.environ.get("TTS_VOICE_REKHA") or os.environ.get("SARVAM_TTS_VOICE_REKHA") or "priya"
        ).strip().lower() or "priya"
        jarvis = (
            os.environ.get("TTS_VOICE_JARVIS") or os.environ.get("SARVAM_TTS_VOICE_JARVIS") or "shubh"
        ).strip().lower() or "shubh"
        if "rekha" in blob:
            return rekha
        if "jarvis" in blob:
            return jarvis
        return TTS_VOICE
    if "rekha" in blob:
        return (os.environ.get("TTS_VOICE_REKHA") or TTS_VOICE).strip() or TTS_VOICE
    if "jarvis" in blob:
        return (os.environ.get("TTS_VOICE_JARVIS") or TTS_VOICE).strip() or TTS_VOICE
    return TTS_VOICE


def _numpy():
    import os

    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
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


def synthesize(client: OpenAI, text: str, voice: str | None = None) -> bytes:
    """Return WAV bytes for `text`."""
    text = text.strip()
    if not text:
        raise ValueError("Nothing to speak.")
    if not voice:
        voice = active_tts_voice()

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


def concat_wavs(parts: list[bytes]) -> bytes:
    """Join WAV blobs that share the same format (streaming TTS chunks)."""
    blobs = [p for p in parts if p]
    if not blobs:
        return b""
    if len(blobs) == 1:
        return blobs[0]
    frames: list[bytes] = []
    params = None
    for blob in blobs:
        with wave.open(io.BytesIO(blob), "rb") as src:
            if params is None:
                params = src.getparams()
            elif (
                src.getnchannels() != params.nchannels
                or src.getsampwidth() != params.sampwidth
                or src.getframerate() != params.framerate
            ):
                continue
            frames.append(src.readframes(src.getnframes()))
    if not frames or params is None:
        return blobs[0]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setparams(params)
        for chunk in frames:
            out.writeframes(chunk)
    return buf.getvalue()


def _phone_reply_sink() -> bool:
    try:
        from app_status import reply_sink

        return reply_sink() == "phone"
    except Exception:
        return False


def play_wav(
    wav_bytes: bytes,
    *,
    interrupt_event=None,
    force_rate: int | None = None,
) -> bool:
    """
    Play WAV bytes. On macOS defaults to afplay (ignores force_rate).

    When the current turn came from the phone, skip Mac speakers and publish
    the WAV for ``GET /v1/speech`` instead.

    Returns True if interrupted via interrupt_event.
    """
    del force_rate  # afplay plays native WAV rate; kept for call-site compat
    if _phone_reply_sink():
        try:
            from app_status import write_phone_speech

            write_phone_speech(wav_bytes)
        except Exception as exc:
            tts_print(f"[tts] phone speech publish failed ({exc})", force=True)
        return False

    from app_status import begin_tts_playback, end_tts_playback

    begin_tts_playback()
    try:
        with _PLAYBACK_LOCK:
            if _TTS_PLAYER in {"afplay", "system"} and sys.platform == "darwin":
                return _play_afplay(wav_bytes, interrupt_event=interrupt_event)
            return _play_sounddevice(wav_bytes, interrupt_event=interrupt_event)
    finally:
        end_tts_playback()


def speak(
    client: OpenAI,
    text: str,
    voice: str | None = None,
    *,
    barge_in: bool | None = None,
) -> bool:
    """
    Synthesize and play `text` aloud.

    Returns True if the user interrupted (wake word or keyboard barge-in).
    Uses the persistent wake monitor when mic barge-in is enabled (armed before
    synthesis so listening covers the full speak path). Keyboard barge-in works
    even when mic barge-in is off, as long as the terminal is focused.
    Phone-sink replies skip Mac playback and barge-in (the phone is the speaker).
    """
    tts_print(f"[tts] {text}")
    phone = _phone_reply_sink()
    enable = False if phone else (BARGE_IN_DEFAULT if barge_in is None else bool(barge_in))
    if enable:
        try:
            from wake import text_mentions_wake_phrase

            if text_mentions_wake_phrase(text):
                tts_print(
                    "[tts] barge-in off for this line (contains wake phrase — avoids echo)",
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
            tts_print(f"[tts] persistent wake unavailable ({exc})", force=True)
            monitor = None

    from app_status import begin_tts_playback, end_tts_playback

    # Cover synth latency too (session may already be back on waiting/listening).
    begin_tts_playback()
    try:
        wav_bytes = synthesize(client, text, voice=voice or active_tts_voice())

        wake_event = monitor.woken if (enable and monitor is not None) else None
        try:
            from keyboard_barge import acquire_tts_interrupt

            interrupt_event, release = acquire_tts_interrupt(wake_event)
        except Exception as exc:
            tts_print(f"[tts] keyboard barge unavailable ({exc})", force=True)
            interrupt_event, release = wake_event, (lambda: None)

        if interrupt_event is None:
            play_wav(wav_bytes)
            return False

        try:
            interrupted = play_wav(wav_bytes, interrupt_event=interrupt_event)
            if interrupted or interrupt_event.is_set():
                if wake_event is not None and wake_event.is_set():
                    tts_print("[tts] interrupted by wake word")
                # keyboard path already logged in keyboard_barge
                elif not interrupted:
                    tts_print("[tts] interrupted")
                return True
            return False
        finally:
            release()
    finally:
        end_tts_playback()


def _speak_later_worker() -> None:
    while True:
        with _SPEAK_LATER_CV:
            while not _SPEAK_LATER_Q:
                _SPEAK_LATER_CV.wait()
            item = _SPEAK_LATER_Q.popleft()
        client, text, voice = item
        try:
            speak(client, text, voice=voice)
        except Exception as e:
            tts_print(f"[tts] background speak failed: {e}", force=True)


def speak_later(
    client: OpenAI,
    text: str,
    voice: str | None = None,
) -> None:
    """Queue TTS and return immediately so the agent can keep working."""
    line = (text or "").strip()
    if not line:
        return
    global _SPEAK_LATER_THREAD
    with _SPEAK_LATER_CV:
        _SPEAK_LATER_Q.append((client, line, voice))
        if _SPEAK_LATER_THREAD is None or not _SPEAK_LATER_THREAD.is_alive():
            _SPEAK_LATER_THREAD = threading.Thread(
                target=_speak_later_worker,
                name="tts-speak-later",
                daemon=True,
            )
            _SPEAK_LATER_THREAD.start()
        _SPEAK_LATER_CV.notify()
