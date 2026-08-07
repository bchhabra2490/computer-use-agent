"""
macOS menu-bar status icon for the computer-use agent.

Hover the icon to see live status + recent log lines (tooltip).
Click for a menu with more logs, open latest run folder, and quit tray.

Usage:
    python status_tray.py

Started automatically by the orchestrator / agent unless STATUS_TRAY=0.
Requires a GUI session (not pure SSH). AppKit must own the main thread.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from app_status import (
    STATUS_PATH,
    active_agents,
    format_tooltip,
    pid_alive,
    read_status,
    set_tray_pid,
    signal_quit_orchestrator,
    status_label,
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
        if isinstance(tray_pid, int) and tray_pid > 0:
            try:
                os.kill(tray_pid, 0)
                return None
            except OSError:
                pass
    except Exception:
        pass

    script = Path(__file__).resolve()
    env = os.environ.copy()
    env["STATUS_TRAY_CHILD"] = "1"
    try:
        proc = subprocess.Popen(
            [sys.executable, str(script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
        print(f"[tray] started menu-bar status (pid={proc.pid})", flush=True)
        return proc
    except Exception as e:
        print(f"[tray] failed to start: {e}", file=sys.stderr)
        return None


def _glyph_for(state: str) -> str:
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


def main() -> None:
    if sys.platform != "darwin":
        print("status_tray is macOS-only.", file=sys.stderr)
        sys.exit(1)

    import objc
    from AppKit import (  # type: ignore
        NSApplication,
        NSApplicationActivationPolicyAccessory,
        NSImage,
        NSMenu,
        NSMenuItem,
        NSObject,
        NSSize,
        NSStatusBar,
        NSVariableStatusItemLength,
        NSWorkspace,
    )
    from Foundation import NSTimer  # type: ignore

    def _make_template_icon():
        try:
            image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                "waveform.circle",
                "Jarvis",
            )
            if image is None:
                return None
            image.setSize_(NSSize(18, 18))
            image.setTemplate_(True)
            return image
        except Exception:
            return None

    class TrayController(NSObject):
        statusItem = objc.ivar()
        menu = objc.ivar()
        lastSig = objc.ivar()

        def init(self):
            self = objc.super(TrayController, self).init()
            if self is None:
                return None
            self.statusItem = NSStatusBar.systemStatusBar().statusItemWithLength_(
                NSVariableStatusItemLength
            )
            button = self.statusItem.button()
            icon = _make_template_icon()
            if icon is not None and button is not None:
                button.setImage_(icon)
                button.setTitle_("")
            elif button is not None:
                button.setTitle_("◇")
            if button is not None:
                button.setToolTip_("Jarvis · starting…")

            self.menu = NSMenu.alloc().init()
            self.statusItem.setMenu_(self.menu)
            self.lastSig = None
            self.applyStatus(read_status())

            NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                POLL_SECONDS,
                self,
                "tick:",
                None,
                True,
            )
            return self

        def tick_(self, _timer) -> None:
            data = read_status()
            sig = (
                f"{data.get('state')}|{data.get('detail')}|{data.get('updated_at')}|"
                f"{len(data.get('logs') or [])}"
            )
            if sig == self.lastSig:
                return
            self.lastSig = sig
            self.applyStatus(data)

        @objc.python_method
        def applyStatus(self, data: dict) -> None:
            button = self.statusItem.button()
            if button is not None:
                glyph = _glyph_for(str(data.get("state") or "idle"))
                if button.image() is None:
                    button.setTitle_(glyph)
                button.setToolTip_(format_tooltip(data))
            self.rebuildMenu(data)

        @objc.python_method
        def rebuildMenu(self, data: dict) -> None:
            self.menu.removeAllItems()

            header = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                status_label(data),
                None,
                "",
            )
            header.setEnabled_(False)
            self.menu.addItem_(header)

            orch_pid = data.get("orchestrator_pid")
            if pid_alive(orch_pid):
                orch_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    f"Orchestrator running (pid {orch_pid})",
                    None,
                    "",
                )
                orch_item.setEnabled_(False)
                self.menu.addItem_(orch_item)

            self.menu.addItem_(NSMenuItem.separatorItem())

            # --- In-progress subagents ---
            agents = active_agents(data)
            section = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                f"In Progress ({len(agents)})" if agents else "In Progress (none)",
                None,
                "",
            )
            section.setEnabled_(False)
            self.menu.addItem_(section)
            if agents:
                for a in agents:
                    kind = (a.get("kind") or "agent").strip()
                    task = (a.get("task") or a.get("id") or "?").strip()
                    started = a.get("started_at")
                    age = ""
                    if isinstance(started, (int, float)) and started > 0:
                        secs = max(0, int(time.time() - float(started)))
                        if secs < 60:
                            age = f" · {secs}s"
                        else:
                            age = f" · {secs // 60}m"
                    title = f"  [{kind}] {task[:55]}{age}"
                    if len(title) > 90:
                        title = title[:87] + "…"
                    item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        title,
                        None,
                        "",
                    )
                    item.setEnabled_(False)
                    self.menu.addItem_(item)
            else:
                idle = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "  (no subagents running)",
                    None,
                    "",
                )
                idle.setEnabled_(False)
                self.menu.addItem_(idle)

            self.menu.addItem_(NSMenuItem.separatorItem())

            # --- Recent logs ---
            logs_header = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Recent Logs",
                None,
                "",
            )
            logs_header.setEnabled_(False)
            self.menu.addItem_(logs_header)

            logs = list(data.get("logs") or [])
            if not logs:
                empty = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "  (no recent logs)",
                    None,
                    "",
                )
                empty.setEnabled_(False)
                self.menu.addItem_(empty)
            else:
                for entry in reversed(logs[-12:]):
                    title = entry if len(entry) <= 90 else entry[:87] + "…"
                    item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        "  " + title,
                        None,
                        "",
                    )
                    item.setEnabled_(False)
                    self.menu.addItem_(item)

            self.menu.addItem_(NSMenuItem.separatorItem())

            open_logs = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Open Latest Log Folder",
                "openLogs:",
                "",
            )
            open_logs.setTarget_(self)
            self.menu.addItem_(open_logs)

            reveal_status = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Reveal Status File",
                "revealStatus:",
                "",
            )
            reveal_status.setTarget_(self)
            self.menu.addItem_(reveal_status)

            self.menu.addItem_(NSMenuItem.separatorItem())

            if pid_alive(data.get("orchestrator_pid")):
                quit_orch = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "Quit Orchestrator",
                    "quitOrchestrator:",
                    "",
                )
                quit_orch.setTarget_(self)
                self.menu.addItem_(quit_orch)
            elif pid_alive(data.get("agent_pid")):
                quit_agent = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "Quit Agent",
                    "quitOrchestrator:",
                    "",
                )
                quit_agent.setTarget_(self)
                self.menu.addItem_(quit_agent)

            quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Quit Status Icon",
                "quitTray:",
                "q",
            )
            quit_item.setTarget_(self)
            self.menu.addItem_(quit_item)

        def openLogs_(self, _sender) -> None:
            data = read_status()
            path = _latest_log_dir(data.get("log_dir"))
            if path is None:
                path = LOGS_DIR
                path.mkdir(parents=True, exist_ok=True)
            NSWorkspace.sharedWorkspace().openFile_(str(path))

        def revealStatus_(self, _sender) -> None:
            STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
            if not STATUS_PATH.exists():
                STATUS_PATH.write_text("{}\n", encoding="utf-8")
            try:
                subprocess.run(
                    ["open", "-R", str(STATUS_PATH)],
                    check=False,
                    timeout=5,
                )
            except Exception:
                NSWorkspace.sharedWorkspace().openFile_(str(STATUS_PATH.parent))

        def quitOrchestrator_(self, _sender) -> None:
            signal_quit_orchestrator()

        def quitTray_(self, _sender) -> None:
            try:
                set_tray_pid(None)
            except Exception:
                pass
            NSApplication.sharedApplication().terminate_(None)

    set_tray_pid(os.getpid())
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    # Keep a strong Python reference so the controller isn't GC'd.
    global _TRAY_CONTROLLER  # noqa: PLW0603
    _TRAY_CONTROLLER = TrayController.alloc().init()
    print(f"[tray] menu bar ready — hover for status (watching {STATUS_PATH})", flush=True)
    app.run()


if __name__ == "__main__":
    main()
