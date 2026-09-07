"""
macOS menu-bar status icon for the computer-use agent.

Hover the icon to see live status + recent log lines (tooltip).
Click for a menu with Send (while listening), Add Memory, Log Overlay, Face Overlay,
Chat (⌘⌃C), Sleep (⌘⌃S), Listen/Cancel (⌘⌃J), Mark Task Done, logs, and quit.

Usage:
    python status_tray.py

Started automatically by the orchestrator / agent unless STATUS_TRAY=0.
Requires a GUI session (not pure SSH). AppKit must own the main thread.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from app_status import (
    STATUS_PATH,
    log as status_log,
    pid_alive,
    read_status,
    request_cancel,
    request_listen,
    set_tray_pid,
)
from task_log import LOGS_DIR

POLL_SECONDS = float(os.environ.get("STATUS_TRAY_POLL", "0.75"))
_TRAY_CONTROLLER = None
STATE_GLYPH = {
    "idle": "○",
    "ready": "○",
    "waiting": "◐",
    "listening": "◉",
    "speaking": "◎",
    "thinking": "◐",
    "agent": "●",
    "running": "●",
    "ask": "?",
    "error": "✖",
    "done": "✓",
}


def _scheduled_task_titles(*, limit: int = 6) -> list[str]:
    try:
        from scheduled_tasks import list_scheduled_tasks

        rows = [row for row in list_scheduled_tasks() if row.status == "queued"]
    except Exception:
        return []
    now = time.time()
    out: list[str] = []
    for row in rows[:limit]:
        secs = max(0, int(row.run_at - now))
        age = f"{secs}s" if secs < 60 else f"{secs // 60}m"
        title = f"  {row.task[:52]} · {age}"
        if len(title) > 88:
            title = title[:85] + "…"
        out.append(title)
    if len(rows) > limit:
        out.append(f"  … {len(rows) - limit} more")
    return out


def _scheduled_task_count() -> int:
    try:
        from scheduled_tasks import list_scheduled_tasks

        return sum(1 for row in list_scheduled_tasks() if row.status == "queued")
    except Exception:
        return 0


def _tray_script_path() -> Path:
    return Path(__file__).resolve()


def _iter_orphan_tray_pids(*, exclude: int | None = None) -> list[int]:
    """Find leftover ``status_tray.py`` processes for this checkout."""
    script = str(_tray_script_path())
    out: list[int] = []
    try:
        proc = subprocess.run(
            ["pgrep", "-f", script],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return out
    me = os.getpid()
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line.isdigit():
            continue
        pid = int(line)
        if pid == me or (exclude is not None and pid == exclude):
            continue
        if pid_alive(pid):
            out.append(pid)
    return out


def ensure_tray_running() -> subprocess.Popen | None:
    """
    Spawn the menu-bar process if not already running and STATUS_TRAY is enabled.

    Safe to call from orchestrator / agent. Returns the Popen handle when started
    from this call, else None.
    """
    if sys.platform != "darwin":
        return None
    if os.environ.get("STATUS_TRAY", "1").strip().lower() in {"0", "false", "no", "off"}:
        return None

    try:
        data = read_status()
        tray_pid = data.get("tray_pid")
        if pid_alive(tray_pid):
            return None
    except Exception:
        pass

    script = _tray_script_path()
    env = os.environ.copy()
    env["STATUS_TRAY_CHILD"] = "1"
    # Don't poison Electron (started by the tray) into Node mode.
    env.pop("ELECTRON_RUN_AS_NODE", None)
    try:
        from app_status import RUNTIME_DIR

        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        log_path = RUNTIME_DIR / "tray.log"
        log_f = open(log_path, "a", encoding="utf-8", buffering=1)
        log_f.write(f"\n--- tray spawn {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        log_f.flush()
        proc = subprocess.Popen(
            [sys.executable, str(script)],
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )
        print(f"[tray] started menu-bar status (pid={proc.pid}) log={log_path}", flush=True)
        return proc
    except Exception as e:
        print(f"[tray] failed to start: {e}", file=sys.stderr)
        return None


def _kill_pid(pid: int, *, wait: float) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.monotonic() + max(0.0, wait)
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return
        time.sleep(0.05)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    time.sleep(0.1)


def stop_tray(*, wait: float = 2.0) -> None:
    """Ask the menu-bar process to close overlays and exit; SIGKILL if needed."""
    if os.environ.get("STATUS_TRAY_CHILD", "").strip() == "1":
        return
    targets: list[int] = []
    try:
        raw = read_status().get("tray_pid")
        if raw is not None:
            pid = int(raw)
            if pid != os.getpid() and pid_alive(pid):
                targets.append(pid)
    except (TypeError, ValueError, Exception):
        pass
    for orphan in _iter_orphan_tray_pids(exclude=os.getpid()):
        if orphan not in targets:
            targets.append(orphan)
    if not targets:
        try:
            set_tray_pid(None)
        except Exception:
            pass
        return
    for pid in targets:
        print(f"[tray] stopping menu-bar status (pid={pid})", flush=True)
        _kill_pid(pid, wait=wait)
    try:
        set_tray_pid(None)
    except Exception:
        pass
    # Face/log panels die with the tray process; clear any stragglers.
    for orphan in _iter_orphan_tray_pids(exclude=os.getpid()):
        print(f"[tray] killing leftover tray (pid={orphan})", flush=True)
        _kill_pid(orphan, wait=0.5)
    try:
        set_tray_pid(None)
    except Exception:
        pass


def _add_memory_from_tray() -> None:
    """Capture the screen immediately, then describe + save in the background."""
    try:
        from memory import capture_screen_png, save_screen_from_png

        png, app = capture_screen_png()
    except Exception as e:
        print(f"[tray] add memory screenshot failed: {e}", flush=True)
        status_log(f"Add memory failed: {e}")
        return

    status_log(f"Add memory: captured screen ({app or 'unknown app'}), describing…")
    print(f"[tray] add memory captured ({len(png)} bytes, app={app!r})", flush=True)

    def _describe_and_save() -> None:
        try:
            from envfile import load_dotenv

            load_dotenv()
            from openai import OpenAI

            client = OpenAI()
            result = save_screen_from_png(
                client,
                png,
                app=app,
                hint="Saved from menu bar Add Memory",
            )
            print(f"[tray] {result}", flush=True)
            status_log(result)
        except Exception as e:
            print(f"[tray] add memory save failed: {e}", flush=True)
            status_log(f"Add memory failed: {e}")

    threading.Thread(target=_describe_and_save, name="tray-add-memory", daemon=True).start()


def _glyph_for(state: str, data: dict | None = None) -> str:
    if data is not None and data.get("sleep_mode"):
        return "☾"
    key = (state or "idle").lower().strip()
    if key in STATE_GLYPH:
        return STATE_GLYPH[key]
    for prefix, glyph in STATE_GLYPH.items():
        if key.startswith(prefix):
            return glyph
    return "◇"


def _latest_log_dir(explicit: str | None = None) -> Path | None:
    if explicit:
        path = Path(explicit)
        if path.is_dir():
            return path
    if not LOGS_DIR.is_dir():
        return None
    dirs = [p for p in LOGS_DIR.iterdir() if p.is_dir()]
    if not dirs:
        return None
    return max(dirs, key=lambda p: p.stat().st_mtime)


def trigger_listen_shortcut(data: dict | None = None) -> str:
    """Start from idle; otherwise cancel and discard the current voice turn."""
    snap = data if data is not None else read_status()
    state = str(snap.get("state") or "").strip().lower()
    idle = not bool(snap.get("stt_active")) and state in {"idle", "ready", "waiting"}
    if not idle:
        request_cancel()
        return "cancel"
    request_listen()
    return "listen"



def main() -> None:
    if sys.platform != "darwin":
        print("status_tray is macOS-only.", file=sys.stderr)
        sys.exit(1)

    from AppKit import NSApplication, NSApplicationActivationPolicyAccessory  # type: ignore
    from status_tray_controller import TrayController

    set_tray_pid(os.getpid())
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    global _TRAY_CONTROLLER  # noqa: PLW0603
    _TRAY_CONTROLLER = TrayController.alloc().init()
    app.setDelegate_(_TRAY_CONTROLLER)

    def _signal_quit(_signum=None, _frame=None) -> None:
        # Never call AppKit teardown directly from a signal handler — schedule
        # quitTray on the main run loop so the face panel is destroyed first.
        ctrl = _TRAY_CONTROLLER
        if ctrl is not None:
            try:
                ctrl.performSelectorOnMainThread_withObject_waitUntilDone_(
                    "quitFromSignal:",
                    None,
                    False,
                )
                return
            except Exception:
                pass
        try:
            NSApplication.sharedApplication().performSelectorOnMainThread_withObject_waitUntilDone_(
                "terminate:",
                None,
                False,
            )
        except Exception:
            os._exit(0)

    try:
        signal.signal(signal.SIGTERM, _signal_quit)
        signal.signal(signal.SIGINT, _signal_quit)
    except Exception:
        pass

    print(f"[tray] menu bar ready — hover for status (watching {STATUS_PATH})", flush=True)
    app.run()


if __name__ == "__main__":
    main()
