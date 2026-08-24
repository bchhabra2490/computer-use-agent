"""
Speech-to-text for dictating tasks and answering spoken questions.

Providers live as modules in this package (``STT_PROVIDER``):
  - ``stt.openai`` — stream mic PCM to OpenAI Realtime (`gpt-live-transcribe`);
    ends after STT_IDLE_SECONDS with no new transcribed words.
  - ``stt.sarvam`` — record locally until silence, then Sarvam Saaras (`saaras:v3`).
  - ``stt.whisperflow`` — record locally until silence, then on-device Whisper
    (mlx-whisper / faster-whisper / optional local HTTP).

Add another backend as ``stt/<name>.py`` and branch on ``STT_PROVIDER``.
"""

from __future__ import annotations

import base64
import io
import math
import os
import queue
import re
import select
import sys
import threading
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

# Before numpy/OpenBLAS (can SIGSEGV if over-threaded on macOS).
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import numpy as np
import sounddevice as sd
from openai import OpenAI

from tts import speak
from .timing import timed

# Device capture → Realtime API expects 24 kHz mono PCM16.
REALTIME_RATE = 24_000
CHANNELS = 1
# Saved clips use the same rate we send to the API.
SAMPLE_RATE = REALTIME_RATE

# openai | sarvam | whisperflow
STT_PROVIDER = os.environ.get("STT_PROVIDER", "openai").strip().lower()
# Live Realtime transcription model (OpenAI path).
TRANSCRIBE_MODEL = os.environ.get("STT_MODEL", "gpt-live-transcribe")
# Optional file re-transcribe / judge (not used by default listen_once).
REFINE_MODEL = os.environ.get("STT_REFINE_MODEL", "gpt-4o-transcribe")
JUDGE_MODEL = os.environ.get("STT_JUDGE_MODEL", "gpt-5-mini")
# near_field | far_field | off — laptop mics + room fan → far_field
NOISE_REDUCTION = os.environ.get("STT_NOISE_REDUCTION", "far_field").strip().lower()
_ROOT = Path(__file__).resolve().parent.parent
RECORDINGS_DIR = _ROOT / "recordings"
MIC_DEVICE = os.environ.get("MIC_DEVICE") or None

SILENCE_SECONDS = 3.0
# End utterance when transcription produces no new text for this long (not mic energy).
# Sarvam path uses the same value as post-speech silence before uploading the clip.
TRANSCRIPT_IDLE_SECONDS = float(os.environ.get("STT_IDLE_SECONDS", str(SILENCE_SECONDS)))
CONFIRM_RECORD_SECONDS = 2.5
POST_TTS_COOLDOWN = 1.0
CHUNK_SECONDS = 0.1
MAX_RECORD_SECONDS = 90.0
MAX_WAIT_FOR_SPEECH = 15.0
MIC_WARMUP_SECONDS = 0.25
NORMALIZE_PEAK = 0.85
# Cut rumble / laptop fan below this (Hz) before streaming.
FAN_HIGHPASS_HZ = float(os.environ.get("STT_HIGHPASS_HZ", "140"))
# Kept for offline record_until_silence helper only.
SPEECH_PEAK = 0.02
VAD_THRESHOLD = float(os.environ.get("STT_VAD_THRESHOLD", "0.55"))

_mic_logged = False

_YES = frozenset(
    {
        "y",
        "yes",
        "yeah",
        "yep",
        "yap",
        "ya",
        "yah",
        "sure",
        "ok",
        "okay",
        "confirm",
        "confirmed",
        "send",
        "use",
        "do",
        "go",
        "proceed",
        "accept",
        "affirmative",
        "please",
        "run",
        "save",
        "correct",
        "right",
        "si",
    }
)
_NO = frozenset(
    {
        "n",
        "no",
        "nope",
        "nah",
        "cancel",
        "stop",
        "decline",
        "reject",
        "skip",
        "negative",
    }
)
_QUIT = frozenset({"q", "quit", "exit", "abort"})
_RETRY = frozenset(
    {
        "r",
        "retry",
        "again",
        "redo",
        "repeat",
        "rerecord",
        "restart",
    }
)


class NoSpeechError(RuntimeError):
    """Recording / transcription produced nothing usable."""


class PhoneCommandReady(Exception):
    """A phone-gateway text command arrived; abort mic capture and use it."""


class ListenCancelled(Exception):
    """User aborted listen (Esc / tray Cancel) — do not process audio."""


def save_recording(
    wav_bytes: bytes,
    *,
    transcript: str | None = None,
    kind: str = "utterance",
    live_transcript: str | None = None,
    refine_transcript: str | None = None,
) -> Path:
    """Write captured mic audio (and optional transcript) under recordings/."""
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe_kind = re.sub(r"[^a-z0-9_-]+", "-", kind.lower()).strip("-") or "utterance"
    base = RECORDINGS_DIR / f"{stamp}_{safe_kind}"
    wav_path = base.with_suffix(".wav")
    wav_path.write_bytes(wav_bytes)
    if transcript is not None or live_transcript is not None or refine_transcript is not None:
        lines: list[str] = []
        if live_transcript is not None:
            lines.append(f"live: {live_transcript.strip()}")
        if refine_transcript is not None:
            lines.append(f"refine: {refine_transcript.strip()}")
        if transcript is not None:
            lines.append(f"chosen: {transcript.strip()}")
        base.with_suffix(".txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[mic] saved {wav_path.name}" + (f' → "{transcript}"' if transcript else ""))
    return wav_path


def _resolve_input_device() -> int | str | None:
    if MIC_DEVICE is None:
        return None
    text = str(MIC_DEVICE).strip()
    if text.isdigit():
        return int(text)
    return text


def _input_device_info() -> dict:
    device = _resolve_input_device()
    if device is None:
        device = sd.default.device[0] if isinstance(sd.default.device, (list, tuple)) else sd.default.device
    return sd.query_devices(device, "input")


def _capture_sample_rate() -> int:
    info = _input_device_info()
    rate = int(info.get("default_samplerate") or 48_000)
    return rate if rate > 0 else 48_000


def _log_mic_settings(capture_rate: int) -> None:
    global _mic_logged
    if _mic_logged:
        return
    info = _input_device_info()
    idx = info.get("index", "?")
    name = info.get("name", "unknown")
    override = f" (MIC_DEVICE={MIC_DEVICE})" if MIC_DEVICE else ""
    nr = NOISE_REDUCTION if NOISE_REDUCTION != "off" else "off"
    print(
        f"[mic] device={idx} {name!r} capture={capture_rate}Hz → realtime={REALTIME_RATE}Hz "
        f"model={TRANSCRIBE_MODEL} noise={nr} idle={TRANSCRIPT_IDLE_SECONDS:g}s "
        f"highpass={FAN_HIGHPASS_HZ:g}Hz{override}",
        flush=True,
    )
    _mic_logged = True


def _resample(pcm: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Resample mono float PCM (prefer integer-ratio average for 48k→24k)."""
    pcm = np.asarray(pcm, dtype=np.float32).reshape(-1)
    if src_rate == dst_rate or pcm.size == 0:
        return pcm
    if src_rate % dst_rate == 0:
        factor = src_rate // dst_rate
        n = (pcm.size // factor) * factor
        if n <= 0:
            return np.zeros(0, dtype=np.float32)
        return pcm[:n].reshape(-1, factor).mean(axis=1).astype(np.float32)
    duration = pcm.size / float(src_rate)
    target_len = max(1, int(round(duration * dst_rate)))
    x_old = np.linspace(0.0, 1.0, num=pcm.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=target_len, endpoint=False)
    return np.interp(x_new, x_old, pcm).astype(np.float32)


def _normalize_peak(pcm: np.ndarray, target: float = NORMALIZE_PEAK) -> np.ndarray:
    if target <= 0 or pcm.size == 0:
        return pcm.astype(np.float32)
    peak = float(np.max(np.abs(pcm)))
    if peak < 1e-5:
        return pcm.astype(np.float32)
    return (pcm * (target / peak)).astype(np.float32)


def _float_to_wav(pcm: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    pcm = np.clip(np.asarray(pcm, dtype=np.float32).reshape(-1), -1.0, 1.0)
    pcm_i16 = (pcm * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_i16.tobytes())
    return buf.getvalue()


def _float_to_pcm16_b64(pcm: np.ndarray) -> str:
    pcm = np.clip(np.asarray(pcm, dtype=np.float32).reshape(-1), -1.0, 1.0)
    pcm_i16 = (pcm * 32767.0).astype(np.int16)
    return base64.b64encode(pcm_i16.tobytes()).decode("ascii")


def _peak(chunk: np.ndarray) -> float:
    if chunk.size == 0:
        return 0.0
    return float(np.max(np.abs(chunk.astype(np.float64))))


def _prepare_mic() -> None:
    try:
        sd.stop()
    except Exception:
        pass


def _cue_listen_start() -> None:
    """Ping as soon as the STT stream is open — do not block capture."""
    try:
        from wake import play_listen_start_chime

        play_listen_start_chime(blocking=False)
    except Exception:
        pass


def _open_input_stream(capture_rate: int, chunk_frames: int):
    device = _resolve_input_device()
    kwargs: dict = {
        "samplerate": capture_rate,
        "channels": CHANNELS,
        "dtype": "float32",
        "blocksize": chunk_frames,
        "latency": "low",
    }
    if device is not None:
        kwargs["device"] = device
    try:
        kwargs["extra_settings"] = sd.CoreAudioSettings(conversion_quality="max")
    except Exception:
        pass
    return sd.InputStream(**kwargs)


class FanNoiseFilter:
    """High-pass + adaptive spectral gate tuned for steady laptop/room fan noise."""

    def __init__(self, sample_rate: int, cutoff_hz: float = FAN_HIGHPASS_HZ):
        self.sample_rate = sample_rate
        self.cutoff_hz = cutoff_hz
        # First-order high-pass state
        rc = 1.0 / (2.0 * math.pi * max(20.0, cutoff_hz))
        dt = 1.0 / float(sample_rate)
        self._hp_alpha = rc / (rc + dt)
        self._prev_x = 0.0
        self._prev_y = 0.0
        # Noise profile (magnitude spectrum) learned from quiet frames
        self._noise_mag: np.ndarray | None = None
        self._noise_rms = 1e-4
        self._learn_left = int(0.5 * sample_rate)  # ~0.5s of quiet to learn fan
        self._fft_n = 1024

    def _highpass(self, pcm: np.ndarray) -> np.ndarray:
        # First-order IIR high-pass (vectorized recurrence).
        x = np.asarray(pcm, dtype=np.float32).reshape(-1)
        if x.size == 0:
            return x
        a = self._hp_alpha
        dx = np.diff(x, prepend=self._prev_x)
        y = np.empty_like(x)
        y[0] = a * (self._prev_y + dx[0])
        for i in range(1, x.size):
            y[i] = a * (y[i - 1] + dx[i])
        self._prev_x = float(x[-1])
        self._prev_y = float(y[-1])
        return y

    def _update_noise(self, pcm: np.ndarray) -> None:
        rms = float(np.sqrt(np.mean(np.square(pcm))) + 1e-12)
        self._noise_rms = 0.9 * self._noise_rms + 0.1 * rms
        n = self._fft_n
        if pcm.size < n:
            padded = np.zeros(n, dtype=np.float32)
            padded[: pcm.size] = pcm
            frame = padded
        else:
            frame = pcm[:n]
        mag = np.abs(np.fft.rfft(frame * np.hanning(n)))
        if self._noise_mag is None:
            self._noise_mag = mag
        else:
            self._noise_mag = np.minimum(self._noise_mag, mag) * 0.15 + self._noise_mag * 0.85

    def _spectral_gate(self, pcm: np.ndarray) -> np.ndarray:
        if self._noise_mag is None or pcm.size == 0:
            return pcm
        n = self._fft_n
        hop = n // 2
        window = np.hanning(n).astype(np.float32)
        out = np.zeros(pcm.size + n, dtype=np.float32)
        weight = np.zeros_like(out)
        noise = self._noise_mag
        alpha, beta = 1.15, 0.08  # over-subtract fan; keep a little residual
        i = 0
        while i < pcm.size:
            frame = np.zeros(n, dtype=np.float32)
            take = min(n, pcm.size - i)
            frame[:take] = pcm[i : i + take]
            spec = np.fft.rfft(frame * window)
            mag = np.abs(spec)
            phase = np.angle(spec)
            clean_mag = np.maximum(mag - alpha * noise[: mag.size], beta * mag)
            cleaned = np.fft.irfft(clean_mag * np.exp(1j * phase), n=n).astype(np.float32)
            out[i : i + n] += cleaned * window
            weight[i : i + n] += window
            i += hop
        weight = np.maximum(weight, 1e-6)
        return (out[: pcm.size] / weight[: pcm.size]).astype(np.float32)

    def process(self, pcm: np.ndarray) -> np.ndarray:
        pcm = np.asarray(pcm, dtype=np.float32).reshape(-1)
        if pcm.size == 0:
            return pcm
        pcm = self._highpass(pcm)
        rms = float(np.sqrt(np.mean(np.square(pcm))) + 1e-12)
        # Learn / refresh fan profile when energy is near the noise floor.
        if self._learn_left > 0 or rms < self._noise_rms * 1.8:
            self._update_noise(pcm)
            self._learn_left = max(0, self._learn_left - pcm.size)
        pcm = self._spectral_gate(pcm)
        # Soft gate: duck leftover steady hiss between words
        if rms < self._noise_rms * 1.6:
            pcm *= 0.15
        return pcm.astype(np.float32)


def _transcription_config() -> dict:
    """Model-specific transcription fields for session.update."""
    model = TRANSCRIBE_MODEL
    cfg: dict = {
        "model": model,
        "prompt": (
            "Transcribe clear English speech for a computer-use agent. " "Ignore steady background fan or HVAC noise."
        ),
    }
    # gpt-live-transcribe / gpt-transcribe prefer `languages` over `language`.
    if model in {"gpt-live-transcribe", "gpt-transcribe"}:
        cfg["languages"] = ["en"]
        cfg["delay"] = "low"
    else:
        cfg["language"] = "en"
    return cfg


def _noise_reduction_session_value() -> dict | None:
    if NOISE_REDUCTION in {"", "off", "none", "false", "0"}:
        return None
    kind = NOISE_REDUCTION if NOISE_REDUCTION in {"near_field", "far_field"} else "far_field"
    return {"type": kind}


def _model_supports_turn_detection(model: str) -> bool:
    # gpt-live-transcribe / gpt-realtime-whisper reject server VAD; client must commit.
    return model not in {
        "gpt-live-transcribe",
        "gpt-realtime-whisper",
        "gpt-transcribe",
    }


def _transcription_session(*, mode: str) -> dict:
    """Build a Realtime `session.update` body for transcription-only mode."""
    audio_input: dict = {
        "format": {"type": "audio/pcm", "rate": REALTIME_RATE},
        "transcription": _transcription_config(),
        # Most live transcription models require null — we commit locally on silence.
        "turn_detection": None,
    }
    if _model_supports_turn_detection(TRANSCRIBE_MODEL):
        silence_ms = int(CONFIRM_RECORD_SECONDS * 1000) if mode == "confirm" else int(SILENCE_SECONDS * 1000)
        audio_input["turn_detection"] = {
            "type": "server_vad",
            "threshold": VAD_THRESHOLD,
            "prefix_padding_ms": 300,
            "silence_duration_ms": silence_ms,
        }
    nr = _noise_reduction_session_value()
    if nr is not None:
        audio_input["noise_reduction"] = nr
    return {
        "type": "transcription",
        "audio": {"input": audio_input},
    }


def _event_type(event) -> str:
    if hasattr(event, "type"):
        return str(event.type)
    if isinstance(event, dict):
        return str(event.get("type", ""))
    return ""


def _event_delta(event) -> str:
    delta = getattr(event, "delta", None)
    if delta is None and isinstance(event, dict):
        delta = event.get("delta")
    return str(delta or "")


def _event_transcript(event) -> str:
    text = getattr(event, "transcript", None)
    if text is None and isinstance(event, dict):
        text = event.get("transcript")
    return str(text or "").strip()


def _print_live(text: str) -> None:
    # Carriage-return live line so partial transcripts feel realtime.
    sys.stdout.write("\r[stt] " + text[:120] + ("…" if len(text) > 120 else "") + " " * 8)
    sys.stdout.flush()


def _use_sarvam() -> bool:
    return STT_PROVIDER in {"sarvam", "saaras", "sarvamai"}


def _use_whisperflow() -> bool:
    return STT_PROVIDER in {
        "whisperflow",
        "whisper-flow",
        "whisper_flow",
        "whisper",
        "mlx",
        "mlx-whisper",
    }


def _use_file_stt() -> bool:
    """Providers that record a clip, then run file STT (no live partials)."""
    return _use_sarvam() or _use_whisperflow()


def _send_requested() -> bool:
    """True once when the menu-bar Send item is clicked during this listen."""
    try:
        from app_status import consume_send

        return consume_send()
    except Exception:
        return False


def _cancel_requested() -> bool:
    """True once when Cancel / Esc was requested during this listen."""
    try:
        from app_status import consume_cancel

        return consume_cancel()
    except Exception:
        return False


def _cancel_pending() -> bool:
    try:
        from app_status import cancel_pending

        return cancel_pending()
    except Exception:
        return False


def _phone_pending() -> bool:
    try:
        from app_status import utterance_pending

        return utterance_pending()
    except Exception:
        return False


def _consume_phone_utterance() -> str | None:
    try:
        from app_status import consume_utterance

        text = consume_utterance()
    except Exception:
        return None
    return (text or "").strip() or None


def _listen_end_spotter():
    try:
        from wake import listen_end_spotter

        return listen_end_spotter()
    except Exception:
        return None


def _listen_end_hint() -> str:
    try:
        from wake import format_listen_end_hint

        return format_listen_end_hint()
    except Exception:
        return "Send"


def _end_phrase_live_enabled() -> bool:
    if os.environ.get("WAKE_END_LIVE_STT", "1").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False
    try:
        from wake import END_LISTEN_PHRASES, listen_end_enabled

        return listen_end_enabled() and bool(END_LISTEN_PHRASES)
    except Exception:
        return False


def _strip_listen_wake(text: str, *, wake_ended: bool) -> str:
    try:
        from wake import (
            strip_trailing_end_phrase,
            strip_trailing_wake_phrase,
            strip_wake_phrase,
        )
    except Exception:
        return (text or "").strip()
    out = strip_wake_phrase(text)
    out = strip_trailing_end_phrase(out)
    if wake_ended:
        out = strip_trailing_wake_phrase(out, include_short=True)
    return out.strip()


class _EndPhraseWatcher:
    """Live STT sidecar: stop recording when the transcript ends with the closer."""

    def __init__(self, client: OpenAI):
        self.hit = threading.Event()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._client = client
        self._conn = None
        self._thread: threading.Thread | None = None
        self.partial = ""

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="end-phrase-watch",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        try:
            from wake import transcript_has_end_phrase

            with self._client.realtime.connect(
                extra_query={"intent": "transcription"}
            ) as connection:
                connection.session.update(session=_transcription_session(mode="freeform"))
                with self._lock:
                    self._conn = connection
                self._ready.set()
                for event in connection:
                    if self._stop.is_set() or self.hit.is_set():
                        break
                    et = _event_type(event)
                    if et == "conversation.item.input_audio_transcription.delta":
                        piece = _event_delta(event)
                        if not piece:
                            continue
                        self.partial += piece
                        if transcript_has_end_phrase(self.partial):
                            print("[stt] over and out — processing audio.")
                            from wake import play_over_and_out_chime

                            play_over_and_out_chime()
                            self.hit.set()
                            break
                    elif et == "conversation.item.input_audio_transcription.completed":
                        text = _event_transcript(event) or self.partial
                        if transcript_has_end_phrase(text):
                            print("[stt] over and out — processing audio.")
                            from wake import play_over_and_out_chime

                            play_over_and_out_chime()
                            self.hit.set()
                            break
        except Exception as exc:
            print(f"[stt] end-phrase watch unavailable ({exc})", file=sys.stderr)
        finally:
            self._ready.set()
            with self._lock:
                self._conn = None

    def feed_pcm24k(self, pcm: np.ndarray) -> None:
        if self.hit.is_set() or self._stop.is_set() or not self._ready.is_set():
            return
        arr = np.asarray(pcm, dtype=np.float32).reshape(-1)
        if arr.size == 0:
            return
        with self._lock:
            conn = self._conn
        if conn is None:
            return
        try:
            conn.input_audio_buffer.append(audio=_float_to_pcm16_b64(arr))
        except Exception:
            pass

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            conn = self._conn
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)


def listen_realtime(
    client: OpenAI,
    *,
    prompt: str | None = None,
    mode: str = "freeform",
    max_wait_for_speech: float | None = None,
    on_partial: Callable[[str], None] | None = None,
) -> tuple[str, bytes]:
    """
    Capture one utterance and return (transcript, wav_bytes).

    OpenAI: stream to Realtime transcription; end after idle with no new words.
    Sarvam / WhisperFlow: record until silence, then file STT.
    ``on_partial`` (OpenAI path only) is called with the growing live transcript.
    """
    # Persistent wake owns the mic for barge-in — release it for STT.
    try:
        from wake import pause_persistent_wake, resume_persistent_wake
    except Exception:
        pause_persistent_wake = None  # type: ignore[assignment]
        resume_persistent_wake = None  # type: ignore[assignment]

    if pause_persistent_wake is not None:
        pause_persistent_wake()
    try:
        from wake import reset_over_and_out_chime

        reset_over_and_out_chime()
    except Exception:
        pass
    try:
        from app_status import set_stt_listening

        set_stt_listening(True)
    except Exception:
        set_stt_listening = None  # type: ignore[assignment]
    try:
        if _use_sarvam():
            with timed("listen_sarvam"):
                return _listen_sarvam(
                    client,
                    prompt=prompt,
                    mode=mode,
                    max_wait_for_speech=max_wait_for_speech,
                )
        if _use_whisperflow():
            with timed("listen_whisperflow"):
                return _listen_whisperflow(
                    client,
                    prompt=prompt,
                    mode=mode,
                    max_wait_for_speech=max_wait_for_speech,
                )
        with timed("listen_openai_realtime"):
            return _listen_realtime_body(
                client,
                prompt=prompt,
                mode=mode,
                max_wait_for_speech=max_wait_for_speech,
                on_partial=on_partial,
            )
    finally:
        if set_stt_listening is not None:
            try:
                set_stt_listening(False)
            except Exception:
                pass
        if resume_persistent_wake is not None:
            resume_persistent_wake()


def _listen_record_then_transcribe(
    client: OpenAI,
    *,
    transcribe,
    fail_label: str,
    banner: str,
    max_record_seconds: float,
    prompt: str | None = None,
    mode: str = "freeform",
    max_wait_for_speech: float | None = None,
) -> tuple[str, bytes]:
    """Record until pause, then run a file STT ``transcribe(wav) -> str``."""
    idle = CONFIRM_RECORD_SECONDS if mode == "confirm" else TRANSCRIPT_IDLE_SECONDS
    wait_limit = MAX_WAIT_FOR_SPEECH if max_wait_for_speech is None else float(max_wait_for_speech)
    max_secs = min(MAX_RECORD_SECONDS, float(max_record_seconds))
    hint = _listen_end_hint()
    default_prompt = (
        f"Listening for yes/no… (sends after {idle:g}s silence, {hint} → {banner})"
        if mode == "confirm"
        else f"Listening… (sends after {idle:g}s silence, {hint} → {banner})"
    )

    spotter = _listen_end_spotter()
    watch = None
    # File STT already uses the ONNX over-and-out spotter. The live OpenAI
    # sidecar is for the streaming provider only — and it is a connection
    # error on local WhisperFlow when the Realtime socket is unused.
    if _end_phrase_live_enabled() and not _use_whisperflow():
        watch = _EndPhraseWatcher(client)
        watch.start()
    try:
        with timed("record_until_silence", mode=mode):
            wav = record_until_silence(
                silence_seconds=idle,
                speech_peak=SPEECH_PEAK,
                max_wait_for_speech=wait_limit,
                max_record_seconds=max_secs,
                prompt=prompt or default_prompt,
                require_speech=True,
                wake_spotter=spotter,
                end_watch=watch,
            )
    finally:
        if watch is not None:
            watch.stop()
    try:
        with timed("transcribe", label=fail_label, bytes=len(wav)):
            text = transcribe(wav)
    except Exception as e:
        raise NoSpeechError(f"{fail_label} failed: {e}") from e
    with timed("strip_listen_wake"):
        text = _strip_listen_wake(
            text or "",
            wake_ended=bool((spotter and spotter.hit) or (watch and watch.hit.is_set())),
        )
    if not text:
        raise NoSpeechError("Transcription came back empty — try speaking again.")
    return text, wav


def _listen_sarvam(
    client: OpenAI,
    *,
    prompt: str | None = None,
    mode: str = "freeform",
    max_wait_for_speech: float | None = None,
) -> tuple[str, bytes]:
    """Record until pause, then transcribe with Sarvam Saaras (REST ≤ ~30s)."""
    from .sarvam import SARVAM_MAX_SECONDS, SARVAM_STT_MODEL, transcribe_wav

    return _listen_record_then_transcribe(
        client,
        transcribe=transcribe_wav,
        fail_label="Sarvam STT",
        banner=f"Sarvam {SARVAM_STT_MODEL}",
        max_record_seconds=SARVAM_MAX_SECONDS,
        prompt=prompt,
        mode=mode,
        max_wait_for_speech=max_wait_for_speech,
    )


def _listen_whisperflow(
    client: OpenAI,
    *,
    prompt: str | None = None,
    mode: str = "freeform",
    max_wait_for_speech: float | None = None,
) -> tuple[str, bytes]:
    """Record until pause, then transcribe with local WhisperFlow."""
    from .whisperflow import WHISPERFLOW_MODEL, transcribe_wav

    return _listen_record_then_transcribe(
        client,
        transcribe=transcribe_wav,
        fail_label="WhisperFlow STT",
        banner=f"WhisperFlow {WHISPERFLOW_MODEL}",
        max_record_seconds=MAX_RECORD_SECONDS,
        prompt=prompt,
        mode=mode,
        max_wait_for_speech=max_wait_for_speech,
    )


def _emit_partial(on_partial: Callable[[str], None] | None, live: str) -> None:
    if on_partial is None:
        return
    try:
        on_partial(live)
    except Exception as e:
        print(f"[stt] on_partial failed: {e}", flush=True)


def _listen_realtime_body(
    client: OpenAI,
    *,
    prompt: str | None = None,
    mode: str = "freeform",
    max_wait_for_speech: float | None = None,
    on_partial: Callable[[str], None] | None = None,
) -> tuple[str, bytes]:
    wait_limit = MAX_WAIT_FOR_SPEECH if max_wait_for_speech is None else float(max_wait_for_speech)
    _prepare_mic()
    capture_rate = _capture_sample_rate()
    _log_mic_settings(capture_rate)
    idle = CONFIRM_RECORD_SECONDS if mode == "confirm" else TRANSCRIPT_IDLE_SECONDS
    hint = _listen_end_hint()
    print(
        prompt
        or (
            f"Listening for yes/no… (sends after {idle:g}s without new words, {hint}; Esc cancels)"
            if mode == "confirm"
            else f"Listening… (sends after {idle:g}s without new words, {hint}; Esc cancels)"
        )
    )
    if _phone_pending():
        raise PhoneCommandReady()

    chunk_frames = max(1, int(CHUNK_SECONDS * capture_rate))
    warmup_frames = int(MIC_WARMUP_SECONDS * capture_rate)
    noise = FanNoiseFilter(capture_rate, FAN_HIGHPASS_HZ)

    stop = threading.Event()
    errors: queue.Queue[BaseException] = queue.Queue()
    pcm_24k_chunks: list[np.ndarray] = []
    send_lock = threading.Lock()
    # "committed" here means "stop appending / finish listen" — not WS commit ack.
    committed = threading.Event()
    cancelled = threading.Event()

    # Shared transcript state — idle timer arms only after the first word.
    state_lock = threading.Lock()
    shared: dict = {
        "partial": "",
        "last_delta_at": None,
        "first_word_at": None,
        "timer_armed": False,
        "finish_deadline": None,
    }
    started_at = time.monotonic()
    mic_deadline = started_at + MAX_RECORD_SECONDS
    wake_spotter = _listen_end_spotter()
    wake_send = threading.Event()
    # After end-listen, use live partials — do not block on input_audio_buffer.completed.
    # Concurrent WS commit/send from worker threads during recv can wedge the socket.
    END_FINISH_SECONDS = float(os.environ.get("STT_END_FINISH_SECONDS", "1.5"))
    hotkeys = _ListenHotkeys(cancel_keys=STT_CANCEL_KEYS, send_keys=STT_SEND_KEYS)
    hotkeys.start()

    def _close_connection(connection) -> None:
        try:
            connection.close()
        except Exception:
            pass

    def _abort_listen(connection, reason: str) -> None:
        """Stop capture and discard — do not return a transcript."""
        if cancelled.is_set():
            return
        try:
            from app_status import consume_cancel

            consume_cancel()
        except Exception:
            pass
        print(f"[stt] {reason}", flush=True)
        cancelled.set()
        committed.set()
        stop.set()
        with state_lock:
            shared["finish_deadline"] = time.monotonic()
        errors.put(ListenCancelled("Listen cancelled"))
        _close_connection(connection)

    def _finish_listen(connection, reason: str, *, settle: float | None = None) -> None:
        """Stop capture and unblock the recv loop; keep any live partial transcript."""
        if committed.is_set() or cancelled.is_set():
            return
        print(f"[stt] {reason}", flush=True)
        committed.set()
        stop.set()
        wait = END_FINISH_SECONDS if settle is None else max(0.0, float(settle))
        with state_lock:
            shared["finish_deadline"] = time.monotonic() + wait

        def _force_close() -> None:
            # Let trailing deltas arrive, then close so `for event in connection` cannot hang.
            time.sleep(wait)
            _close_connection(connection)

        threading.Thread(target=_force_close, name="stt-finish-close", daemon=True).start()

    def mic_worker(connection) -> None:
        try:
            with _open_input_stream(capture_rate, chunk_frames) as stream:
                _cue_listen_start()
                if warmup_frames > 0:
                    data, _ = stream.read(warmup_frames)
                    raw = np.asarray(data, dtype=np.float32).reshape(-1)
                    cleaned = noise.process(raw)
                    pcm_24k = _resample(cleaned, capture_rate, REALTIME_RATE)
                    if pcm_24k.size:
                        pcm_24k_chunks.append(pcm_24k.copy())
                        b64 = _float_to_pcm16_b64(pcm_24k)
                        with send_lock:
                            if not committed.is_set():
                                connection.input_audio_buffer.append(audio=b64)
                while not stop.is_set():
                    if time.monotonic() > mic_deadline:
                        break
                    data, overflowed = stream.read(chunk_frames)
                    if overflowed:
                        print("[mic] warning: input overflow", file=sys.stderr)
                    raw = np.asarray(data, dtype=np.float32).reshape(-1)
                    cleaned = noise.process(raw)
                    if wake_spotter is not None:
                        try:
                            if wake_spotter.feed(cleaned, capture_rate):
                                print("[stt] wake word — processing audio.", flush=True)
                                wake_send.set()
                                from wake import play_over_and_out_chime

                                play_over_and_out_chime()
                        except Exception:
                            pass
                    if committed.is_set():
                        break
                    pcm_24k = _resample(cleaned, capture_rate, REALTIME_RATE)
                    if pcm_24k.size == 0:
                        continue
                    peak = _peak(pcm_24k)
                    if peak > 1e-4:
                        pcm_24k = np.clip(pcm_24k * min(NORMALIZE_PEAK / peak, 4.0), -1.0, 1.0)
                    pcm_24k_chunks.append(pcm_24k.copy())
                    b64 = _float_to_pcm16_b64(pcm_24k)
                    with send_lock:
                        if not committed.is_set():
                            connection.input_audio_buffer.append(audio=b64)
        except BaseException as exc:  # noqa: BLE001 — surface to main thread
            errors.put(exc)
            stop.set()

    def idle_watch_worker(connection) -> None:
        """3s idle timer starts only after the first transcribed word."""
        try:
            while not stop.is_set() and not committed.is_set():
                time.sleep(0.1)
                now = time.monotonic()
                with state_lock:
                    text = shared["partial"].strip()
                    last = shared["last_delta_at"]
                    first = shared["first_word_at"]
                if hotkeys.cancel.is_set() or _cancel_pending():
                    _abort_listen(connection, "cancelled — discarding audio.")
                    return
                if _phone_pending():
                    print("[stt] phone command — using typed text.", flush=True)
                    stop.set()
                    _close_connection(connection)
                    errors.put(PhoneCommandReady())
                    return
                if wake_send.is_set() or hotkeys.send.is_set() or _send_requested():
                    if wake_send.is_set():
                        reason = "over and out — finishing with live transcript."
                    elif hotkeys.send.is_set():
                        reason = "Enter — processing audio."
                    else:
                        reason = "Send — processing audio."
                    _finish_listen(connection, reason)
                    return
                # No words yet: wait (do not run the 3s send timer).
                if first is None or not text or last is None:
                    if (now - started_at) >= wait_limit:
                        print(
                            f"[stt] no words after {wait_limit:g}s — aborting listen.",
                            file=sys.stderr,
                            flush=True,
                        )
                        errors.put(NoSpeechError("No speech transcribed — try again."))
                        stop.set()
                        _close_connection(connection)
                    continue
                if (now - last) >= idle:
                    _finish_listen(
                        connection,
                        f"no new words for {idle:g}s — sending.",
                        settle=0.4,
                    )
                    return
                if now >= mic_deadline:
                    _finish_listen(connection, "max record time — sending.", settle=0.4)
                    return
        except BaseException as exc:  # noqa: BLE001
            errors.put(exc)
            stop.set()
            _close_connection(connection)

    # Transcription sessions must use intent=transcription and must NOT pass ?model=.
    try:
        with client.realtime.connect(extra_query={"intent": "transcription"}) as connection:
            connection.session.update(session=_transcription_session(mode=mode))

            worker = threading.Thread(target=mic_worker, args=(connection,), daemon=True)
            watcher = threading.Thread(target=idle_watch_worker, args=(connection,), daemon=True)
            worker.start()
            watcher.start()

            final_text = ""
            deadline = started_at + MAX_RECORD_SECONDS + 20.0

            try:
                for event in connection:
                    if not errors.empty():
                        raise errors.get()
                    if cancelled.is_set() or hotkeys.cancel.is_set() or _cancel_pending():
                        if not cancelled.is_set():
                            _abort_listen(connection, "cancelled — discarding audio.")
                        raise ListenCancelled("Listen cancelled")
                    et = _event_type(event)
                    if et == "conversation.item.input_audio_transcription.delta":
                        piece = _event_delta(event)
                        if piece and piece.strip():
                            with state_lock:
                                shared["partial"] += piece
                                now = time.monotonic()
                                shared["last_delta_at"] = now
                                if shared["first_word_at"] is None:
                                    shared["first_word_at"] = now
                                    if not shared["timer_armed"]:
                                        shared["timer_armed"] = True
                                        print(
                                            f"\n[stt] first word — {idle:g}s idle timer started",
                                            flush=True,
                                        )
                                live = shared["partial"]
                            _print_live(live)
                            _emit_partial(on_partial, live)
                            try:
                                from wake import transcript_has_end_phrase

                                if transcript_has_end_phrase(live):
                                    from wake import play_over_and_out_chime

                                    play_over_and_out_chime()
                                    wake_send.set()
                                    with state_lock:
                                        final_text = shared["partial"].strip()
                                    sys.stdout.write("\n")
                                    _finish_listen(
                                        connection,
                                        "over and out — finishing with live transcript.",
                                        settle=0.35,
                                    )
                            except Exception:
                                pass
                    elif et == "conversation.item.input_audio_transcription.completed":
                        with state_lock:
                            fallback = shared["partial"].strip()
                        final_text = _event_transcript(event) or fallback
                        if final_text:
                            _emit_partial(on_partial, final_text)
                        sys.stdout.write("\n")
                        stop.set()
                        committed.set()
                        break
                    elif et == "conversation.item.input_audio_transcription.failed":
                        sys.stdout.write("\n")
                        err = getattr(event, "error", None)
                        raise NoSpeechError(f"Realtime transcription failed: {err or event}")
                    elif et == "error":
                        # Empty-buffer commit errors are ignorable if we already have partials.
                        with state_lock:
                            has_partial = bool(shared["partial"].strip())
                        if committed.is_set() and has_partial:
                            sys.stdout.write("\n")
                            break
                        sys.stdout.write("\n")
                        raise RuntimeError(getattr(event, "error", event))

                    with state_lock:
                        finish_at = shared["finish_deadline"]
                    if finish_at is not None:
                        deadline = min(deadline, finish_at)

                    if stop.is_set() and not committed.is_set() and shared["first_word_at"] is None:
                        # Aborted with no words.
                        break
                    if committed.is_set() and finish_at is not None and time.monotonic() >= finish_at:
                        break
                    if time.monotonic() > deadline:
                        break
            except ListenCancelled:
                raise
            except Exception:
                # Finish-watcher connection.close() unblocks recv; keep live partial.
                with state_lock:
                    has_partial = bool(shared["partial"].strip())
                if cancelled.is_set():
                    raise ListenCancelled("Listen cancelled")
                if not (committed.is_set() and (has_partial or final_text)):
                    raise
            finally:
                stop.set()
                committed.set()
                worker.join(timeout=2.0)
                watcher.join(timeout=1.0)
    finally:
        hotkeys.stop()

    if not errors.empty():
        err = errors.get()
        raise err

    if cancelled.is_set():
        raise ListenCancelled("Listen cancelled")

    if not pcm_24k_chunks:
        raise NoSpeechError("No audio captured — check microphone permissions.")

    pcm_all = np.concatenate(pcm_24k_chunks)
    wav = _float_to_wav(_normalize_peak(pcm_all), REALTIME_RATE)
    with state_lock:
        fallback = shared["partial"].strip()
    text = _strip_listen_wake(
        final_text.strip() or fallback,
        wake_ended=bool(wake_spotter and wake_spotter.hit),
    )
    if not text:
        raise NoSpeechError("Transcription came back empty — try speaking again.")
    print(f"[stt] model=realtime:{TRANSCRIBE_MODEL} noise={NOISE_REDUCTION}")
    return text, wav


# Back-compat recording helpers (non-streaming) kept for scripts/tests.
def record_fixed(
    seconds: float = CONFIRM_RECORD_SECONDS,
    *,
    sample_rate: int | None = None,
    prompt: str | None = None,
) -> bytes:
    _prepare_mic()
    capture_rate = int(sample_rate) if sample_rate else _capture_sample_rate()
    _log_mic_settings(capture_rate)
    if prompt:
        print(prompt)
    chunk_frames = int(CHUNK_SECONDS * capture_rate)
    warmup_frames = int(MIC_WARMUP_SECONDS * capture_rate)
    noise = FanNoiseFilter(capture_rate)
    chunks: list[np.ndarray] = []
    target = int(seconds * capture_rate)
    got = 0
    with _open_input_stream(capture_rate, chunk_frames) as stream:
        if warmup_frames:
            data, _ = stream.read(warmup_frames)
            noise.process(np.asarray(data, dtype=np.float32).reshape(-1))
        while got < target:
            need = min(chunk_frames, target - got)
            data, _ = stream.read(need)
            cleaned = noise.process(np.asarray(data, dtype=np.float32).reshape(-1))
            chunks.append(_resample(cleaned, capture_rate, REALTIME_RATE))
            got += need
    pcm = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
    return _float_to_wav(_normalize_peak(pcm), REALTIME_RATE)


_ENTER_KEYS = frozenset({b"\n", b"\r"})
_CANCEL_KEY_ALIASES: dict[str, frozenset[bytes]] = {
    "esc": frozenset({b"\x1b"}),
    "escape": frozenset({b"\x1b"}),
    "space": frozenset({b" "}),
    "enter": frozenset({b"\n", b"\r"}),
    "return": frozenset({b"\n", b"\r"}),
}


def _parse_listen_keys(raw: str | None, *, default: str) -> frozenset[bytes]:
    text = (raw if raw is not None else default).strip().lower()
    if text in {"0", "false", "no", "off", ""}:
        return frozenset()
    out: set[bytes] = set()
    for part in text.split(","):
        token = part.strip()
        if not token:
            continue
        if token in _CANCEL_KEY_ALIASES:
            out |= _CANCEL_KEY_ALIASES[token]
        elif len(token) == 1:
            out.add(token.encode("utf-8"))
    return frozenset(out)


# Esc (default) aborts listen without processing. Enter still used by enter-only modes.
STT_CANCEL_KEYS = _parse_listen_keys(
    os.environ.get("STT_CANCEL_KEYS"),
    default="esc",
)
STT_SEND_KEYS = _parse_listen_keys(
    os.environ.get("STT_SEND_KEYS"),
    default="enter",
)


def _stdin_is_tty() -> bool:
    try:
        return bool(sys.stdin and sys.stdin.isatty())
    except Exception:
        return False


class _ListenHotkeys:
    """TTY hotkeys while STT owns the mic: cancel (Esc) and optional send (Enter)."""

    def __init__(
        self,
        *,
        cancel_keys: frozenset[bytes] | None = None,
        send_keys: frozenset[bytes] | None = None,
    ) -> None:
        self.cancel = threading.Event()
        self.send = threading.Event()
        self._cancel_keys = cancel_keys if cancel_keys is not None else STT_CANCEL_KEYS
        self._send_keys = send_keys if send_keys is not None else frozenset()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._old_term = None
        self._fd: int | None = None
        self._owned_tty = False

    @property
    def event(self) -> threading.Event:
        """Back-compat alias used by enter-only record helpers (send)."""
        return self.send

    def start(self) -> None:
        if sys.platform == "win32":
            return
        if not self._cancel_keys and not self._send_keys:
            return
        try:
            self._fd = os.open("/dev/tty", os.O_RDONLY)
            self._owned_tty = True
        except OSError:
            if not _stdin_is_tty():
                return
            self._fd = sys.stdin.fileno()
            self._owned_tty = False
        try:
            import termios
            import tty

            self._old_term = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        except Exception:
            if self._owned_tty and self._fd is not None:
                os.close(self._fd)
            self._fd = None
            self._owned_tty = False
            self._old_term = None
            return
        bits = []
        if self._cancel_keys:
            bits.append("Esc=cancel")
        if self._send_keys:
            bits.append("Enter=send")
        if bits:
            print(f"[stt] hotkeys: {', '.join(bits)} (terminal focused)", flush=True)
        self._thread = threading.Thread(
            target=self._loop,
            name="stt-listen-hotkeys",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.5)
        self._thread = None
        if self._old_term is not None and self._fd is not None:
            try:
                import termios

                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_term)
            except Exception:
                pass
            self._old_term = None
        if self._fd is not None:
            try:
                while True:
                    ready, _, _ = select.select([self._fd], [], [], 0)
                    if not ready:
                        break
                    os.read(self._fd, 1024)
            except Exception:
                pass
        if self._owned_tty and self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
        self._fd = None
        self._owned_tty = False

    def _loop(self) -> None:
        fd = self._fd
        if fd is None:
            return
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([fd], [], [], 0.05)
                if not ready:
                    continue
                data = os.read(fd, 32)
                if not data:
                    continue
                for i in range(len(data)):
                    key = data[i : i + 1]
                    if key in self._cancel_keys:
                        self.cancel.set()
                        return
                    if key in self._send_keys:
                        self.send.set()
                        return
            except Exception:
                return


# Back-compat name for enter-only helpers.
_EnterKeyListener = _ListenHotkeys


def record_until_silence(
    sample_rate: int | None = None,
    *,
    silence_seconds: float = SILENCE_SECONDS,
    speech_peak: float = SPEECH_PEAK,
    max_wait_for_speech: float = MAX_WAIT_FOR_SPEECH,
    max_record_seconds: float = MAX_RECORD_SECONDS,
    prompt: str = "Listening… (pause when done)",
    require_speech: bool = False,
    wake_spotter=None,
    end_watch=None,
    end_on_enter: bool = False,
    enter_only: bool = False,
) -> bytes:
    _prepare_mic()
    capture_rate = int(sample_rate) if sample_rate else _capture_sample_rate()
    _log_mic_settings(capture_rate)
    print(prompt)
    cancel_listener = _ListenHotkeys(
        cancel_keys=STT_CANCEL_KEYS,
        send_keys=STT_SEND_KEYS if end_on_enter else frozenset(),
    )
    cancel_listener.start()
    enter_listener = cancel_listener if end_on_enter else None
    chunk_frames = int(CHUNK_SECONDS * capture_rate)
    warmup_frames = int(MIC_WARMUP_SECONDS * capture_rate)
    noise = FanNoiseFilter(capture_rate)
    chunks: list[np.ndarray] = []
    heard = False
    sent = False
    silent_run = waited = total = 0.0
    try:
        with _open_input_stream(capture_rate, chunk_frames) as stream:
            _cue_listen_start()
            if warmup_frames:
                data, _ = stream.read(warmup_frames)
                cleaned = noise.process(np.asarray(data, dtype=np.float32).reshape(-1))
                chunks.append(_resample(cleaned, capture_rate, REALTIME_RATE))
                total += warmup_frames / float(capture_rate)
            while total < max_record_seconds:
                if cancel_listener.cancel.is_set() or _cancel_pending():
                    print("[stt] cancelled — discarding audio.", flush=True)
                    try:
                        from app_status import consume_cancel

                        consume_cancel()
                    except Exception:
                        pass
                    raise ListenCancelled("Listen cancelled")
                data, _ = stream.read(chunk_frames)
                cleaned = noise.process(np.asarray(data, dtype=np.float32).reshape(-1))
                pcm_24k = _resample(cleaned, capture_rate, REALTIME_RATE)
                chunks.append(pcm_24k)
                total += CHUNK_SECONDS
                if end_watch is not None:
                    try:
                        end_watch.feed_pcm24k(pcm_24k)
                        if end_watch.hit.is_set():
                            from wake import play_over_and_out_chime

                            play_over_and_out_chime()
                            sent = True
                            break
                    except Exception:
                        pass
                if wake_spotter is not None:
                    try:
                        if wake_spotter.feed(cleaned, capture_rate):
                            print("[stt] wake word — processing audio.")
                            from wake import play_over_and_out_chime

                            play_over_and_out_chime()
                            sent = True
                            break
                    except Exception:
                        pass
                if _phone_pending():
                    print("[stt] phone command — using typed text.", flush=True)
                    raise PhoneCommandReady()
                if _send_requested() or (enter_listener is not None and enter_listener.send.is_set()):
                    print("[stt] menu Send — processing audio.")
                    sent = True
                    break
                peak = _peak(cleaned)
                if peak >= speech_peak:
                    heard = True
                    silent_run = 0.0
                elif heard and not enter_only:
                    silent_run += CHUNK_SECONDS
                    if silent_run >= silence_seconds:
                        break
                else:
                    waited += CHUNK_SECONDS
                    if waited >= max_wait_for_speech:
                        break
    finally:
        cancel_listener.stop()
    if require_speech and not heard and not sent:
        raise NoSpeechError("No speech detected — try again.")
    pcm = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
    return _float_to_wav(_normalize_peak(pcm), REALTIME_RATE)


def record_until_enter(*args, **kwargs) -> bytes:
    kwargs.setdefault("end_on_enter", True)
    kwargs.setdefault("enter_only", True)
    return record_until_silence(*args, **kwargs)


def transcribe(client: OpenAI | None = None, wav_bytes: bytes = b"", model: str | None = None) -> str:
    """One-shot file transcription (OpenAI, Sarvam Saaras, or local WhisperFlow)."""
    if not wav_bytes:
        raise NoSpeechError("No audio to transcribe.")

    model_name = (model or "").strip()
    if _use_sarvam() or model_name.startswith("saaras:"):
        from .sarvam import transcribe_wav

        text = transcribe_wav(wav_bytes, model=model_name or None)
        if not text:
            raise NoSpeechError("Transcription came back empty — try speaking again.")
        return text

    if _use_whisperflow():
        from .whisperflow import transcribe_wav as whisperflow_transcribe

        text = whisperflow_transcribe(wav_bytes, model=model_name or None)
        if not text:
            raise NoSpeechError("Transcription came back empty — try speaking again.")
        return text

    from .openai import transcribe_wav as openai_transcribe_wav

    client = client or OpenAI()
    model = model or REFINE_MODEL
    text = openai_transcribe_wav(client, wav_bytes, model=model)
    if not text:
        raise NoSpeechError("Transcription came back empty — try speaking again.")
    print(f"[stt] model={model}")
    return text


def _response_output_text(response) -> str:
    chunks: list[str] = []
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) != "message":
            continue
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", None) == "output_text":
                chunks.append(part.text)
    if chunks:
        return "\n".join(chunks).strip()
    return (getattr(response, "output_text", None) or "").strip()


def choose_transcript(client: OpenAI, live: str, refined: str) -> str:
    """Pick the more relevant / coherent of live vs refined transcripts."""
    live = (live or "").strip()
    refined = (refined or "").strip()
    if not refined:
        return live
    if not live:
        return refined
    if _normalize_reply(live) == _normalize_reply(refined):
        print("[stt] live ≈ refine — using refine")
        return refined

    print("[stt] comparing live vs refine…")
    try:
        response = client.responses.create(
            model=JUDGE_MODEL,
            instructions=(
                "You compare two speech-to-text hypotheses of the SAME spoken utterance. "
                "Choose the hypothesis that is more fluent, coherent English and more "
                "plausible as a command or answer to a desktop voice assistant. "
                "Prefer clear meaning over raw length. Reply with exactly one token: "
                "LIVE or REFINE."
            ),
            input=(
                f"LIVE transcript:\n{live}\n\n"
                f"REFINE transcript:\n{refined}\n\n"
                "Which is better? Reply LIVE or REFINE only."
            ),
        )
        verdict = _response_output_text(response).upper()
        if re.search(r"\bLIVE\b", verdict) and not re.search(r"\bREFINE\b", verdict):
            print("[stt] judge → LIVE")
            return live
        if re.search(r"\bREFINE\b", verdict):
            print("[stt] judge → REFINE")
            return refined
        # Ambiguous reply — prefer the stronger file model.
        print(f"[stt] judge unclear ({verdict!r}) — using refine")
        return refined
    except Exception as e:
        print(f"[stt] judge failed ({e}) — using refine", file=sys.stderr)
        return refined


def refine_after_pause(client: OpenAI, live: str, wav_bytes: bytes) -> tuple[str, str]:
    """
    Re-transcribe the committed clip with REFINE_MODEL and choose vs live.
    Returns (chosen_text, refine_text).
    """
    print(f"[stt] re-transcribing pause with {REFINE_MODEL}…")
    try:
        refined = transcribe(client, wav_bytes, model=REFINE_MODEL)
    except Exception as e:
        print(f"[stt] refine failed ({e}) — keeping live", file=sys.stderr)
        return live, ""
    print(f'[stt] live:    "{live}"')
    print(f'[stt] refine:  "{refined}"')
    chosen = choose_transcript(client, live, refined)
    print(f'[stt] chosen:  "{chosen}"')
    return chosen, refined


def _normalize_reply(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s']", " ", text)
    return " ".join(text.split())


def classify_yes_no(text: str) -> str | None:
    """Return 'yes', 'no', 'quit', 'retry', or None if unclear."""
    norm = _normalize_reply(text)
    if not norm:
        return None

    if norm in _YES:
        return "yes"
    if norm in _NO:
        return "no"
    if norm in _QUIT:
        return "quit"
    if norm in _RETRY:
        return "retry"

    tokens = norm.split()
    token_set = set(tokens)

    if token_set & _QUIT:
        return "quit"
    if token_set & _RETRY or "again" in token_set:
        return "retry"

    has_no = any(t in _NO or t == "no" for t in tokens)
    has_yes = any(t in _YES or t.startswith("ye") or t in {"ya", "yah"} for t in tokens)
    if has_no and not has_yes:
        return "no"
    if has_yes and not has_no:
        return "yes"

    if re.search(r"\byes\b|\byeah\b|\byep\b", norm):
        return "yes"
    if re.search(r"\bno\b|\bnope\b|\bnah\b", norm):
        return "no"

    return None


def _tag_speaker(wav_bytes: bytes | None) -> None:
    if not wav_bytes:
        return
    try:
        from speaker_id import enabled, identify, set_last_speaker

        if not enabled():
            set_last_speaker(None)
            return
        set_last_speaker(identify(wav_bytes))
    except Exception as e:
        print(f"[speaker] tag failed ({e})", flush=True)


def listen_once(
    client: OpenAI,
    *,
    prompt: str | None = None,
    mode: str = "freeform",
    max_attempts: int = 3,
    announce_retries: bool = True,
    max_wait_for_speech: float | None = None,
    on_partial: Callable[[str], None] | None = None,
) -> str:
    """Capture one utterance via the configured STT provider."""
    idle = CONFIRM_RECORD_SECONDS if mode == "confirm" else TRANSCRIPT_IDLE_SECONDS
    hint = _listen_end_hint()
    if _use_file_stt():
        default_prompt = (
            f"Say yes or no now… (sends after {idle:g}s silence, {hint})"
            if mode == "confirm"
            else f"Listening… (sends after {idle:g}s silence, {hint})"
        )
    else:
        default_prompt = (
            f"Say yes or no now… (sends after {idle:g}s without new words, {hint})"
            if mode == "confirm"
            else f"Listening… (sends after {idle:g}s without new words, {hint})"
        )
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        wav: bytes | None = None
        live = ""
        queued = _consume_phone_utterance()
        if queued:
            try:
                from speaker_id import clear_last_speaker

                clear_last_speaker()
            except Exception:
                pass
            print(f'Heard: "{queued}" (phone)')
            return queued
        try:
            try:
                from speaker_id import clear_last_speaker, enabled

                if enabled():
                    clear_last_speaker()
            except Exception:
                pass
            with timed("listen_once", attempt=attempt, mode=mode):
                live, wav = listen_realtime(
                    client,
                    prompt=prompt or default_prompt,
                    mode=mode,
                    max_wait_for_speech=max_wait_for_speech,
                    on_partial=on_partial,
                )
            try:
                from wake import play_listen_end_chime

                play_listen_end_chime()
            except Exception:
                pass
            with timed("save_recording"):
                save_recording(wav, transcript=live, kind=mode, live_transcript=live)
            print(f'Heard: "{live}"')
            with timed("tag_speaker"):
                _tag_speaker(wav)
            return live
        except ListenCancelled:
            print("[stt] listen cancelled.", flush=True)
            raise
        except PhoneCommandReady:
            queued = _consume_phone_utterance()
            if queued:
                print(f'Heard: "{queued}" (phone)')
                return queued
            last_err = NoSpeechError("Phone command vanished before it was read.")
            print(f"[mic] {last_err} (attempt {attempt}/{max_attempts})", file=sys.stderr)
            if attempt < max_attempts:
                time.sleep(0.2)
        except NoSpeechError as e:
            if wav:
                save_recording(
                    wav,
                    transcript="",
                    kind=f"{mode}-empty",
                    live_transcript=live or None,
                )
            last_err = e
            print(f"[mic] {e} (attempt {attempt}/{max_attempts})", file=sys.stderr)
            if attempt < max_attempts and announce_retries:
                interrupted = speak(client, "I didn't hear you. Please speak again.")
                if not interrupted:
                    time.sleep(POST_TTS_COOLDOWN)
            elif attempt < max_attempts:
                time.sleep(0.2)
        except Exception as e:
            last_err = e
            print(f"[stt] {e} (attempt {attempt}/{max_attempts})", file=sys.stderr)
            if attempt < max_attempts:
                time.sleep(0.5)
    raise NoSpeechError(str(last_err) if last_err else "No speech captured.")


def voice_ask(client: OpenAI, question: str, *, mode: str = "freeform") -> str:
    print(f"\n[voice] {question}")
    interrupted = speak(client, question)
    if not interrupted:
        time.sleep(POST_TTS_COOLDOWN)
    return listen_once(client, mode=mode)


def voice_confirm(
    client: OpenAI,
    question: str,
    *,
    allow_retry: bool = False,
    allow_quit: bool = False,
    default_yes: bool = False,
) -> str:
    """Speak a question, then capture yes/no with a short VAD window."""
    print(f"\n[voice] {question}")
    interrupted = speak(client, question)
    if not interrupted:
        time.sleep(POST_TTS_COOLDOWN)

    attempts = 0
    while True:
        attempts += 1
        try:
            answer = listen_once(
                client,
                mode="confirm",
                max_attempts=2,
                prompt=f"Say yes or no now… (sends after ~{CONFIRM_RECORD_SECONDS:g}s without new words)",
            )
        except NoSpeechError:
            interrupted = speak(client, "Still didn't hear you. Please say yes or no clearly.")
            if not interrupted:
                time.sleep(POST_TTS_COOLDOWN)
            if attempts >= 5:
                return "yes" if default_yes else "no"
            continue

        kind = classify_yes_no(answer)
        if kind == "retry" and not allow_retry:
            kind = None
        if kind == "quit" and not allow_quit:
            kind = None
        if kind is not None:
            print(f"[voice] interpreted as {kind}")
            return kind

        hint = "Please say only yes or no"
        if allow_retry:
            hint += ", or retry"
        if allow_quit:
            hint += ", or quit"
        interrupted = speak(client, f"I heard {answer}. {hint}.")
        if not interrupted:
            time.sleep(POST_TTS_COOLDOWN)

        if attempts >= 6:
            return "yes" if default_yes else "no"


def listen_and_confirm(
    client: OpenAI,
    *,
    listen_prompt: str | None = None,
    confirm_question: str | None = None,
) -> str:
    """Record free-form speech, then confirm with yes/no."""
    while True:
        text = listen_once(client, prompt=listen_prompt, mode="freeform")
        if confirm_question and "{text}" in confirm_question:
            question = confirm_question.format(text=text)
        else:
            question = confirm_question or (f"I heard: {text}. Say yes to continue, or no to cancel.")

        decision = voice_confirm(
            client,
            question,
            allow_retry=True,
            allow_quit=True,
            default_yes=False,
        )
        if decision == "yes":
            return text
        if decision == "retry":
            interrupted = speak(client, "Okay, try again.")
            if not interrupted:
                time.sleep(POST_TTS_COOLDOWN)
            continue
        print("Cancelled.")
        speak(client, "Cancelled.")
        sys.exit(0)


def ask_user(client: OpenAI, question: str) -> str:
    """Speak a question, then capture a free-form spoken answer (no yes/no gate).

    Empty captures return a string the caller can feed back to the model.
    They must not raise — the orchestrator loop would exit.
    """
    print(f"\n[ask_user] {question}")
    interrupted = speak(client, question)
    if not interrupted:
        time.sleep(POST_TTS_COOLDOWN)
    try:
        return listen_once(
            client,
            mode="freeform",
            prompt="Listening for your answer… (sends after 3s without new words)",
        )
    except ListenCancelled:
        print("[ask_user] cancelled", flush=True)
        return "The user cancelled listening. Do not assume an answer."
    except NoSpeechError as e:
        print(f"[ask_user] no speech: {e}", file=sys.stderr)
        return (
            "No speech was captured after several attempts. "
            "Ask again with ask_user if you still need an answer, "
            "or continue without it."
        )


def listen_for_utterance(
    client: OpenAI | None = None,
    *,
    prompt: str | None = None,
    max_wait_for_speech: float | None = None,
) -> str:
    """Listen for the next free-form user utterance (orchestrator idle loop).

    Failures stay quiet — the orchestrator retries without speaking.
    """
    client = client or OpenAI()
    return listen_once(
        client,
        mode="freeform",
        prompt=prompt or f"Listening… (sends after {TRANSCRIPT_IDLE_SECONDS:g}s without new words)",
        max_attempts=1,
        announce_retries=False,
        max_wait_for_speech=max_wait_for_speech,
    )
