"""Non-activating, click-through log overlay (macOS).

Shows live agent/orchestrator logs on a transparent NSPanel. Clicks pass
through to whatever is underneath. Prefers a secondary display.

Computer-use screenshots now include every monitor, so the panel hides for
each capture (same as a single-display Mac) and comes back after.

Toggle from the menu-bar icon (**Log Overlay**). Built by the tray process
(AppKit main thread).
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Any, Iterator

from app_status import format_tooltip, pid_alive, read_status, set_overlay_hidden

OVERLAY_WIDTH = int(os.environ.get("STATUS_OVERLAY_WIDTH", "440"))
OVERLAY_HEIGHT = int(os.environ.get("STATUS_OVERLAY_HEIGHT", "300"))
OVERLAY_MARGIN = int(os.environ.get("STATUS_OVERLAY_MARGIN", "18"))
OVERLAY_LOG_LINES = int(os.environ.get("STATUS_OVERLAY_LOG_LINES", "16"))
OVERLAY_HIDE_NOTE = "cua.logOverlay.hide"
OVERLAY_SHOW_NOTE = "cua.logOverlay.show"


def overlay_enabled(data: dict[str, Any] | None = None) -> bool:
    """True unless the tray toggle turned the panel off (default on)."""
    snap = data if data is not None else read_status()
    val = snap.get("overlay_enabled")
    if val is None:
        return True
    return bool(val)


def overlay_target_monitor(monitors: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Prefer a non-primary display so CU screenshots stay clean."""
    if not monitors:
        return None
    for mon in monitors:
        if not mon.get("main"):
            return mon
    return next((m for m in monitors if m.get("main")), monitors[0])


def overlay_frame_top_left(
    monitor: dict[str, Any],
    *,
    width: int = OVERLAY_WIDTH,
    height: int = OVERLAY_HEIGHT,
    margin: int = OVERLAY_MARGIN,
) -> dict[str, int]:
    """Bottom-left of ``monitor`` in top-left desktop coordinates."""
    w = min(width, max(80, int(monitor["width"]) - 2 * margin))
    h = min(height, max(80, int(monitor["height"]) - 2 * margin))
    x = int(monitor["x"]) + margin
    y = int(monitor["y"]) + int(monitor["height"]) - margin - h
    return {"x": x, "y": y, "width": w, "height": h}


def format_overlay_text(data: dict[str, Any] | None = None) -> str:
    """Compact live log block for the overlay (same source as the tray tooltip)."""
    return format_tooltip(data, max_log_lines=OVERLAY_LOG_LINES)


def overlay_owner_alive(data: dict[str, Any] | None = None) -> bool:
    """True while the orchestrator or a standalone agent process is running."""
    snap = data if data is not None else read_status()
    return pid_alive(snap.get("orchestrator_pid")) or pid_alive(snap.get("agent_pid"))


def overlay_should_show(data: dict[str, Any] | None = None) -> bool:
    """Panel is visible only while an owner process is alive and not mid-capture."""
    snap = data if data is not None else read_status()
    if not overlay_enabled(snap):
        return False
    if snap.get("overlay_hidden"):
        return False
    return overlay_owner_alive(snap)


def should_hide_overlay_for_capture(monitors: list[dict[str, Any]] | None = None) -> bool:
    """True when a CU screenshot might include log or face overlays."""
    if overlay_enabled():
        return True
    try:
        from face_overlay import face_overlay_enabled

        if face_overlay_enabled():
            return True
    except Exception:
        pass
    try:
        from chat_overlay import chat_overlay_enabled

        if chat_overlay_enabled():
            return True
    except Exception:
        pass
    return False


def _post_overlay_note(name: str) -> None:
    try:
        from Foundation import NSDistributedNotificationCenter

        NSDistributedNotificationCenter.defaultCenter().postNotificationName_object_userInfo_deliverImmediately_(
            name,
            None,
            None,
            True,
        )
    except Exception:
        pass


def _wait_overlay_ack(*, hidden: bool, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if bool(read_status().get("overlay_ack_hidden")) is hidden:
            return
        time.sleep(0.01)


@contextmanager
def pause_overlay_for_capture(
    *,
    monitors: list[dict[str, Any]] | None = None,
) -> Iterator[None]:
    """Hide the log overlay while capturing a screenshot."""
    if not should_hide_overlay_for_capture(monitors):
        yield
        return
    if not pid_alive(read_status().get("tray_pid")):
        yield
        return
    set_overlay_hidden(True)
    _post_overlay_note(OVERLAY_HIDE_NOTE)
    _wait_overlay_ack(hidden=True)
    time.sleep(0.03)
    try:
        yield
    finally:
        set_overlay_hidden(False)
        _post_overlay_note(OVERLAY_SHOW_NOTE)


class LogOverlay:
    """Click-through NSPanel. Construct only on the AppKit main thread."""

    def __init__(self) -> None:
        self.panel = None
        self.text_view = None
        self._last_text = ""
        self._build()

    def _build(self) -> None:
        from AppKit import (  # type: ignore
            NSBackingStoreBuffered,
            NSColor,
            NSFont,
            NSMakeRect,
            NSPanel,
            NSStatusWindowLevel,
            NSTextView,
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorFullScreenAuxiliary,
            NSWindowCollectionBehaviorIgnoresCycle,
            NSWindowSharingNone,
            NSWindowStyleMaskBorderless,
            NSWindowStyleMaskNonactivatingPanel,
        )

        frame = self._cocoa_frame()
        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            style,
            NSBackingStoreBuffered,
            False,
        )
        panel.setLevel_(NSStatusWindowLevel)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.colorWithCalibratedWhite_alpha_(0.05, 0.78))
        panel.setIgnoresMouseEvents_(True)
        panel.setAcceptsMouseMovedEvents_(False)
        panel.setHidesOnDeactivate_(False)
        panel.setFloatingPanel_(True)
        panel.setBecomesKeyOnlyIfNeeded_(True)
        panel.setHasShadow_(True)
        panel.setReleasedWhenClosed_(False)
        panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorIgnoresCycle
        )
        try:
            panel.setSharingType_(NSWindowSharingNone)
        except Exception:
            pass

        inset = 10.0
        tv = NSTextView.alloc().initWithFrame_(
            NSMakeRect(
                inset,
                inset,
                max(40.0, frame.size.width - 2 * inset),
                max(40.0, frame.size.height - 2 * inset),
            )
        )
        tv.setEditable_(False)
        tv.setSelectable_(False)
        tv.setDrawsBackground_(False)
        tv.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(0.96, 0.96))
        try:
            tv.setFont_(NSFont.monospacedSystemFontOfSize_weight_(11.0, 0.0))
        except Exception:
            tv.setFont_(NSFont.userFixedPitchFontOfSize_(11.0))
        panel.contentView().addSubview_(tv)
        panel.orderFrontRegardless()
        self.panel = panel
        self.text_view = tv

    def _cocoa_frame(self):
        from AppKit import NSMakeRect, NSScreen  # type: ignore

        screens = list(NSScreen.screens() or [])
        if not screens:
            return NSMakeRect(18, 18, float(OVERLAY_WIDTH), float(OVERLAY_HEIGHT))
        main = NSScreen.mainScreen()
        target = next((s for s in screens if s != main), None) or main or screens[0]
        vis = target.visibleFrame()
        width = min(float(OVERLAY_WIDTH), max(80.0, vis.size.width - 2 * OVERLAY_MARGIN))
        height = min(float(OVERLAY_HEIGHT), max(80.0, vis.size.height - 2 * OVERLAY_MARGIN))
        x = vis.origin.x + OVERLAY_MARGIN
        y = vis.origin.y + OVERLAY_MARGIN
        return NSMakeRect(x, y, width, height)

    def hide(self) -> None:
        if self.panel is not None:
            self.panel.orderOut_(None)

    def show(self) -> None:
        if self.panel is not None:
            self.panel.orderFrontRegardless()

    def destroy(self) -> None:
        """Take the panel off screen and release it (call on tray quit)."""
        panel = self.panel
        self.panel = None
        self.text_view = None
        if panel is None:
            return
        try:
            panel.orderOut_(None)
        except Exception:
            pass
        try:
            panel.setReleasedWhenClosed_(True)
        except Exception:
            pass
        try:
            panel.close()
        except Exception:
            pass

    def apply_status(self, data: dict[str, Any]) -> None:
        if self.panel is None or self.text_view is None:
            return
        if not overlay_should_show(data):
            self.hide()
            return
        text = format_overlay_text(data)
        if text != self._last_text:
            self._last_text = text
            self.text_view.setString_(text)
            try:
                self.panel.setFrame_display_(self._cocoa_frame(), False)
            except Exception:
                pass
        self.show()
