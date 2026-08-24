"""
macOS menu-bar status icon for the computer-use agent.

Hover the icon to see live status + recent log lines (tooltip).
Click for a menu with Send (while listening), Add Memory, Log Overlay, Face Overlay,
Chat (⌘⌥C), Sleep (⌘⌥S), Mark Task Done, logs, and quit.

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
    ack_overlay_hidden,
    active_agents,
    format_tooltip,
    log as status_log,
    pid_alive,
    read_status,
    request_mark_done,
    request_cancel,
    request_send,
    set_face_overlay_enabled,
    set_overlay_enabled,
    set_chat_overlay_enabled,
    set_tray_pid,
    signal_quit_orchestrator,
    sleep_mode_enabled,
    status_label,
    toggle_sleep_mode,
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


def stop_tray(*, wait: float = 1.5) -> None:
    """Ask the menu-bar process to close its NSPanel and exit."""
    if os.environ.get("STATUS_TRAY_CHILD", "").strip() == "1":
        return
    try:
        pid = read_status().get("tray_pid")
    except Exception:
        return
    if not pid_alive(pid):
        return
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return
    if pid == os.getpid():
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.monotonic() + max(0.0, wait)
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            try:
                set_tray_pid(None)
            except Exception:
                pass
            return
        time.sleep(0.05)


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
    from Foundation import NSDistributedNotificationCenter, NSTimer  # type: ignore

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
        overlay = objc.ivar()
        face = objc.ivar()

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
            self.overlay = None
            self.face = None
            self._hotkeyAt = 0.0
            self._hotkeyMonitors = []
            try:
                from AppKit import (  # type: ignore
                    NSEvent,
                    NSEventMaskKeyDown,
                    NSEventModifierFlagCommand,
                    NSEventModifierFlagOption,
                    NSEventModifierFlagControl,
                    NSEventModifierFlagShift,
                )

                cmd = int(NSEventModifierFlagCommand)
                opt = int(NSEventModifierFlagOption)
                shift = int(NSEventModifierFlagShift)
                ctrl = int(NSEventModifierFlagControl)
                need = cmd | opt
                extras = shift | ctrl
                owner = self

                def _cmd_opt_hotkey(event):
                    # ⌘⌥C = chat toggle, ⌘⌥S = sleep toggle
                    try:
                        flags = int(event.modifierFlags())
                        if (flags & need) != need:
                            return event
                        if flags & extras:
                            return event
                        chars = (event.charactersIgnoringModifiers() or "").lower()
                        if chars not in {"c", "s"}:
                            return event
                        now = time.monotonic()
                        if now - float(getattr(owner, "_hotkeyAt", 0.0) or 0.0) < 0.45:
                            return None
                        owner._hotkeyAt = now
                        if chars == "c":
                            owner.toggleChat_(None)
                        else:
                            owner.toggleSleep_(None)
                        return None
                    except Exception:
                        return event

                g = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                    NSEventMaskKeyDown, _cmd_opt_hotkey
                )
                loc = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
                    NSEventMaskKeyDown, _cmd_opt_hotkey
                )
                self._hotkeyMonitors = [m for m in (g, loc) if m is not None]
                print("[tray] hotkeys ⌘⌥C (chat) · ⌘⌥S (sleep) armed", flush=True)
            except Exception as e:
                print(f"[tray] hotkeys unavailable: {e}", flush=True)
            try:
                from log_overlay import OVERLAY_HIDE_NOTE, OVERLAY_SHOW_NOTE

                center = NSDistributedNotificationCenter.defaultCenter()
                center.addObserver_selector_name_object_(
                    self, "hideLogOverlay:", OVERLAY_HIDE_NOTE, None
                )
                center.addObserver_selector_name_object_(
                    self, "showLogOverlay:", OVERLAY_SHOW_NOTE, None
                )
            except Exception as e:
                print(f"[tray] overlay hide/show notes unavailable: {e}", flush=True)
            self.applyStatus(read_status())

            NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                POLL_SECONDS,
                self,
                "tick:",
                None,
                True,
            )
            return self

        def teardownOverlay(self) -> None:
            overlay = getattr(self, "overlay", None)
            self.overlay = None
            if overlay is not None:
                try:
                    overlay.destroy()
                except Exception:
                    pass
            face = getattr(self, "face", None)
            self.face = None
            if face is not None:
                try:
                    face.destroy()
                except Exception:
                    pass
            try:
                from chat_overlay import stop_chat_app

                stop_chat_app()
            except Exception:
                pass

        def applicationWillTerminate_(self, _notif) -> None:
            self.teardownOverlay()
            try:
                set_tray_pid(None)
            except Exception:
                pass

        def hideLogOverlay_(self, _note) -> None:
            overlay = getattr(self, "overlay", None)
            if overlay is not None:
                try:
                    overlay.hide()
                except Exception:
                    pass
            face = getattr(self, "face", None)
            if face is not None:
                try:
                    face.hide()
                except Exception:
                    pass
            ack_overlay_hidden(True)

        def showLogOverlay_(self, _note) -> None:
            data = read_status()
            overlay = getattr(self, "overlay", None)
            if overlay is not None:
                try:
                    from log_overlay import overlay_should_show

                    if overlay_should_show(data):
                        overlay.show()
                    else:
                        overlay.hide()
                except Exception:
                    pass
            face = getattr(self, "face", None)
            if face is not None:
                try:
                    from face_overlay import face_should_show

                    if face_should_show(data):
                        face.show()
                    else:
                        face.hide()
                except Exception:
                    pass
            ack_overlay_hidden(False)

        def tick_(self, _timer) -> None:
            data = read_status()
            agents = active_agents(data)
            sig = (
                f"{data.get('state')}|{data.get('detail')}|{data.get('updated_at')}|"
                f"{len(data.get('logs') or [])}|{len(agents)}|"
                f"{data.get('done_requested')}|{data.get('stt_active')}|"
                f"{data.get('send_requested')}|{data.get('cancel_requested')}|"
                f"{data.get('overlay_hidden')}|"
                f"{data.get('overlay_enabled')}|{data.get('face_overlay_enabled')}|"
                f"{data.get('chat_overlay_enabled')}|"
                f"{data.get('sleep_mode')}|"
                f"{data.get('tts_playing')}|{data.get('tts_play_depth')}|"
                f"{data.get('orchestrator_pid')}|"
                f"{data.get('agent_pid')}"
            )
            if sig != self.lastSig:
                self.lastSig = sig
                self.applyStatus(data)
            else:
                # Recover face if it was orderOut'd (e.g. capture hide) without a
                # status-sig change the poll would otherwise skip.
                self.keepFaceVisible(data)

        @objc.python_method
        def keepFaceVisible(self, data: dict) -> None:
            face = getattr(self, "face", None)
            if face is None:
                return
            try:
                face.apply_status(data)
            except Exception:
                pass

        @objc.python_method
        def applyStatus(self, data: dict) -> None:
            button = self.statusItem.button()
            if button is not None:
                glyph = _glyph_for(str(data.get("state") or "idle"), data)
                if button.image() is None:
                    button.setTitle_(glyph)
                button.setToolTip_(format_tooltip(data))
            self.rebuildMenu(data)
            self.syncOverlay(data)
            self.syncFace(data)
            self.syncChat(data)

        @objc.python_method
        def syncOverlay(self, data: dict) -> None:
            from log_overlay import LogOverlay, overlay_enabled

            want = overlay_enabled(data)
            if want and getattr(self, "overlay", None) is None:
                try:
                    self.overlay = LogOverlay()
                    print("[tray] log overlay on (click-through, non-activating)", flush=True)
                except Exception as e:
                    print(f"[tray] log overlay unavailable: {e}", flush=True)
            elif not want and getattr(self, "overlay", None) is not None:
                overlay = self.overlay
                self.overlay = None
                try:
                    overlay.destroy()
                except Exception:
                    pass
            overlay = getattr(self, "overlay", None)
            if overlay is not None:
                try:
                    overlay.apply_status(data)
                except Exception:
                    pass

        @objc.python_method
        def syncFace(self, data: dict) -> None:
            from face_overlay import FaceOverlay, face_overlay_enabled

            want = face_overlay_enabled(data)
            if want and getattr(self, "face", None) is None:
                try:
                    self.face = FaceOverlay()
                    print("[tray] face overlay on (top-center, capture-excluded)", flush=True)
                except Exception as e:
                    print(f"[tray] face overlay unavailable: {e}", flush=True)
            elif not want and getattr(self, "face", None) is not None:
                face = self.face
                self.face = None
                try:
                    face.destroy()
                except Exception:
                    pass
            face = getattr(self, "face", None)
            if face is not None:
                try:
                    face.apply_status(data)
                except Exception:
                    pass

        @objc.python_method
        def syncChat(self, data: dict) -> None:
            try:
                from chat_overlay import sync_chat_app

                sync_chat_app(data)
            except Exception as e:
                print(f"[tray] chat sync failed: {e}", flush=True)

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
                    title = f"  [{kind}] {task[:50]}{age}"
                    if len(title) > 90:
                        title = title[:87] + "…"
                    item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        title,
                        None,
                        "",
                    )
                    item.setEnabled_(False)
                    self.menu.addItem_(item)
                    mark = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        "    Mark Done",
                        "markDone:",
                        "",
                    )
                    mark.setTarget_(self)
                    mark.setRepresentedObject_(str(a.get("id") or ""))
                    self.menu.addItem_(mark)
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

            listening = bool(data.get("stt_active")) or str(
                data.get("state") or ""
            ) in {"listening", "ask"}
            busy = listening or bool(agents)
            send = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Send",
                "sendAudio:",
                "",
            )
            send.setTarget_(self)
            send.setEnabled_(listening)
            self.menu.addItem_(send)

            cancel = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Cancel Listen / Processing",
                "cancelListen:",
                "",
            )
            cancel.setTarget_(self)
            cancel.setEnabled_(busy)
            self.menu.addItem_(cancel)

            add_mem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Add Memory",
                "addMemory:",
                "",
            )
            add_mem.setTarget_(self)
            self.menu.addItem_(add_mem)

            from log_overlay import overlay_enabled as overlay_is_on
            from face_overlay import face_overlay_enabled as face_is_on
            from chat_overlay import chat_overlay_enabled as chat_is_on

            overlay_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Log Overlay",
                "toggleOverlay:",
                "",
            )
            overlay_item.setTarget_(self)
            overlay_item.setState_(1 if overlay_is_on(data) else 0)
            self.menu.addItem_(overlay_item)

            face_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Face Overlay",
                "toggleFaceOverlay:",
                "",
            )
            face_item.setTarget_(self)
            face_item.setState_(1 if face_is_on(data) else 0)
            self.menu.addItem_(face_item)

            chat_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Chat ⌘⌥C",
                "toggleChat:",
                "",
            )
            chat_item.setTarget_(self)
            chat_item.setState_(1 if chat_is_on(data) else 0)
            self.menu.addItem_(chat_item)

            sleep_on = sleep_mode_enabled(data)
            sleep_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Sleep (ignore wake) ⌘⌥S",
                "toggleSleep:",
                "",
            )
            sleep_item.setTarget_(self)
            sleep_item.setState_(1 if sleep_on else 0)
            self.menu.addItem_(sleep_item)

            if agents:
                mark_all = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "Mark Task Done",
                    "markDone:",
                    "",
                )
                mark_all.setTarget_(self)
                mark_all.setRepresentedObject_("")
                self.menu.addItem_(mark_all)

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

        def toggleOverlay_(self, _sender) -> None:
            from log_overlay import overlay_enabled

            data = read_status()
            set_overlay_enabled(not overlay_enabled(data))
            self.applyStatus(read_status())

        def toggleFaceOverlay_(self, _sender) -> None:
            from face_overlay import face_overlay_enabled

            data = read_status()
            set_face_overlay_enabled(not face_overlay_enabled(data))
            self.applyStatus(read_status())

        def toggleChat_(self, _sender) -> None:
            from chat_overlay import chat_overlay_enabled, ensure_chat_bridge_and_app, stop_chat_app

            data = read_status()
            on = not chat_overlay_enabled(data)
            set_chat_overlay_enabled(on)
            status_log("Chat window on" if on else "Chat window off")
            print("[tray] chat on (Electron)" if on else "[tray] chat off", flush=True)
            if on:
                ensure_chat_bridge_and_app(focus=True)
            else:
                stop_chat_app()
            self.applyStatus(read_status())

        def toggleSleep_(self, _sender) -> None:
            on = toggle_sleep_mode()
            status_log("Sleep on — wake word ignored" if on else "Sleep off — listening")
            print(
                "[tray] sleep on" if on else "[tray] sleep off",
                flush=True,
            )
            self.applyStatus(read_status())

        def sendAudio_(self, _sender) -> None:
            data = read_status()
            listening = bool(data.get("stt_active")) or str(
                data.get("state") or ""
            ) in {"listening", "ask"}
            if not listening:
                return
            request_send()

        def cancelListen_(self, _sender) -> None:
            request_cancel()

        def addMemory_(self, _sender) -> None:
            _add_memory_from_tray()

        def markDone_(self, sender) -> None:
            agent_id = None
            try:
                obj = sender.representedObject()
                if obj:
                    agent_id = str(obj).strip() or None
            except Exception:
                agent_id = None
            request_mark_done(agent_id)

        def quitOrchestrator_(self, _sender) -> None:
            signal_quit_orchestrator()

        def quitTray_(self, _sender) -> None:
            self.teardownOverlay()
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
    app.setDelegate_(_TRAY_CONTROLLER)

    def _signal_quit(_signum=None, _frame=None) -> None:
        # Close the panel on the AppKit thread, then terminate.
        NSApplication.sharedApplication().performSelectorOnMainThread_withObject_waitUntilDone_(
            "terminate:",
            None,
            False,
        )

    try:
        signal.signal(signal.SIGTERM, _signal_quit)
        signal.signal(signal.SIGINT, _signal_quit)
    except Exception:
        pass

    print(f"[tray] menu bar ready — hover for status (watching {STATUS_PATH})", flush=True)
    app.run()


if __name__ == "__main__":
    main()
