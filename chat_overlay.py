"""Electron chat desktop app launcher + shared helpers.

The AppKit ``NSPanel`` chat UI was removed. Chat is now an Electron window
(``chat_app/``) talking to ``chat_bridge.py`` on localhost.

Tray / ``cua chat`` set ``chat_overlay_enabled`` and call ``ensure_chat_app``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from app_status import (
    pid_alive,
    read_status,
    set_chat_app_pid,
    set_chat_overlay_enabled,
)

_OFF = {"0", "false", "no", "off"}
ROOT = Path(__file__).resolve().parent
CHAT_APP_DIR = ROOT / "chat_app"


def chat_overlay_env_enabled() -> bool:
    return os.environ.get("CHAT_OVERLAY", "0").strip().lower() not in _OFF


def chat_overlay_enabled(data: dict[str, Any] | None = None) -> bool:
    """True when the chat window should be shown (tray / cua chat / env)."""
    snap = data if data is not None else read_status()
    val = snap.get("chat_overlay_enabled")
    if val is None:
        return chat_overlay_env_enabled()
    return bool(val)


def chat_should_show(data: dict[str, Any] | None = None) -> bool:
    snap = data if data is not None else read_status()
    if not chat_overlay_enabled(snap):
        return False
    if snap.get("overlay_hidden"):
        return False
    return True


def command_for_orchestrator(text: str, *, look_at_screen: bool) -> str:
    """User bubble text → utterance the orchestrator should hear."""
    body = (text or "").strip()
    if look_at_screen:
        if body:
            return f"Look at the current screen. {body}"
        return "Look at the current screen and tell me what you see."
    return body


def relative_chat_time(iso: str, *, now=None) -> str:
    """Compact relative time for sidebar rows (Just now, 5m ago, Yesterday)."""
    from datetime import datetime, timezone

    raw = (iso or "").strip()
    if not raw:
        return ""
    try:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw[:10]
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    delta = current - stamp.astimezone(timezone.utc)
    secs = int(delta.total_seconds())
    if secs < 45:
        return "Just now"
    if secs < 3600:
        return f"{max(1, secs // 60)}m ago"
    if secs < 86400:
        return f"{max(1, secs // 3600)}h ago"
    days = secs // 86400
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"{days}d ago"
    local = stamp.astimezone()
    if local.year == current.astimezone().year:
        return f"{local.strftime('%b')} {local.day}"
    return f"{local.strftime('%b')} {local.day}, {local.year}"


def _electron_bin() -> str | None:
    local = CHAT_APP_DIR / "node_modules" / ".bin" / "electron"
    if local.is_file():
        return str(local)
    which = shutil.which("electron")
    return which


def ensure_chat_bridge_and_app(*, focus: bool = False) -> None:
    """Start chat_bridge + Electron when chat is enabled."""
    from chat_bridge import ensure_chat_bridge

    ensure_chat_bridge()
    data = read_status()
    pid = data.get("chat_app_pid")
    if pid_alive(pid):
        if focus:
            _focus_electron()
        return
    electron = _electron_bin()
    if not electron:
        print(
            "[chat] Electron not installed. Run: cd chat_app && npm install",
            flush=True,
        )
        return
    env = os.environ.copy()
    env.setdefault("CHAT_BRIDGE_PORT", os.environ.get("CHAT_BRIDGE_PORT", "8743"))
    # Cursor / some hosts set this so Electron runs as plain Node; then
    # require("electron") is a path string and main.js crashes on app.whenReady.
    env.pop("ELECTRON_RUN_AS_NODE", None)
    try:
        from app_status import RUNTIME_DIR

        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        log_path = RUNTIME_DIR / "chat-app.log"
        log_f = open(log_path, "a", encoding="utf-8", buffering=1)
        log_f.write(f"\n--- electron spawn {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        log_f.flush()
    except Exception:
        log_f = subprocess.DEVNULL
        log_path = None
    try:
        proc = subprocess.Popen(
            [electron, str(CHAT_APP_DIR)],
            cwd=str(CHAT_APP_DIR),
            env=env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except Exception as e:
        print(f"[chat] failed to start Electron: {e}", flush=True)
        return
    set_chat_app_pid(proc.pid)
    extra = f" log={log_path}" if log_path else ""
    print(f"[chat] Electron started (pid={proc.pid}){extra}", flush=True)


def _focus_electron() -> None:
    """Best-effort raise on macOS."""
    if sys.platform != "darwin":
        return
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to set frontmost of '
                'first process whose name contains "Electron" to true',
            ],
            check=False,
            timeout=2,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def stop_chat_app(*, wait: float = 1.5) -> None:
    from chat_bridge import stop_chat_bridge

    data = read_status()
    pid = data.get("chat_app_pid")
    if pid_alive(pid):
        try:
            os.kill(int(pid), 15)
        except Exception:
            pass
        deadline = time.time() + wait
        while time.time() < deadline and pid_alive(pid):
            time.sleep(0.05)
        if pid_alive(pid):
            try:
                os.kill(int(pid), 9)
            except Exception:
                pass
    set_chat_app_pid(None)
    stop_chat_bridge(wait=wait)


def sync_chat_app(data: dict[str, Any] | None = None) -> None:
    """Tray poll: start Electron when enabled, stop when disabled."""
    snap = data if data is not None else read_status()
    want = chat_overlay_enabled(snap)
    if want:
        ensure_chat_bridge_and_app(focus=False)
    else:
        # Hide by quitting the app (reopens quickly on next toggle).
        if pid_alive(snap.get("chat_app_pid")):
            stop_chat_app()


def cmd_chat(mode: str | None) -> int:
    """``cua chat`` / ``on`` / ``off`` / ``toggle``."""
    key = (mode or "status").strip().lower()
    if key in {"on", "show", "1", "true"}:
        set_chat_overlay_enabled(True)
        try:
            from status_tray import ensure_tray_running

            ensure_tray_running()
        except Exception:
            pass
        ensure_chat_bridge_and_app(focus=True)
        print("chat window on (Electron)")
        return 0
    if key in {"off", "hide", "0", "false"}:
        set_chat_overlay_enabled(False)
        stop_chat_app()
        print("chat window off")
        return 0
    if key in {"toggle", ""}:
        now = chat_overlay_enabled()
        set_chat_overlay_enabled(not now)
        if not now:
            try:
                from status_tray import ensure_tray_running

                ensure_tray_running()
            except Exception:
                pass
            ensure_chat_bridge_and_app(focus=True)
        else:
            stop_chat_app()
        print("chat window " + ("off" if now else "on (Electron)"))
        return 0
    if key == "status":
        print("chat window " + ("on" if chat_overlay_enabled() else "off") + " (Electron · ⌘⌥C)")
        return 0
    print("usage: cua chat [on|off|toggle|status]  (hotkey ⌘⌥C)")
    return 2
