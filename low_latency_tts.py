"""Non-blocking, chunked TTS pipeline used by the voice orchestrator.

Public API on :class:`LowLatencyTTS`:
  - ``start_stream(response_id)``
  - ``add_text_chunk(chunk)``
  - ``stop_stream()``

The Responses API emits tool-call JSON a few characters at a time. The
orchestrator decodes the growing ``message`` string from
``give_response_to_user`` and feeds plaintext via ``add_text_chunk``. Separate
synthesis and playback workers overlap cloud TTS with audio playback.

Playback goes through :func:`tts.play_wav` (afplay on macOS by default) so we do
not open a PortAudio output stream during speech — that path caused speaker hiss
in this project. Set ``TTS_PLAYER=sounddevice`` only if you accept that trade-off.

When ``TTS_BARGE_IN`` is on (default), playback shares the process-wide
persistent wake monitor so ``Hey Jarvis`` can interrupt at any time.
Keyboard barge-in (Space / Esc / Enter in the terminal) is also on by default
(``TTS_KEYBOARD_BARGE``); both feed the same interrupt → listen path.

Latency markers (``chunk_available``, ``first_audio_play``) are appended to
``tts_latency.log`` in the project root.
"""

from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openai import OpenAI

from tts import (
    BARGE_IN_DEFAULT,
    TTS_VOICE,
    active_tts_voice,
    concat_wavs,
    play_wav,
    synthesize,
)

# Prefer fewer, longer chunks: each Sarvam/OpenAI synth call pays RTT.
# Sentence boundaries first; commas only when a chunk is already long.
_MIN_CHARS = int(os.environ.get("TTS_CHUNK_MIN_CHARS", "40"))
_MAX_CHARS = int(os.environ.get("TTS_CHUNK_MAX_CHARS", "220"))
# Soft floor before allowing comma/semicolon cuts (avoids "Safety notes," spam).
_COMMA_MIN_CHARS = int(os.environ.get("TTS_CHUNK_COMMA_MIN_CHARS", "120"))
_WARMUP = os.environ.get("TTS_WARMUP", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
_STOP = object()
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
_CLAUSE_BREAK = re.compile(r"(?<=[,;:])\s+")


def _timestamp() -> str:
    return (
        time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
        + f".{int(time.time_ns() % 1_000_000_000):09d}"
    )


def decoded_message_prefix(arguments: str) -> str:
    """Decode the valid prefix of a possibly incomplete JSON ``message`` value."""
    match = re.search(r'"message"\s*:\s*"', arguments or "")
    if not match:
        return ""
    raw = arguments[match.end() :]
    out: list[str] = []
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == '"':
            break
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        if i + 1 >= len(raw):
            break
        esc = raw[i + 1]
        simple = {
            '"': '"',
            "\\": "\\",
            "/": "/",
            "b": "\b",
            "f": "\f",
            "n": "\n",
            "r": "\r",
            "t": "\t",
        }
        if esc in simple:
            out.append(simple[esc])
            i += 2
        elif esc == "u" and i + 6 <= len(raw):
            try:
                out.append(chr(int(raw[i + 2 : i + 6], 16)))
                i += 6
            except ValueError:
                break
        else:
            break
    return "".join(out)


def extract_message_field(arguments: str) -> str:
    """Best-effort final ``message`` from complete or nearly-complete tool JSON."""
    text = (arguments or "").strip()
    if not text:
        return ""
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return str(data.get("message") or "").strip()
    except json.JSONDecodeError:
        pass
    return decoded_message_prefix(text).strip()


@dataclass
class _Session:
    response_id: str
    text: str = ""
    emitted: int = 0
    pending: str = ""
    first_audio_at: float | None = None
    first_audio_wall: str | None = None
    first_chunk_at: float | None = None
    first_chunk_wall: str | None = None
    response_ready_at: float | None = None
    response_ready_wall: str | None = None
    done: threading.Event = field(default_factory=threading.Event)
    interrupted: bool = False
    outstanding: int = 0
    final_seen: bool = False
    call_ids: set[str] = field(default_factory=set)
    phone_chunks: list[bytes] = field(default_factory=list)


class LowLatencyTTS:
    """Thread-safe two-stage (synthesis → playback) streaming TTS pipeline."""

    def __init__(self, client: OpenAI, project_root: str | Path | None = None):
        self.client = client
        root = Path(project_root) if project_root else Path(__file__).resolve().parent
        self.log_path = root / "tts_latency.log"
        # Unbounded queues avoid shutdown deadlocks when both stages back up.
        self._synth_q: queue.Queue[Any] = queue.Queue()
        self._audio_q: queue.Queue[Any] = queue.Queue()
        self._lock = threading.Lock()
        self._sessions: dict[str, _Session] = {}
        self._call_to_response: dict[str, str] = {}
        self._streamed_calls: set[str] = set()
        self._active_response_id: str | None = None
        self._closed = False
        self._synth_thread = threading.Thread(
            target=self._synth_worker, name="tts-synthesis", daemon=True
        )
        self._play_thread = threading.Thread(
            target=self._play_worker, name="tts-playback", daemon=True
        )
        self._synth_thread.start()
        self._play_thread.start()
        self._barge_in = BARGE_IN_DEFAULT
        self._log(
            "engine_initialized",
            detail=(
                f"warmup={int(_WARMUP)} min_chars={_MIN_CHARS} max_chars={_MAX_CHARS} "
                f"barge_in={int(self._barge_in)}"
            ),
        )
        if _WARMUP:
            threading.Thread(target=self._warm, name="tts-warmup", daemon=True).start()

    def _wake_interrupt_event(self):
        """Reuse the process-wide persistent wake monitor (never stop it here)."""
        if not self._barge_in:
            return None
        try:
            from wake import ensure_persistent_wake

            monitor = ensure_persistent_wake()
            return None if monitor is None else monitor.woken
        except Exception as exc:
            self._log("barge_in_unavailable", detail=repr(exc))
            return None

    def _acquire_interrupt(self):
        """Wake and/or keyboard interrupt event + release callback."""
        wake_event = self._wake_interrupt_event()
        try:
            from keyboard_barge import acquire_tts_interrupt

            return acquire_tts_interrupt(wake_event)
        except Exception as exc:
            self._log("keyboard_barge_unavailable", detail=repr(exc))
            if wake_event is None:
                return None, (lambda: None)
            return wake_event, (lambda: None)

    def _interrupt_session(self, response_id: str) -> None:
        """Stop remaining synthesis/playback after a wake-word barge-in."""
        with self._lock:
            session = self._sessions.get(response_id)
            if session is None:
                return
            session.interrupted = True
            session.final_seen = True
            session.pending = ""
            if session.outstanding == 0:
                session.done.set()
            if self._active_response_id == response_id:
                self._active_response_id = None
        self._log("response_interrupted", response_id=response_id)

    def _log(self, event: str, *, response_id: str = "-", detail: str = "") -> None:
        line = (
            f"{_timestamp()} monotonic={time.monotonic():.6f} "
            f"response={response_id} event={event}"
        )
        if detail:
            line += f" detail={detail}"
        print(f"[tts-latency] {line}", flush=True)
        try:
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError as exc:
            print(f"[tts-latency] log write failed: {exc}", flush=True)

    def _warm(self) -> None:
        started = time.monotonic()
        try:
            # Primes DNS/TLS/HTTP and provider-side model before the first reply.
            synthesize(self.client, "Ready.", voice=TTS_VOICE)  # warmup: default voice
            self._log(
                "engine_warm",
                detail=f"seconds={time.monotonic() - started:.3f}",
            )
        except Exception as exc:  # warmup must never prevent startup
            self._log("engine_warm_failed", detail=repr(exc))

    def start_stream(self, response_id: str) -> None:
        """Begin a streaming TTS session for ``response_id`` (public API)."""
        response_id = (response_id or "").strip()
        if not response_id:
            return
        with self._lock:
            if self._closed:
                return
            self._sessions[response_id] = _Session(response_id=response_id)
            self._active_response_id = response_id
        self._log("response_stream_started", response_id=response_id)

    def add_text_chunk(self, chunk: str) -> None:
        """Append plaintext to the active stream and queue speakable clauses."""
        piece = chunk or ""
        if not piece:
            return
        with self._lock:
            response_id = self._active_response_id
            if not response_id or self._closed:
                return
            session = self._sessions.get(response_id)
            if session is None or session.interrupted or session.final_seen:
                return
            session.text += piece
            session.emitted = len(session.text)
            session.pending += piece
            chunks = self._take_chunks(session, final=False)
        for speakable in chunks:
            self._queue_chunk(response_id, speakable)

    def stop_stream(self) -> None:
        """Finalize the active stream: flush remaining text into the synth queue."""
        wall = _timestamp()
        mono = time.monotonic()
        with self._lock:
            response_id = self._active_response_id
            if not response_id:
                return
            session = self._sessions.get(response_id)
            if session is None or session.interrupted:
                self._active_response_id = None
                return
            session.response_ready_at = mono
            session.response_ready_wall = wall
            session.final_seen = True
            chunks = self._take_chunks(session, final=True)
            text_len = len(session.text)
            first_audio = session.first_audio_at
            first_wall = session.first_audio_wall
            if text_len > 0 or chunks or session.outstanding > 0:
                for call_id in session.call_ids:
                    self._streamed_calls.add(call_id)
            no_work = session.outstanding == 0 and not chunks
            if no_work:
                session.done.set()
            self._active_response_id = None
        detail = f"wall={wall} chars={text_len}"
        if first_audio is not None:
            detail += (
                f" first_audio_wall={first_wall} "
                f"delta_seconds={first_audio - mono:.3f}"
            )
        self._log("response_ready", response_id=response_id, detail=detail)
        for speakable in chunks:
            self._queue_chunk(response_id, speakable)

    def bind_call(self, response_id: str, call_id: str) -> None:
        """Associate a function call_id with a streaming response (idempotent)."""
        call_id = (call_id or "").strip()
        if not call_id:
            return
        with self._lock:
            session = self._sessions.get(response_id)
            if session is None:
                return
            session.call_ids.add(call_id)
            self._call_to_response[call_id] = response_id

    def abandon(self, response_id: str) -> None:
        """Cancel a stream without speaking remaining text (e.g. stream fallback)."""
        with self._lock:
            session = self._sessions.get(response_id)
            if session is None:
                return
            session.interrupted = True
            session.final_seen = True
            session.pending = ""
            for call_id in list(session.call_ids):
                # Allow the sync fallback path to speak this call_id.
                self._streamed_calls.discard(call_id)
            if session.outstanding == 0:
                session.done.set()
            if self._active_response_id == response_id:
                self._active_response_id = None
        self._log("response_abandoned", response_id=response_id)

    def _take_chunks(self, session: _Session, *, final: bool) -> list[str]:
        chunks: list[str] = []
        text = session.pending
        while text:
            cut = -1
            if len(text) >= _MIN_CHARS:
                window = text[:_MAX_CHARS]
                # Prefer end of sentence so we don't pay one synth RTT per comma.
                sentence = list(_SENTENCE_BREAK.finditer(window))
                if sentence:
                    cut = sentence[-1].end()
                elif len(window) >= _COMMA_MIN_CHARS:
                    clause = list(_CLAUSE_BREAK.finditer(window))
                    if clause:
                        cut = clause[-1].end()
                if cut < 0 and len(text) >= _MAX_CHARS:
                    space = window.rfind(" ")
                    cut = space + 1 if space >= _MIN_CHARS else _MAX_CHARS
            if cut < 0:
                if final:
                    cut = len(text)
                else:
                    break
            chunk, text = text[:cut].strip(), text[cut:]
            if chunk:
                chunks.append(chunk)
        session.pending = text
        return chunks

    def _queue_chunk(self, response_id: str, text: str) -> None:
        # Increment under lock, then put WITHOUT holding the lock so a full
        # (or slow) queue cannot deadlock against workers that need the lock.
        wall = _timestamp()
        mono = time.monotonic()
        first_chunk = False
        with self._lock:
            session = self._sessions.get(response_id)
            if session is None or session.interrupted or self._closed:
                return
            session.outstanding += 1
            for call_id in session.call_ids:
                self._streamed_calls.add(call_id)
            if session.first_chunk_at is None:
                session.first_chunk_at = mono
                session.first_chunk_wall = wall
                first_chunk = True
        detail = f"wall={wall} text={json.dumps(text, ensure_ascii=False)}"
        if first_chunk:
            detail += " first=1"
        self._log("chunk_available", response_id=response_id, detail=detail)
        try:
            self._synth_q.put((response_id, text))
        except Exception:
            self._complete_chunk(response_id)

    def _session_skippable(self, response_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(response_id)
            return session is None or session.interrupted or self._closed

    def _synth_worker(self) -> None:
        while True:
            item = self._synth_q.get()
            try:
                if item is _STOP:
                    return
                response_id, text = item
                if self._session_skippable(response_id):
                    self._complete_chunk(response_id)
                    continue
                try:
                    started = time.monotonic()
                    audio = synthesize(self.client, text, voice=active_tts_voice())
                    self._log(
                        "audio_chunk_ready",
                        response_id=response_id,
                        detail=(
                            f"bytes={len(audio)} "
                            f"synth_seconds={time.monotonic() - started:.3f}"
                        ),
                    )
                    if self._session_skippable(response_id):
                        self._complete_chunk(response_id)
                        continue
                    self._audio_q.put((response_id, audio, text))
                except Exception as exc:
                    self._log(
                        "synthesis_error",
                        response_id=response_id,
                        detail=repr(exc),
                    )
                    self._complete_chunk(response_id)
            finally:
                self._synth_q.task_done()

    def _play_worker(self) -> None:
        while True:
            item = self._audio_q.get()
            try:
                if item is _STOP:
                    return
                response_id, audio, text = item
                if self._session_skippable(response_id):
                    self._complete_chunk(response_id)
                    continue
                first = False
                ready_at = None
                first_at = None
                ready_wall = None
                chunk_at = None
                chunk_wall = None
                try:
                    with self._lock:
                        session = self._sessions.get(response_id)
                        if session is not None and session.first_audio_at is None:
                            first = True
                            session.first_audio_at = time.monotonic()
                            session.first_audio_wall = _timestamp()
                            first_at = session.first_audio_at
                            ready_at = session.response_ready_at
                            ready_wall = session.response_ready_wall
                            chunk_at = session.first_chunk_at
                            chunk_wall = session.first_chunk_wall
                    if first:
                        detail = f"wall={_timestamp()}"
                        if chunk_at is not None and first_at is not None:
                            detail += (
                                f" chunk_available_wall={chunk_wall} "
                                f"delta_from_chunk_seconds={first_at - chunk_at:.3f}"
                            )
                        if ready_at is not None and first_at is not None:
                            detail += (
                                f" response_ready_wall={ready_wall} "
                                f"delta_from_ready_seconds={first_at - ready_at:.3f}"
                            )
                        self._log(
                            "first_audio_play",
                            response_id=response_id,
                            detail=detail,
                        )
                    print(f"[tts] {text}", flush=True)
                    try:
                        from app_status import reply_sink

                        phone = reply_sink() == "phone"
                    except Exception:
                        phone = False
                    if phone:
                        with self._lock:
                            session = self._sessions.get(response_id)
                            if session is not None:
                                session.phone_chunks.append(audio)
                        continue
                    interrupt_event, release = self._acquire_interrupt()
                    try:
                        # afplay / configured player — avoid PortAudio TTS by default.
                        interrupted = bool(
                            play_wav(audio, interrupt_event=interrupt_event)
                            or (interrupt_event is not None and interrupt_event.is_set())
                        )
                        if interrupted:
                            print("[tts] streaming interrupted", flush=True)
                            self._interrupt_session(response_id)
                    finally:
                        release()
                except Exception as exc:
                    self._log(
                        "playback_error",
                        response_id=response_id,
                        detail=repr(exc),
                    )
                finally:
                    self._complete_chunk(response_id)
            finally:
                self._audio_q.task_done()

    def _complete_chunk(self, response_id: str) -> None:
        chunks: list[bytes] = []
        with self._lock:
            session = self._sessions.get(response_id)
            if session is None:
                return
            session.outstanding = max(0, session.outstanding - 1)
            if session.final_seen and session.outstanding == 0:
                chunks = list(session.phone_chunks)
                session.phone_chunks.clear()
                session.done.set()
        if chunks:
            try:
                from app_status import reply_sink, write_phone_speech

                if reply_sink() == "phone":
                    write_phone_speech(concat_wavs(chunks))
            except Exception as exc:
                self._log(
                    "phone_speech_error",
                    response_id=response_id,
                    detail=repr(exc),
                )
    def wait(self, response_id: str, timeout: float | None = None) -> bool:
        with self._lock:
            session = self._sessions.get(response_id)
        if session is None:
            return False
        finished = session.done.wait(timeout)
        if finished:
            self._cleanup_session(response_id)
        return session.interrupted

    def wait_call(self, call_id: str, timeout: float | None = None) -> bool:
        with self._lock:
            response_id = self._call_to_response.get(call_id)
        if not response_id:
            return False
        return self.wait(response_id, timeout=timeout)

    def took_call(self, call_id: str) -> bool:
        with self._lock:
            return call_id in self._streamed_calls

    def has_session(self, response_id: str) -> bool:
        with self._lock:
            return response_id in self._sessions

    def _cleanup_session(self, response_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(response_id, None)
            if session is None:
                return
            for call_id in list(session.call_ids):
                self._call_to_response.pop(call_id, None)
                # Keep _streamed_calls until tool handler checks took_call once.
                # Cleared explicitly via acknowledge_call.

    def acknowledge_call(self, call_id: str) -> None:
        """Drop streamed-call bookkeeping after the tool handler has consumed it."""
        with self._lock:
            self._streamed_calls.discard(call_id)
            self._call_to_response.pop(call_id, None)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for session in self._sessions.values():
                session.interrupted = True
                session.final_seen = True
                session.done.set()
            self._active_response_id = None
        # STOP after any already-queued work; workers skip interrupted sessions.
        self._synth_q.put(_STOP)
        self._synth_thread.join(timeout=30.0)
        self._audio_q.put(_STOP)
        self._play_thread.join(timeout=60.0)
        self._log("engine_closed")
