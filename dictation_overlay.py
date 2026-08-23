"""Cursor overlay for Fn dictation: dots while holding, spinner after release."""

from __future__ import annotations

import os
import sys
import time
from typing import Any

_OFF = {"0", "false", "no", "off"}

OVERLAY_WIDTH = int(os.environ.get("DICTATION_OVERLAY_WIDTH", "52"))
OVERLAY_HEIGHT = int(os.environ.get("DICTATION_OVERLAY_HEIGHT", "20"))
OVERLAY_OFFSET_X = int(os.environ.get("DICTATION_OVERLAY_OFFSET_X", "14"))
OVERLAY_MARGIN_BELOW = int(os.environ.get("DICTATION_OVERLAY_MARGIN_BELOW", "10"))
OVERLAY_FPS = float(os.environ.get("DICTATION_OVERLAY_FPS", "20"))
OVERLAY_STYLE_DOTS = "dots"
OVERLAY_STYLE_SPINNER = "spinner"
_DOT_PHASE_HZ = 10.0
_SPINNER_RPS = 1.15
_SPINNER_SWEEP = 280.0

_overlay: Any = None


def dictation_overlay_enabled() -> bool:
    if sys.platform != "darwin":
        return False
    return os.environ.get("DICTATION_OVERLAY", "1").strip().lower() not in _OFF


def overlay_frame_near_point(
    cursor_x: float,
    cursor_y: float,
    *,
    width: int = OVERLAY_WIDTH,
    height: int = OVERLAY_HEIGHT,
    offset_x: int = OVERLAY_OFFSET_X,
    margin_below: int = OVERLAY_MARGIN_BELOW,
) -> dict[str, int]:
    """Panel frame in Cocoa screen coords (origin bottom-left)."""
    x = int(cursor_x) + offset_x
    y = int(cursor_y) - height - margin_below
    return {"x": x, "y": y, "width": width, "height": height}


def read_cursor_point() -> tuple[float, float]:
    """Mouse location in Cocoa screen coordinates."""
    try:
        from AppKit import NSEvent  # type: ignore

        loc = NSEvent.mouseLocation()
        return float(loc.x), float(loc.y)
    except Exception:
        pass
    try:
        from Quartz import CGEventCreate, CGEventGetLocation  # type: ignore

        loc = CGEventGetLocation(CGEventCreate(None))
        return float(loc.x), float(loc.y)
    except Exception:
        return 0.0, 0.0


def dot_alphas(phase: int) -> tuple[float, float, float]:
    """Typing-indicator style: one bright dot cycles left to right."""
    phase = int(phase) % 3
    out: list[float] = []
    for i in range(3):
        if i == phase:
            out.append(1.0)
        elif i == (phase - 1) % 3:
            out.append(0.55)
        else:
            out.append(0.28)
    return out[0], out[1], out[2]


def spinner_angles(
    elapsed: float, *, rps: float = _SPINNER_RPS, sweep: float = _SPINNER_SWEEP
) -> tuple[float, float]:
    """Start/end degrees for a rotating arc (Cocoa: 0° = east, CCW)."""
    start = (float(elapsed) * float(rps) * 360.0) % 360.0
    return start, start + float(sweep)


def init_dictation_overlay() -> bool:
    """Create the overlay panel on the AppKit thread. Call once before the run loop."""
    global _overlay
    if not dictation_overlay_enabled():
        return False
    if _overlay is not None:
        return True
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory  # type: ignore

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        _overlay = DictationDotsOverlay()
        return True
    except Exception as exc:
        print(f"[dictation] overlay unavailable ({exc})", flush=True)
        _overlay = None
        return False


def show_dictation_overlay(style: str = OVERLAY_STYLE_DOTS) -> None:
    if _overlay is None:
        return

    def _show() -> None:
        _overlay.show(style=style)

    try:
        from PyObjCTools import AppHelper

        AppHelper.callAfter(_show)
    except Exception:
        try:
            _show()
        except Exception:
            pass


def set_dictation_overlay_style(style: str) -> None:
    """Switch dots ↔ spinner without hiding. No-op if the overlay is down."""
    if _overlay is None:
        return

    def _set() -> None:
        _overlay.set_style(style)

    try:
        from PyObjCTools import AppHelper

        AppHelper.callAfter(_set)
    except Exception:
        try:
            _set()
        except Exception:
            pass


def hide_dictation_overlay() -> None:
    if _overlay is None:
        return
    try:
        from PyObjCTools import AppHelper

        AppHelper.callAfter(_overlay.hide)
    except Exception:
        try:
            _overlay.hide()
        except Exception:
            pass


class DictationDotsOverlay:
    """Click-through NSPanel: three dots while holding Fn, spinner after release."""

    def __init__(self) -> None:
        self.panel = None
        self.view = None
        self._timer = None
        self._timer_target = None
        self._phase = 0
        self._style = OVERLAY_STYLE_DOTS
        self._visible = False
        self._t0 = time.monotonic()
        self._NSBezierPath = None
        self._NSColor = None
        self._NSMakeRect = None
        self._line_cap = 1  # NSRoundLineCapStyle
        self._build()

    def _cocoa_frame(self) -> Any:
        from AppKit import NSMakeRect  # type: ignore

        cx, cy = read_cursor_point()
        rect = overlay_frame_near_point(cx, cy)
        return NSMakeRect(rect["x"], rect["y"], rect["width"], rect["height"])

    def _build(self) -> None:
        import objc
        from AppKit import (  # type: ignore
            NSBackingStoreBuffered,
            NSBezierPath,
            NSColor,
            NSMakeRect,
            NSObject,
            NSPanel,
            NSStatusWindowLevel,
            NSView,
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorFullScreenAuxiliary,
            NSWindowCollectionBehaviorIgnoresCycle,
            NSWindowSharingNone,
            NSRoundLineCapStyle,
            NSWindowStyleMaskBorderless,
            NSWindowStyleMaskNonactivatingPanel,
        )
        from Foundation import NSTimer  # type: ignore

        owner = self

        class DotsView(NSView):
            def initWithFrame_(self, frame):  # noqa: N802
                self = objc.super(DotsView, self).initWithFrame_(frame)
                if self is None:
                    return None
                return self

            def isFlipped(self) -> bool:  # noqa: N802
                return True

            def drawRect_(self, _rect) -> None:  # noqa: N802
                try:
                    owner._draw(self)
                except Exception:
                    pass

        class _AnimTarget(NSObject):
            def tickAnim_(self, _timer) -> None:  # noqa: N802
                if not owner._visible:
                    return
                elapsed = time.monotonic() - owner._t0
                owner._phase = int(elapsed * _DOT_PHASE_HZ) % 3
                try:
                    owner.panel.setFrame_display_(owner._cocoa_frame(), True)
                except Exception:
                    pass
                view = owner.view
                if view is not None:
                    try:
                        view.setNeedsDisplay_(True)
                    except Exception:
                        pass

        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            self._cocoa_frame(),
            style,
            NSBackingStoreBuffered,
            False,
        )
        panel.setLevel_(NSStatusWindowLevel + 2)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
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

        view = DotsView.alloc().initWithFrame_(panel.contentView().bounds())
        view.setAutoresizingMask_(18)
        panel.setContentView_(view)

        target = _AnimTarget.alloc().init()
        interval = max(0.05, 1.0 / max(4.0, OVERLAY_FPS))
        timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            interval,
            target,
            "tickAnim:",
            None,
            True,
        )

        self.panel = panel
        self.view = view
        self._timer = timer
        self._timer_target = target
        self._NSBezierPath = NSBezierPath
        self._NSColor = NSColor
        self._NSMakeRect = NSMakeRect
        self._line_cap = NSRoundLineCapStyle

    def _draw(self, view) -> None:
        NSBezierPath = self._NSBezierPath
        NSColor = self._NSColor
        NSMakeRect = self._NSMakeRect
        if NSBezierPath is None or NSColor is None or NSMakeRect is None:
            return

        bounds = view.bounds()
        w = float(bounds.size.width)
        h = float(bounds.size.height)
        pad = 3.0
        card = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(pad, pad, w - 2 * pad, h - 2 * pad),
            8.0,
            8.0,
        )
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.12, 0.14, 0.20, 0.88).setFill()
        card.fill()

        if self._style == OVERLAY_STYLE_SPINNER:
            self._draw_spinner(w, h)
            return

        alphas = dot_alphas(self._phase)
        dot_r = min(3.2, h * 0.22)
        gap = dot_r * 2.6
        total = gap * 2
        start_x = (w - total) / 2.0
        cy = h / 2.0
        for i, alpha in enumerate(alphas):
            cx = start_x + i * gap
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.35, 0.78, 1.0, alpha).setFill()
            dot = NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(cx - dot_r, cy - dot_r, dot_r * 2, dot_r * 2)
            )
            dot.fill()

    def _draw_spinner(self, w: float, h: float) -> None:
        NSBezierPath = self._NSBezierPath
        NSColor = self._NSColor
        if NSBezierPath is None or NSColor is None:
            return
        cx, cy = w / 2.0, h / 2.0
        radius = min(w, h) * 0.28
        start, end = spinner_angles(time.monotonic() - self._t0)
        path = NSBezierPath.bezierPath()
        path.setLineWidth_(2.2)
        try:
            path.setLineCapStyle_(self._line_cap)
        except Exception:
            pass
        path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
            (cx, cy), radius, start, end, False
        )
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.35, 0.78, 1.0, 1.0).setStroke()
        path.stroke()

    def set_style(self, style: str) -> None:
        nxt = OVERLAY_STYLE_SPINNER if style == OVERLAY_STYLE_SPINNER else OVERLAY_STYLE_DOTS
        if nxt == self._style and self._visible:
            return
        self._style = nxt
        self._phase = 0
        self._t0 = time.monotonic()
        if not self._visible:
            return
        if self.view is not None:
            try:
                self.view.setNeedsDisplay_(True)
            except Exception:
                pass

    def show(self, style: str = OVERLAY_STYLE_DOTS) -> None:
        if self.panel is None:
            return
        self._style = (
            OVERLAY_STYLE_SPINNER if style == OVERLAY_STYLE_SPINNER else OVERLAY_STYLE_DOTS
        )
        self._visible = True
        self._phase = 0
        self._t0 = time.monotonic()
        try:
            self.panel.setFrame_display_(self._cocoa_frame(), False)
        except Exception:
            pass
        try:
            self.panel.orderFrontRegardless()
        except Exception:
            pass
        if self.view is not None:
            try:
                self.view.setNeedsDisplay_(True)
            except Exception:
                pass

    def hide(self) -> None:
        self._visible = False
        if self.panel is None:
            return
        try:
            self.panel.orderOut_(None)
        except Exception:
            pass
