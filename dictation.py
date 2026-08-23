"""Fn-key dictation: speak into the focused field via OpenAI Realtime STT.

Press Fn alone (no other modifiers) while a text field is focused. The mic
opens, Realtime transcription runs, and partial text is pasted as you speak.
The face overlay switches to listen mode while the mic is open (``stt_active``).

Modes (DICTATION_MODE):
  tap  — Fn press starts; ends after silence / Esc / over-and-out (default)
  hold — hold Fn while speaking; release to send

Requires Accessibility (and usually Input Monitoring) for the event tap.
Start with the orchestrator when DICTATION=1, or: ``cua dictation start``.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / ".runtime"
PID_PATH = RUNTIME_DIR / "dictation.pid"
LOG_PATH = ROOT / "logs" / "dictation.log"

_OFF = {"0", "false", "no", "off"}

DICTATION_ENABLED = os.environ.get("DICTATION", "1").strip().lower() not in _OFF
DICTATION_MODE = (os.environ.get("DICTATION_MODE") or "tap").strip().lower()
DICTATION_IDLE = float(os.environ.get("DICTATION_IDLE_SECONDS", "2.0"))
DICTATION_SWALLOW = os.environ.get("DICTATION_SWALLOW", "1").strip().lower() not in _OFF
DICTATION_REQUIRE_EDITABLE = (
    os.environ.get("DICTATION_REQUIRE_EDITABLE", "0").strip().lower() not in _OFF
)
# Ignore Fn edges this long after a session (debounce + avoid key-repeat noise).
DICTATION_COOLDOWN = float(os.environ.get("DICTATION_COOLDOWN", "0.45"))
# Batch rapid STT deltas before paste (seconds).
DICTATION_PASTE_DEBOUNCE = float(os.environ.get("DICTATION_PASTE_DEBOUNCE", "0.08"))


def dictation_enabled() -> bool:
    if sys.platform != "darwin":
        return False
    return DICTATION_ENABLED


def _python() -> str:
    venv = ROOT / ".venv" / "bin" / "python"
    if venv.is_file():
        return str(venv)
    return sys.executable


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def running_pid() -> int | None:
    try:
        raw = PID_PATH.read_text(encoding="utf-8").strip()
        pid = int(raw)
    except (OSError, ValueError):
        return None
    if _pid_alive(pid):
        return pid
    try:
        PID_PATH.unlink(missing_ok=True)
    except OSError:
        pass
    return None


def ensure_dictation_running() -> subprocess.Popen | None:
    """Spawn the dictation daemon if DICTATION=1 and not already running."""
    if not dictation_enabled():
        return None
    if running_pid() is not None:
        return None
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("PYTHONPATH", str(ROOT))
    log_fh = open(LOG_PATH, "a", encoding="utf-8")
    try:
        log_fh.write(f"\n--- dictation start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        log_fh.flush()
        proc = subprocess.Popen(
            [_python(), str(ROOT / "dictation.py")],
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )
    finally:
        log_fh.close()
    time.sleep(0.35)
    if proc.poll() is not None:
        print(
            f"[dictation] failed to start (exit {proc.returncode}). See {LOG_PATH}",
            flush=True,
        )
        return None
    PID_PATH.write_text(f"{proc.pid}\n", encoding="utf-8")
    print(f"[dictation] started (pid={proc.pid}) — Fn alone to dictate", flush=True)
    return proc


def stop_dictation() -> None:
    pid = running_pid()
    if pid is None:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline and _pid_alive(pid):
        time.sleep(0.1)
    if _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    try:
        PID_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def cmd_start() -> int:
    if not dictation_enabled():
        print("dictation disabled (DICTATION=0 or not macOS)")
        return 0
    pid = running_pid()
    if pid is not None:
        print(f"dictation is already running (pid {pid})")
        return 0
    proc = ensure_dictation_running()
    if proc is None:
        # ensure may have raced; check again
        pid = running_pid()
        if pid is not None:
            print(f"dictation is already running (pid {pid})")
            return 0
        return 1
    print(f"logs: {LOG_PATH}")
    return 0


def cmd_stop() -> int:
    pid = running_pid()
    if pid is None:
        print("dictation is not running")
        return 0
    stop_dictation()
    print("dictation stopped")
    return 0


def cmd_status() -> int:
    pid = running_pid()
    if pid is None:
        print("dictation: stopped")
        return 1
    print(f"dictation: running (pid {pid})")
    print(f"mode={DICTATION_MODE} idle={DICTATION_IDLE:g}s swallow={int(DICTATION_SWALLOW)}")
    return 0


def _fn_alone(flags: int, *, secondary_fn: int, other_mods: int) -> bool:
    return bool(flags & secondary_fn) and not bool(flags & other_mods)


def _keystroke_v() -> None:
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "System Events" to keystroke "v" using command down',
        ],
        check=False,
        timeout=5,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _backspace_n(n: int) -> None:
    n = max(0, int(n))
    if n <= 0:
        return
    # Batch deletes in AppleScript to avoid one osascript spawn per char.
    chunk = 40
    while n > 0:
        k = min(chunk, n)
        subprocess.run(
            [
                "osascript",
                "-e",
                f'tell application "System Events" to repeat {k} times\n'
                f"key code 51\n"
                f"end repeat",
            ],
            check=False,
            timeout=max(5.0, k * 0.05 + 2.0),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        n -= k


def paste_dictation(text: str) -> None:
    """Paste into the focused field, restoring the previous clipboard."""
    blob = (text or "").strip()
    if not blob:
        return
    old = b""
    try:
        old = subprocess.check_output(["pbpaste"], stderr=subprocess.DEVNULL)
    except Exception:
        old = b""
    try:
        subprocess.run(["pbcopy"], input=blob.encode("utf-8"), check=True)
        _keystroke_v()
        time.sleep(0.05)
    finally:
        try:
            subprocess.run(["pbcopy"], input=old, check=False)
        except Exception:
            pass


class LiveDictationPaster:
    """Paste growing STT partials; revise via AX or backspace when text changes."""

    def __init__(self, *, debounce_s: float | None = None) -> None:
        self._lock = threading.Lock()
        self._inserted = ""
        self._pending: str | None = None
        self._timer: threading.Timer | None = None
        self._debounce = (
            DICTATION_PASTE_DEBOUNCE if debounce_s is None else float(debounce_s)
        )
        self._old_clip: bytes | None = None
        self._closed = False

    def on_partial(self, live: str) -> None:
        text = live or ""
        with self._lock:
            if self._closed:
                return
            self._pending = text
            if self._timer is not None:
                return
            delay = max(0.0, self._debounce)
            t = threading.Timer(delay, self._flush_timer)
            t.daemon = True
            self._timer = t
            t.start()

    def _flush_timer(self) -> None:
        with self._lock:
            self._timer = None
            pending = self._pending
            self._pending = None
            closed = self._closed
        if closed or pending is None:
            return
        self._apply(pending)

    def finalize(self, final: str) -> None:
        """Sync to the final transcript and restore the clipboard."""
        text = (final or "").strip()
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._pending = None
        self._apply(text)
        self._restore_clip()

    def discard(self) -> None:
        """Remove anything we inserted (cancel) and restore the clipboard."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._pending = None
            self._closed = True
            prev = self._inserted
            self._inserted = ""
        if prev:
            if not self._ax_replace(prev, ""):
                _backspace_n(len(prev))
        self._restore_clip()

    def _ensure_clip(self) -> None:
        if self._old_clip is not None:
            return
        try:
            self._old_clip = subprocess.check_output(
                ["pbpaste"], stderr=subprocess.DEVNULL
            )
        except Exception:
            self._old_clip = b""

    def _restore_clip(self) -> None:
        old = self._old_clip
        self._old_clip = None
        if old is None:
            return
        try:
            subprocess.run(["pbcopy"], input=old, check=False)
        except Exception:
            pass

    def _paste_chunk(self, chunk: str) -> None:
        if not chunk:
            return
        self._ensure_clip()
        subprocess.run(["pbcopy"], input=chunk.encode("utf-8"), check=True)
        _keystroke_v()
        time.sleep(0.02)

    def _ax_replace(self, old: str, new: str) -> bool:
        try:
            from accessibility import replace_focused_inserted_tail

            return bool(replace_focused_inserted_tail(old, new))
        except Exception:
            return False

    def _apply(self, live: str) -> None:
        with self._lock:
            if self._closed and live:
                return
            prev = self._inserted
            if live == prev:
                return
            self._inserted = live
        if live.startswith(prev):
            delta = live[len(prev) :]
            if delta:
                self._paste_chunk(delta)
            return
        if self._ax_replace(prev, live):
            return
        if prev:
            _backspace_n(len(prev))
        if live:
            self._paste_chunk(live)


class DictationDaemon:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._busy = threading.Lock()
        self._session = threading.Event()
        self._fn_down = False
        self._last_edge = 0.0
        self._hold_send = threading.Event()

    def stop(self) -> None:
        self._stop.set()
        self._hold_send.set()
        try:
            from app_status import request_cancel

            request_cancel()
        except Exception:
            pass

    def _can_start(self) -> tuple[bool, str]:
        try:
            from app_status import read_status

            data = read_status()
            if data.get("stt_active"):
                return False, "orchestrator already listening"
        except Exception:
            pass
        try:
            from accessibility import focused_edit_info

            info = focused_edit_info()
        except Exception as e:
            if DICTATION_REQUIRE_EDITABLE:
                return False, f"accessibility unavailable ({e})"
            return True, "no AX (continuing)"
        if info.get("secure"):
            return False, "password field — skipped"
        if DICTATION_REQUIRE_EDITABLE and not info.get("editable"):
            role = info.get("role") or "unknown"
            return False, f"focus is not editable ({role})"
        return True, info.get("role") or "ok"

    def _run_session(self, *, hold: bool) -> None:
        if not self._busy.acquire(blocking=False):
            print("[dictation] already recording", flush=True)
            return
        self._session.set()
        self._hold_send.clear()
        paster = LiveDictationPaster()
        prev_status: dict | None = None
        try:
            ok, why = self._can_start()
            if not ok:
                print(f"[dictation] skip: {why}", flush=True)
                return
            print(f"[dictation] listening… ({why})", flush=True)
            try:
                from app_status import read_status, set_state

                prev_status = dict(read_status())
                set_state("listening", "Dictation…")
            except Exception:
                prev_status = None
            try:
                from wake import pause_persistent_wake, play_listen_start_chime

                pause_persistent_wake()
                play_listen_start_chime(blocking=False)
            except Exception:
                pass

            # Prefer a shorter idle than the voice orchestrator.
            prev_idle = os.environ.get("STT_IDLE_SECONDS")
            os.environ["STT_IDLE_SECONDS"] = str(DICTATION_IDLE)
            try:
                from openai import OpenAI

                from stt import ListenCancelled, NoSpeechError, listen_once

                client = OpenAI()
                if hold:
                    # Background: watch for Fn release → Send.
                    def _hold_watch() -> None:
                        while self._session.is_set() and not self._stop.is_set():
                            if self._hold_send.is_set() or not self._fn_down:
                                try:
                                    from app_status import request_send

                                    request_send()
                                except Exception:
                                    pass
                                return
                            time.sleep(0.05)

                    threading.Thread(
                        target=_hold_watch, name="dictation-hold", daemon=True
                    ).start()

                text = listen_once(
                    client,
                    prompt="Dictation… (speak, then pause; Esc cancels)",
                    mode="freeform",
                    max_attempts=1,
                    announce_retries=False,
                    max_wait_for_speech=12.0,
                    on_partial=paster.on_partial,
                )
            except ListenCancelled:
                print("[dictation] cancelled", flush=True)
                paster.discard()
                return
            except NoSpeechError as e:
                print(f"[dictation] no speech ({e})", flush=True)
                paster.discard()
                return
            except Exception as e:
                print(f"[dictation] STT failed: {e}", flush=True)
                paster.discard()
                return
            finally:
                if prev_idle is None:
                    os.environ.pop("STT_IDLE_SECONDS", None)
                else:
                    os.environ["STT_IDLE_SECONDS"] = prev_idle
                try:
                    from wake import resume_persistent_wake

                    resume_persistent_wake()
                except Exception:
                    pass

            text = (text or "").strip()
            if not text:
                print("[dictation] empty transcript", flush=True)
                paster.discard()
                return
            print(
                f'[dictation] live paste done: '
                f'"{text[:120]}{"…" if len(text) > 120 else ""}"',
                flush=True,
            )
            paster.finalize(text)
            try:
                from wake import play_listen_end_chime

                play_listen_end_chime()
            except Exception:
                pass
        finally:
            if prev_status is not None:
                try:
                    from app_status import set_state

                    set_state(
                        str(prev_status.get("state") or "waiting"),
                        str(prev_status.get("detail") or ""),
                    )
                except Exception:
                    pass
            self._session.clear()
            self._busy.release()

    def on_fn_edge(self, *, down: bool) -> bool:
        """Handle Fn alone edge. Returns True if the event should be swallowed."""
        now = time.monotonic()
        if down:
            if now - self._last_edge < DICTATION_COOLDOWN and not self._session.is_set():
                return False
            self._last_edge = now
            self._fn_down = True
            if self._session.is_set():
                # Second Fn while recording → cancel.
                try:
                    from app_status import request_cancel

                    request_cancel()
                except Exception:
                    pass
                print("[dictation] Fn again — cancel", flush=True)
                return DICTATION_SWALLOW
            if DICTATION_MODE == "hold":
                threading.Thread(
                    target=self._run_session,
                    kwargs={"hold": True},
                    name="dictation-session",
                    daemon=True,
                ).start()
                return DICTATION_SWALLOW
            # tap
            threading.Thread(
                target=self._run_session,
                kwargs={"hold": False},
                name="dictation-session",
                daemon=True,
            ).start()
            return DICTATION_SWALLOW

        # Fn up
        was = self._fn_down
        self._fn_down = False
        if was and DICTATION_MODE == "hold" and self._session.is_set():
            self._hold_send.set()
            return DICTATION_SWALLOW
        return False


def _install_fn_tap(daemon: DictationDaemon) -> bool:
    try:
        from Quartz import (
            CFMachPortCreateRunLoopSource,
            CFRunLoopAddSource,
            CFRunLoopGetCurrent,
            CGEventGetFlags,
            CGEventMaskBit,
            CGEventTapCreate,
            CGEventTapEnable,
            kCFRunLoopCommonModes,
            kCGEventFlagsChanged,
            kCGEventFlagMaskAlternate,
            kCGEventFlagMaskCommand,
            kCGEventFlagMaskControl,
            kCGEventFlagMaskSecondaryFn,
            kCGEventFlagMaskShift,
            kCGEventTapOptionDefault,
            kCGEventTapOptionListenOnly,
            kCGHeadInsertEventTap,
            kCGSessionEventTap,
        )
    except Exception as e:
        print(f"[dictation] Quartz unavailable ({e})", flush=True)
        return False

    secondary = int(kCGEventFlagMaskSecondaryFn)
    other = int(
        kCGEventFlagMaskShift
        | kCGEventFlagMaskControl
        | kCGEventFlagMaskAlternate
        | kCGEventFlagMaskCommand
    )
    option = kCGEventTapOptionDefault if DICTATION_SWALLOW else kCGEventTapOptionListenOnly
    state = {"fn": False}

    def callback(_proxy, etype, event, _ref):
        try:
            if etype != kCGEventFlagsChanged:
                return event
            flags = int(CGEventGetFlags(event))
            down = _fn_alone(flags, secondary_fn=secondary, other_mods=other)
            if down and not state["fn"]:
                state["fn"] = True
                if daemon.on_fn_edge(down=True):
                    return None
            elif not down and state["fn"]:
                state["fn"] = False
                if daemon.on_fn_edge(down=False):
                    return None
        except Exception as e:
            print(f"[dictation] tap callback: {e}", flush=True)
        return event

    mask = CGEventMaskBit(kCGEventFlagsChanged)
    tap = CGEventTapCreate(
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        option,
        mask,
        callback,
        None,
    )
    if tap is None:
        print(
            "[dictation] event tap unavailable — grant Accessibility "
            "(and Input Monitoring) to this terminal/Python in System Settings.",
            flush=True,
        )
        return False
    source = CFMachPortCreateRunLoopSource(None, tap, 0)
    CFRunLoopAddSource(CFRunLoopGetCurrent(), source, kCFRunLoopCommonModes)
    CGEventTapEnable(tap, True)
    print(
        f"[dictation] Fn hotkey armed (mode={DICTATION_MODE}, swallow={int(DICTATION_SWALLOW)})",
        flush=True,
    )
    return True


def run_dictation() -> None:
    from envfile import load_dotenv

    load_dotenv()
    if not dictation_enabled():
        print("[dictation] disabled", flush=True)
        return

    daemon = DictationDaemon()

    def _on_sig(_signum, _frame) -> None:
        daemon.stop()
        try:
            from Quartz import CFRunLoopGetCurrent, CFRunLoopStop

            CFRunLoopStop(CFRunLoopGetCurrent())
        except Exception:
            pass

    signal.signal(signal.SIGTERM, _on_sig)
    signal.signal(signal.SIGINT, _on_sig)

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(f"{os.getpid()}\n", encoding="utf-8")
    print(
        f"[dictation] ready — press Fn alone to dictate into the focused field "
        f"(idle={DICTATION_IDLE:g}s)",
        flush=True,
    )
    if not _install_fn_tap(daemon):
        print("[dictation] no event tap — exiting", flush=True)
        return
    try:
        from Quartz import CFRunLoopRun

        CFRunLoopRun()
    except Exception as e:
        print(f"[dictation] run loop ended: {e}", flush=True)
    daemon.stop()
    try:
        PID_PATH.unlink(missing_ok=True)
    except OSError:
        pass
    print("[dictation] stopped", flush=True)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print("dictation.py takes no args; use: cua dictation start", file=sys.stderr)
        return 2
    run_dictation()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
