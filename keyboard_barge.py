"""Keyboard barge-in during TTS (terminal key → stop speech → listen).

When the orchestrator terminal is focused, pressing a barge key (default:
Space, Esc, or Enter) sets an interrupt event so playback stops. The
orchestrator then uses the same listen-after-barge path as wake-word barge-in.

Requires a TTY (does nothing when stdin is not a terminal). Disable with
``TTS_KEYBOARD_BARGE=0``. Keys: ``TTS_KEYBOARD_BARGE_KEYS=space,esc,enter``.
"""

from __future__ import annotations

import os
import select
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

KEYBOARD_BARGE_DEFAULT = os.environ.get("TTS_KEYBOARD_BARGE", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}


def keyboard_barge_enabled() -> bool:
    raw = os.environ.get("TTS_KEYBOARD_BARGE")
    if raw is None:
        return KEYBOARD_BARGE_DEFAULT
    return raw.strip().lower() not in {"0", "false", "no", "off"}

_KEY_ALIASES: dict[str, frozenset[bytes]] = {
    "space": frozenset({b" "}),
    "esc": frozenset({b"\x1b"}),
    "escape": frozenset({b"\x1b"}),
    "enter": frozenset({b"\n", b"\r"}),
    "return": frozenset({b"\n", b"\r"}),
}


def _parse_keys(raw: str | None) -> frozenset[bytes]:
    text = (raw or "space,esc,enter").strip().lower()
    out: set[bytes] = set()
    for part in text.split(","):
        token = part.strip()
        if not token:
            continue
        if token in _KEY_ALIASES:
            out |= _KEY_ALIASES[token]
        elif len(token) == 1:
            out.add(token.encode("utf-8"))
    return frozenset(out) or frozenset({b" ", b"\x1b", b"\n", b"\r"})


BARGE_KEYS = _parse_keys(os.environ.get("TTS_KEYBOARD_BARGE_KEYS"))

_lock = threading.Lock()
_refcount = 0
_stop = threading.Event()
_thread: threading.Thread | None = None
_kb_event = threading.Event()
_old_term: Any = None


def _stdin_is_tty() -> bool:
    try:
        return bool(sys.stdin and sys.stdin.isatty())
    except Exception:
        return False


def _enter_cbreak() -> None:
    global _old_term
    if not _stdin_is_tty() or sys.platform == "win32":
        return
    try:
        import termios
        import tty

        fd = sys.stdin.fileno()
        _old_term = termios.tcgetattr(fd)
        tty.setcbreak(fd)
    except Exception:
        _old_term = None


def _restore_term() -> None:
    global _old_term
    if _old_term is None:
        return
    try:
        import termios

        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _old_term)
    except Exception:
        pass
    _old_term = None


def _drain_stdin() -> None:
    if not _stdin_is_tty():
        return
    try:
        fd = sys.stdin.fileno()
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                break
            os.read(fd, 1024)
    except Exception:
        pass


def _listener_loop() -> None:
    if not _stdin_is_tty():
        return
    try:
        fd = sys.stdin.fileno()
    except Exception:
        return
    try:
        from tts import tts_print

        tts_print(
            "[tts] keyboard barge-in armed "
            f"(keys={os.environ.get('TTS_KEYBOARD_BARGE_KEYS', 'space,esc,enter')})",
        )
    except Exception:
        pass
    while not _stop.is_set():
        try:
            ready, _, _ = select.select([fd], [], [], 0.05)
            if not ready:
                continue
            data = os.read(fd, 32)
            if not data:
                continue
            # Match any configured single-byte key in the chunk.
            if any(data[i : i + 1] in BARGE_KEYS for i in range(len(data))):
                _kb_event.set()
                try:
                    from tts import tts_print

                    tts_print("[tts] interrupted by keyboard")
                except Exception:
                    pass
                break
        except Exception:
            break


def _ensure_listener_locked() -> None:
    global _thread, _refcount
    _refcount += 1
    if _refcount == 1:
        _stop.clear()
        _kb_event.clear()
        _drain_stdin()
        _enter_cbreak()
        _thread = threading.Thread(target=_listener_loop, name="tts-keyboard-barge", daemon=True)
        _thread.start()


def _release_listener_locked() -> None:
    global _thread, _refcount
    _refcount = max(0, _refcount - 1)
    if _refcount > 0:
        return
    _stop.set()
    t = _thread
    _thread = None
    if t is not None and t.is_alive() and t is not threading.current_thread():
        t.join(timeout=0.5)
    _restore_term()
    _drain_stdin()


def acquire_tts_interrupt(
    *sources: threading.Event | None,
) -> tuple[threading.Event, Callable[[], None]]:
    """
    Return ``(event, release)`` set when any source or a barge key fires.

    Always call ``release()`` when playback finishes (use try/finally).
    Keyboard listening is refcounted across overlapping TTS chunks.
    """
    merged = threading.Event()
    stop = threading.Event()
    active_sources = [s for s in sources if s is not None]

    use_keyboard = keyboard_barge_enabled() and _stdin_is_tty()
    with _lock:
        if use_keyboard:
            _ensure_listener_locked()
        # If a previous chunk already triggered keyboard, propagate immediately.
        if _kb_event.is_set():
            merged.set()

    def bridge() -> None:
        while not stop.is_set():
            if use_keyboard and _kb_event.is_set():
                merged.set()
                return
            for src in active_sources:
                if src.is_set():
                    merged.set()
                    return
            if not active_sources and not use_keyboard:
                return
            time.sleep(0.04)

    bridge_thread = threading.Thread(target=bridge, name="tts-interrupt-bridge", daemon=True)
    bridge_thread.start()

    released = False

    def release() -> None:
        nonlocal released
        if released:
            return
        released = True
        stop.set()
        bridge_thread.join(timeout=0.5)
        if use_keyboard:
            with _lock:
                _release_listener_locked()

    return merged, release
