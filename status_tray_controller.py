"""AppKit tray controller. Imported only from status_tray.main (macOS)."""

from __future__ import annotations

import os
import subprocess
import time

import objc
from AppKit import (  # type: ignore
    NSApplication,
    NSEvent,
    NSEventMaskKeyDown,
    NSEventModifierFlagCommand,
    NSEventModifierFlagControl,
    NSEventModifierFlagOption,
    NSEventModifierFlagShift,
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

from app_status import (
    STATUS_PATH,
    ack_overlay_hidden,
    active_agents,
    format_tooltip,
    log as status_log,
    pid_alive,
    read_status,
    request_cancel,
    request_mark_done,
    request_send,
    set_chat_overlay_enabled,
    set_face_overlay_enabled,
    set_overlay_enabled,
    set_tray_pid,
    signal_quit_orchestrator,
    sleep_mode_enabled,
    status_label,
    toggle_sleep_mode,
)
from status_tray import (
    POLL_SECONDS,
    _add_memory_from_tray,
    _glyph_for,
    _latest_log_dir,
    _scheduled_task_count,
    _scheduled_task_titles,
    trigger_listen_shortcut,
)
from task_log import LOGS_DIR


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
        self._arm_hotkeys()
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

    @objc.python_method
    def _arm_hotkeys(self) -> None:
        try:
            g = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                NSEventMaskKeyDown, self._on_global_hotkey
            )
            loc = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
                NSEventMaskKeyDown, self._on_global_hotkey
            )
            self._hotkeyMonitors = [m for m in (g, loc) if m is not None]
            print(
                "[tray] hotkeys ⌘⌃C (chat) · ⌘⌃S (sleep) · "
                "⌘⌃J (listen/cancel) armed",
                flush=True,
            )
        except Exception as e:
            print(f"[tray] hotkeys unavailable: {e}", flush=True)

    @objc.python_method
    def _on_global_hotkey(self, event):
        # ⌘⌃C = chat toggle (avoids Chrome Inspect ⌘⌥C)
        # ⌘⌃S = sleep toggle; ⌘⌃J = listen/cancel without wake word.
        try:
            cmd = int(NSEventModifierFlagCommand)
            opt = int(NSEventModifierFlagOption)
            shift = int(NSEventModifierFlagShift)
            ctrl = int(NSEventModifierFlagControl)
            flags = int(event.modifierFlags())
            mods = flags & (cmd | opt | shift | ctrl)
            chars = (event.charactersIgnoringModifiers() or "").lower()
            now = time.monotonic()
            chord = chars in {"c", "s", "j"} and mods == (cmd | ctrl)
            if now - float(getattr(self, "_hotkeyAt", 0.0) or 0.0) < 0.45:
                return None if chord else event
            actions = {
                "c": self.toggleChat_,
                "s": self.toggleSleep_,
                "j": self.listenNow_,
            }
            action = actions.get(chars) if mods == (cmd | ctrl) else None
            if action is None:
                return event
            self._hotkeyAt = now
            action(None)
            return None
        except Exception:
            return event

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
        try:
            self.syncOverlay(data)
        except Exception as e:
            print(f"[tray] log overlay sync failed: {e}", flush=True)
        try:
            self.syncFace(data)
        except Exception as e:
            print(f"[tray] face sync failed: {e}", flush=True)
        try:
            self.syncChat(data)
        except Exception as e:
            print(f"[tray] chat sync failed: {e}", flush=True)

    @objc.python_method
    def syncOverlay(self, data: dict) -> None:
        try:
            from log_overlay import LogOverlay, overlay_enabled
        except Exception as e:
            print(f"[tray] log overlay import failed: {e}", flush=True)
            return

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
        try:
            from face_overlay import FaceOverlay, face_overlay_enabled
        except Exception as e:
            print(f"[tray] face overlay import failed: {e}", flush=True)
            return

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
        from chat_overlay import sync_chat_app

        sync_chat_app(data)

    @objc.python_method
    def _add_disabled(self, title: str) -> None:
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, None, "")
        item.setEnabled_(False)
        self.menu.addItem_(item)

    @objc.python_method
    def _add_action(
        self,
        title: str,
        selector: str,
        key: str = "",
        represented=None,
        enabled: bool = True,
        state=None,
    ) -> None:
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, selector, key)
        item.setTarget_(self)
        if represented is not None:
            item.setRepresentedObject_(represented)
        item.setEnabled_(enabled)
        if state is not None:
            item.setState_(state)
        self.menu.addItem_(item)

    @objc.python_method
    def _add_agents_section(self, agents) -> None:
        self._add_disabled(
            f"In Progress ({len(agents)})" if agents else "In Progress (none)"
        )
        if not agents:
            self._add_disabled("  (no subagents running)")
            return
        for a in agents:
            kind = (a.get("kind") or "agent").strip()
            task = (a.get("task") or a.get("id") or "?").strip()
            started = a.get("started_at")
            age = ""
            if isinstance(started, (int, float)) and started > 0:
                secs = max(0, int(time.time() - float(started)))
                age = f" · {secs}s" if secs < 60 else f" · {secs // 60}m"
            title = f"  [{kind}] {task[:50]}{age}"
            if len(title) > 90:
                title = title[:87] + "…"
            self._add_disabled(title)
            self._add_action("    Mark Done", "markDone:", represented=str(a.get("id") or ""))

    @objc.python_method
    def _add_queue_section(self) -> None:
        queued_titles = _scheduled_task_titles()
        queued_count = _scheduled_task_count()
        self._add_disabled(
            f"Scheduled Queue ({queued_count})" if queued_titles else "Scheduled Queue (none)"
        )
        if not queued_titles:
            self._add_disabled("  (no scheduled tasks)")
            return
        for title in queued_titles:
            self._add_disabled(title)

    @objc.python_method
    def _add_logs_section(self, data: dict) -> None:
        self._add_disabled("Recent Logs")
        logs = list(data.get("logs") or [])
        if not logs:
            self._add_disabled("  (no recent logs)")
            return
        for entry in reversed(logs[-12:]):
            title = entry if len(entry) <= 90 else entry[:87] + "…"
            self._add_disabled("  " + title)

    @objc.python_method
    def _add_controls_section(self, data: dict, agents) -> None:
        from log_overlay import overlay_enabled as overlay_is_on
        from face_overlay import face_overlay_enabled as face_is_on
        from chat_overlay import chat_overlay_enabled as chat_is_on

        listening = bool(data.get("stt_active")) or str(data.get("state") or "") in {
            "listening",
            "ask",
        }
        busy = listening or bool(agents)
        self._add_action("Send", "sendAudio:", enabled=listening)
        self._add_action("Cancel Listen / Processing", "cancelListen:", enabled=busy)
        self._add_action("Add Memory", "addMemory:")
        self._add_action("Log Overlay", "toggleOverlay:", state=1 if overlay_is_on(data) else 0)
        self._add_action("Face Overlay", "toggleFaceOverlay:", state=1 if face_is_on(data) else 0)
        self._add_action("Chat ⌘⌃C", "toggleChat:", state=1 if chat_is_on(data) else 0)
        self._add_action(
            "Sleep (ignore wake) ⌘⌃S",
            "toggleSleep:",
            state=1 if sleep_mode_enabled(data) else 0,
        )
        if agents:
            self._add_action("Mark Task Done", "markDone:", represented="")

    @objc.python_method
    def _add_quit_section(self, data: dict) -> None:
        if pid_alive(data.get("orchestrator_pid")):
            self._add_action("Quit Orchestrator", "quitOrchestrator:")
        elif pid_alive(data.get("agent_pid")):
            self._add_action("Quit Agent", "quitOrchestrator:")
        self._add_action("Quit Status Icon", "quitTray:", key="q")

    @objc.python_method
    def rebuildMenu(self, data: dict) -> None:
        self.menu.removeAllItems()
        self._add_disabled(status_label(data))
        orch_pid = data.get("orchestrator_pid")
        if pid_alive(orch_pid):
            self._add_disabled(f"Orchestrator running (pid {orch_pid})")
        self.menu.addItem_(NSMenuItem.separatorItem())
        agents = active_agents(data)
        self._add_agents_section(agents)
        self.menu.addItem_(NSMenuItem.separatorItem())
        self._add_queue_section()
        self.menu.addItem_(NSMenuItem.separatorItem())
        self._add_logs_section(data)
        self.menu.addItem_(NSMenuItem.separatorItem())
        self._add_controls_section(data, agents)
        self.menu.addItem_(NSMenuItem.separatorItem())
        self._add_action("Open Latest Log Folder", "openLogs:")
        self._add_action("Reveal Status File", "revealStatus:")
        self.menu.addItem_(NSMenuItem.separatorItem())
        self._add_quit_section(data)

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
        from chat_overlay import chat_overlay_enabled, ensure_chat_bridge_and_app, hide_chat_app

        data = read_status()
        on = not chat_overlay_enabled(data)
        set_chat_overlay_enabled(on)
        status_log("Chat window on" if on else "Chat window off")
        print("[tray] chat on (Electron)" if on else "[tray] chat off", flush=True)
        if on:
            ensure_chat_bridge_and_app(focus=True)
        else:
            hide_chat_app()
        self.applyStatus(read_status())

    def toggleSleep_(self, _sender) -> None:
        on = toggle_sleep_mode()
        status_log("Sleep on — wake word ignored" if on else "Sleep off — listening")
        print(
            "[tray] sleep on" if on else "[tray] sleep off",
            flush=True,
        )
        self.applyStatus(read_status())

    def listenNow_(self, _sender) -> None:
        trigger_listen_shortcut()

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

    def quitFromSignal_(self, _sender) -> None:
        """Main-thread entry for SIGTERM/SIGINT (see _signal_quit)."""
        self.quitTray_(None)

