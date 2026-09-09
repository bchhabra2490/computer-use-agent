"""Persistent Realtime voice session for CLI wake-word mode.

After a wake word, the orchestrator keeps one OpenAI Realtime transcription
socket open: live partials, semantic turn-taking, barge-in while Jarvis is
speaking. The session closes after VOICE_LIVE_IDLE_SECONDS with no speech, or
when the user explicitly ends it (e.g. "stop listening", "go to sleep").
"""
from __future__ import annotations

import os
import queue
import re
import threading
import time
from typing import Callable

from openai import OpenAI

IDLE_SECONDS = float(os.environ.get("VOICE_LIVE_IDLE_SECONDS", "10"))
EAGERNESS = os.environ.get("VOICE_LIVE_EAGERNESS", "medium").strip().lower() or "medium"
# Hold echo-matching after speakers stop — trailing STT often arrives late.
_TTS_ECHO_HOLD = float(os.environ.get("VOICE_LIVE_TTS_ECHO_HOLD", "2.5"))
_SHUT = object()
_ECHO_STOP = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "for",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "this",
        "to",
        "was",
    }
)

_SHUT_PHRASES = frozenset(
    {
        "stop listening",
        "thats all",
        "that is all",
        "thats it",
        "that is it",
        "thats enough",
        "that is enough",
        "go to sleep",
        "go to sleep jarvis",
        "sleep now",
        "were done",
        "we are done",
        "back to sleep",
    }
)


def live_voice_enabled() -> bool:
    return os.environ.get("VOICE_LIVE", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def idle_seconds() -> float:
    return max(2.0, float(os.environ.get("VOICE_LIVE_IDLE_SECONDS", str(IDLE_SECONDS))))


def _normalize(text: str) -> str:
    return re.sub(r"[^\w\s]", "", (text or "").lower()).strip()


def is_live_shutdown(text: str) -> bool:
    return _normalize(text) in _SHUT_PHRASES


def _echo_tokens(text: str) -> list[str]:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower().replace("'", ""))
    return [tok for tok in cleaned.split() if tok]


def _echo_stems(words: set[str]) -> set[str]:
    stems = set(words)
    for word in words:
        if word.endswith("s") and len(word) > 3:
            stems.add(word[:-1])
        else:
            stems.add(word + "s")
    return stems


def looks_like_tts_echo(heard: str, spoken: str) -> bool:
    """True when `heard` is the mic picking up `spoken` (speaker echo)."""
    heard_tokens = _echo_tokens(heard)
    spoken_tokens = _echo_tokens(spoken)
    if not heard_tokens or not spoken_tokens:
        return False
    heard_norm = " ".join(heard_tokens)
    spoken_norm = " ".join(spoken_tokens)
    if heard_norm in spoken_norm:
        return True
    if len(heard_norm) >= 8 and spoken_norm in heard_norm:
        return True
    heard_sig = {tok for tok in heard_tokens if tok not in _ECHO_STOP and len(tok) > 1}
    spoken_sig = _echo_stems(
        {tok for tok in spoken_tokens if tok not in _ECHO_STOP and len(tok) > 1}
    )
    if not heard_sig:
        return heard_norm in spoken_norm
    hits = 0
    for tok in heard_sig:
        if tok in spoken_sig or (tok.endswith("s") and tok[:-1] in spoken_sig):
            hits += 1
    return hits / len(heard_sig) >= 0.6


_active: LiveVoiceSession | None = None
_active_lock = threading.Lock()


def current() -> LiveVoiceSession | None:
    with _active_lock:
        return _active


def interrupt_event() -> threading.Event | None:
    """TTS barge-in source while a live session owns the mic."""
    with _active_lock:
        sess = _active
    if sess is None or not sess.alive:
        return None
    return sess.barge


def note_tts(text: str) -> None:
    """Record text that is about to be spoken so live STT can ignore echo."""
    sess = current()
    if sess is not None and sess.alive:
        sess.note_tts(text)


def on_tts_playback_start() -> None:
    sess = current()
    if sess is not None and sess.alive:
        sess.on_tts_playback_start()


def on_tts_playback_end() -> None:
    sess = current()
    if sess is not None and sess.alive:
        sess.on_tts_playback_end()


class LiveVoiceSession:
    """One Realtime transcription socket reused across voice turns."""

    def __init__(self, client: OpenAI, *, idle: float | None = None):
        self.client = client
        self.idle = idle if idle is not None else idle_seconds()
        self.barge = threading.Event()
        self.alive = False
        self._stop = threading.Event()
        self._utterances: queue.Queue = queue.Queue()
        self._send_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._in_speech = False
        self._idle_anchor = time.monotonic()
        self._partial = ""
        self._tts_text = ""
        self._tts_active = False
        self._tts_until = 0.0
        self._connection = None
        self._cm = None
        self._mic_thread: threading.Thread | None = None
        self._recv_thread: threading.Thread | None = None

    def note_tts(self, text: str) -> None:
        piece = (text or "").strip()
        with self._state_lock:
            if piece:
                self._tts_text = (self._tts_text + " " + piece).strip()[-4000:]
            self._tts_until = time.monotonic() + max(8.0, _TTS_ECHO_HOLD)

    def begin_tts_stream(self) -> None:
        """New spoken reply — drop prior TTS text so echo matching stays current."""
        with self._state_lock:
            self._tts_text = ""
            self._tts_until = time.monotonic() + max(8.0, _TTS_ECHO_HOLD)
        self.barge.clear()

    def _touch_idle(self) -> None:
        self._idle_anchor = time.monotonic()

    def on_tts_playback_start(self) -> None:
        with self._state_lock:
            self._tts_active = True
            self._tts_until = time.monotonic() + max(8.0, _TTS_ECHO_HOLD)

    def on_tts_playback_end(self) -> None:
        with self._state_lock:
            self._tts_active = False
            self._tts_until = time.monotonic() + _TTS_ECHO_HOLD
            self._in_speech = False
            self._touch_idle()
        self._clear_input_buffer()

    def _clear_input_buffer(self) -> None:
        """Drop leftover speaker echo so the next user turn is a clean VAD."""
        try:
            with self._send_lock:
                conn = self._connection
                if conn is None:
                    return
                conn.input_audio_buffer.clear()
        except Exception:
            pass

    def _in_tts_window(self) -> bool:
        with self._state_lock:
            return self._tts_active or time.monotonic() < self._tts_until

    def _spoken_text(self) -> str:
        with self._state_lock:
            return self._tts_text

    def _should_ignore_echo(self, text: str) -> bool:
        spoken = self._spoken_text()
        if not spoken:
            return False
        if not self._in_tts_window():
            return False
        return looks_like_tts_echo(text, spoken)

    def start(self, *, connection=None, capture: bool = True) -> None:
        global _active
        if self.alive:
            return
        from stt import (
            TRANSCRIBE_MODEL,
            _model_supports_turn_detection,
            _noise_reduction_session_value,
        )
        from wake import pause_persistent_wake

        pause_persistent_wake()
        model = (os.environ.get("VOICE_LIVE_STT_MODEL") or "").strip() or TRANSCRIBE_MODEL
        if not _model_supports_turn_detection(model):
            model = "gpt-4o-mini-transcribe"
        eagerness = EAGERNESS if EAGERNESS in {"low", "medium", "high", "auto"} else "medium"
        transcription = {"model": model, "language": "en"}
        session = {
            "type": "transcription",
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": 24_000},
                    "transcription": transcription,
                    "turn_detection": {
                        "type": "semantic_vad",
                        "eagerness": eagerness,
                    },
                }
            },
        }
        nr = _noise_reduction_session_value()
        if nr is not None:
            session["audio"]["input"]["noise_reduction"] = nr
        if connection is None:
            self._cm = self.client.realtime.connect(extra_query={"intent": "transcription"})
            connection = self._cm.__enter__()
        self._connection = connection
        connection.session.update(session=session)
        self.alive = True
        self._idle_anchor = time.monotonic()
        with _active_lock:
            _active = self
        self._recv_thread = threading.Thread(target=self._recv_loop, name="voice-live-recv", daemon=True)
        self._recv_thread.start()
        if capture:
            self._mic_thread = threading.Thread(target=self._mic_loop, name="voice-live-mic", daemon=True)
            self._mic_thread.start()
        print(
            f"[voice] live socket open — speak naturally; "
            f"sleeps after {self.idle:g}s idle or 'stop listening'",
            flush=True,
        )

    def wait_utterance(self, *, should_stop: Callable[[], bool] | None = None) -> str | None:
        """Block until the next user turn, idle timeout, shutdown phrase, or stop."""
        if not self.alive:
            return None
        with self._state_lock:
            # 10s idle starts after Jarvis finishes talking, not during TTS mute.
            if not self._tts_active:
                self._touch_idle()
        while not self._stop.is_set():
            if should_stop is not None:
                try:
                    if should_stop():
                        return None
                except Exception:
                    return None
            try:
                item = self._utterances.get(timeout=0.1)
            except queue.Empty:
                with self._state_lock:
                    speaking = self._in_speech
                    tts_playing = self._tts_active
                    idle_from = self._idle_anchor
                if tts_playing:
                    continue
                if not speaking and (time.monotonic() - idle_from) >= self.idle:
                    print(f"[voice] {self.idle:g}s idle — closing live socket", flush=True)
                    self.close()
                    return None
                continue
            if item is _SHUT:
                return None
            return str(item)
        return None

    def close(self) -> None:
        global _active
        if not self.alive and self._stop.is_set():
            self._finish_close()
            return
        self.alive = False
        self._stop.set()
        self.barge.set()
        try:
            if self._connection is not None:
                self._connection.close()
        except Exception:
            pass
        if self._cm is not None:
            try:
                self._cm.__exit__(None, None, None)
            except Exception:
                pass
            self._cm = None
        for thread in (self._mic_thread, self._recv_thread):
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=1.5)
        self._utterances.put(_SHUT)
        with _active_lock:
            if _active is self:
                _active = None
        try:
            from wake import resume_persistent_wake

            resume_persistent_wake()
        except Exception:
            pass
        print("[voice] live socket closed", flush=True)

    def _finish_close(self) -> None:
        with _active_lock:
            global _active
            if _active is self:
                _active = None

    def _on_event(self, event) -> None:
        from stt import _event_delta, _event_transcript, _event_type, _print_live

        kind = _event_type(event)
        if kind == "input_audio_buffer.speech_started":
            with self._state_lock:
                self._in_speech = True
                self._idle_anchor = time.monotonic()
                self._partial = ""
            # Speaker echo of TTS looks like barge-in. Wait for a transcript
            # that is not the current spoken text before interrupting playback.
            if not self._in_tts_window():
                self.barge.set()
        elif kind == "input_audio_buffer.speech_stopped":
            with self._state_lock:
                self._in_speech = False
                self._idle_anchor = time.monotonic()
            if not self._in_tts_window():
                self.barge.clear()
        elif kind == "conversation.item.input_audio_transcription.delta":
            piece = _event_delta(event)
            if not piece:
                return
            with self._state_lock:
                self._partial += piece
                self._idle_anchor = time.monotonic()
                live = self._partial
            if self._should_ignore_echo(live):
                return
            _print_live(live)
        elif kind == "conversation.item.input_audio_transcription.completed":
            with self._state_lock:
                fallback = self._partial.strip()
                self._partial = ""
                self._in_speech = False
                self._idle_anchor = time.monotonic()
            text = (_event_transcript(event) or fallback).strip()
            if not text:
                self.barge.clear()
                return
            if self._should_ignore_echo(text):
                print(f"\n[voice] ignoring TTS echo: {text}", flush=True)
                self.barge.clear()
                return
            print(f"\n[voice] {text}", flush=True)
            if is_live_shutdown(text):
                print("[voice] shutdown phrase — closing live socket", flush=True)
                self._utterances.put(_SHUT)
                self.close()
                return
            if self._in_tts_window():
                self.barge.set()
            else:
                self.barge.clear()
            self._utterances.put(text)
        elif kind == "error":
            err = getattr(event, "error", None) or event
            print(f"[voice] realtime error: {err}", flush=True)

    def _recv_loop(self) -> None:
        try:
            for event in self._connection:
                if self._stop.is_set():
                    break
                self._on_event(event)
        except Exception:
            if not self._stop.is_set():
                self._stop.set()
                self.alive = False

    def _mic_loop(self) -> None:
        from stt import (
            CHUNK_SECONDS,
            FAN_HIGHPASS_HZ,
            FanNoiseFilter,
            NORMALIZE_PEAK,
            REALTIME_RATE,
            _capture_sample_rate,
            _cue_listen_start,
            _float_to_pcm16_b64,
            _log_mic_settings,
            _open_input_stream,
            _peak,
            _prepare_mic,
            _resample,
        )

        try:
            _prepare_mic()
            capture_rate = _capture_sample_rate()
            _log_mic_settings(capture_rate)
            chunk_frames = max(1, int(CHUNK_SECONDS * capture_rate))
            noise = FanNoiseFilter(capture_rate, FAN_HIGHPASS_HZ)
            with _open_input_stream(capture_rate, chunk_frames) as stream:
                _cue_listen_start()
                while not self._stop.is_set():
                    data, overflowed = stream.read(chunk_frames)
                    if overflowed:
                        pass
                    import numpy as np

                    raw = np.asarray(data, dtype=np.float32).reshape(-1)
                    cleaned = noise.process(raw)
                    pcm = _resample(cleaned, capture_rate, REALTIME_RATE)
                    if pcm.size == 0:
                        continue
                    with self._state_lock:
                        mute_tts = self._tts_active
                    if mute_tts:
                        # Laptop speakers bleed into the mic. Don't send that
                        # echo to Realtime or TTS barge-in loops on itself.
                        continue
                    peak = _peak(pcm)
                    if peak > 1e-4:
                        pcm = np.clip(pcm * min(NORMALIZE_PEAK / peak, 4.0), -1.0, 1.0)
                    b64 = _float_to_pcm16_b64(pcm)
                    with self._send_lock:
                        if self._stop.is_set() or self._connection is None:
                            break
                        self._connection.input_audio_buffer.append(audio=b64)
        except Exception as exc:
            if not self._stop.is_set():
                print(f"[voice] mic capture failed: {exc}", flush=True)
                self.close()
