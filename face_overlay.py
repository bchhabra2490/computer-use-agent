"""Top-center Jarvis face overlay (macOS) — eyes by session mood.

Click-through NSPanel with ``NSWindowSharingNone`` so it stays out of
screenshots when possible; ``pause_overlay_for_capture`` also hides it.

Moods (from ``status.json`` state / live TTS):
  sleep   — waiting / idle (eyes shut, floating zzz)
  listen  — listening / ask (eyes open after wake)
  speak   — TTS playing (eyes pulse; no mouth)
  think   — thinking / agent (eyes look up, blink loop)
"""

from __future__ import annotations

import math
import os
import time
from typing import Any

from app_status import read_status

FACE_WIDTH = int(os.environ.get("FACE_OVERLAY_WIDTH", "132"))
FACE_HEIGHT = int(os.environ.get("FACE_OVERLAY_HEIGHT", "110"))
FACE_MARGIN_TOP = int(os.environ.get("FACE_OVERLAY_MARGIN_TOP", "10"))
FACE_FPS = float(os.environ.get("FACE_OVERLAY_FPS", "20"))

_SLEEP_STATES = frozenset({"idle", "ready", "waiting", "done", "error"})
_LISTEN_STATES = frozenset({"listening", "ask"})
_SPEAK_STATES = frozenset({"speaking"})
_THINK_STATES = frozenset({"thinking", "agent", "running"})


def face_overlay_env_enabled() -> bool:
    return os.environ.get("FACE_OVERLAY", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def face_overlay_enabled(data: dict[str, Any] | None = None) -> bool:
    """True unless tray toggle / env turned the face off (default on)."""
    if not face_overlay_env_enabled():
        return False
    snap = data if data is not None else read_status()
    val = snap.get("face_overlay_enabled")
    if val is None:
        return True
    return bool(val)


def face_mood_for_state(
    state: str | None,
    data: dict[str, Any] | None = None,
) -> str:
    """Map session phase → face mood.

    Prefer live TTS playback over session phase — async speak_later / streaming
    TTS often leaves the session on waiting while audio is still playing.
    """
    snap = data if data is not None else None
    if snap is not None and snap.get("tts_playing"):
        return "speak"
    key = (state or "idle").strip().lower()
    if key in _SPEAK_STATES or key.startswith("speaking"):
        return "speak"
    if key in _LISTEN_STATES or key.startswith("listen") or key.startswith("ask"):
        return "listen"
    if key in _THINK_STATES or key.startswith("think") or key.startswith("agent"):
        return "think"
    if key in _SLEEP_STATES or key.startswith("wait") or key.startswith("idle"):
        return "sleep"
    return "sleep"


def face_should_show(data: dict[str, Any] | None = None) -> bool:
    """Visible while the face toggle is on and not mid-screenshot hide.

    Does not require orchestrator_pid — the tray owns the panel, and requiring
    a live owner raced with startup (face flashed then stayed hidden).
    """
    snap = data if data is not None else read_status()
    if not face_overlay_enabled(snap):
        return False
    if snap.get("overlay_hidden"):
        return False
    return True


def face_frame_top_center(
    monitor: dict[str, Any],
    *,
    width: int = FACE_WIDTH,
    height: int = FACE_HEIGHT,
    margin_top: int = FACE_MARGIN_TOP,
) -> dict[str, int]:
    """Top-center of ``monitor`` in top-left desktop coordinates."""
    w = min(width, max(64, int(monitor["width"]) - 40))
    h = min(height, max(56, int(monitor["height"]) - 40))
    x = int(monitor["x"]) + (int(monitor["width"]) - w) // 2
    y = int(monitor["y"]) + margin_top
    return {"x": x, "y": y, "width": w, "height": h}


class FaceOverlay:
    """Animated face NSPanel. Construct only on the AppKit main thread."""

    def __init__(self) -> None:
        self.panel = None
        self.view = None
        self._timer = None
        self._timer_target = None
        self._mood = "sleep"
        self._t0 = time.monotonic()
        self._NSBezierPath = None
        self._NSColor = None
        self._NSFont = None
        self._NSMakeRect = None
        self._NSString = None
        self._build()

    def _build(self) -> None:
        import objc
        from AppKit import (  # type: ignore
            NSBackingStoreBuffered,
            NSBezierPath,
            NSColor,
            NSFont,
            NSMakeRect,
            NSObject,
            NSPanel,
            NSStatusWindowLevel,
            NSView,
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorFullScreenAuxiliary,
            NSWindowCollectionBehaviorIgnoresCycle,
            NSWindowSharingNone,
            NSWindowStyleMaskBorderless,
            NSWindowStyleMaskNonactivatingPanel,
        )
        from Foundation import NSString, NSTimer  # type: ignore

        owner = self

        class FaceView(NSView):
            def initWithFrame_(self, frame):  # noqa: N802
                self = objc.super(FaceView, self).initWithFrame_(frame)
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
                view = owner.view
                if view is None:
                    return
                try:
                    view.setNeedsDisplay_(True)
                except Exception:
                    pass

        frame = self._cocoa_frame()
        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            style,
            NSBackingStoreBuffered,
            False,
        )
        panel.setLevel_(NSStatusWindowLevel + 1)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setIgnoresMouseEvents_(True)
        panel.setAcceptsMouseMovedEvents_(False)
        panel.setHidesOnDeactivate_(False)
        panel.setFloatingPanel_(True)
        panel.setBecomesKeyOnlyIfNeeded_(True)
        panel.setHasShadow_(False)
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

        view = FaceView.alloc().initWithFrame_(panel.contentView().bounds())
        view.setAutoresizingMask_(18)  # width + height flexible
        panel.setContentView_(view)

        target = _AnimTarget.alloc().init()
        interval = max(0.04, 1.0 / max(8.0, FACE_FPS))
        timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            interval,
            target,
            "tickAnim:",
            None,
            True,
        )

        # Do not orderFront here — apply_status decides visibility (avoids flash-then-hide).
        self.panel = panel
        self.view = view
        self._timer = timer
        self._timer_target = target
        self._NSBezierPath = NSBezierPath
        self._NSColor = NSColor
        self._NSFont = NSFont
        self._NSMakeRect = NSMakeRect
        self._NSString = NSString
        self.apply_status(read_status())

    def _cocoa_frame(self):
        from AppKit import NSMakeRect, NSScreen  # type: ignore

        screens = list(NSScreen.screens() or [])
        if not screens:
            return NSMakeRect(100, 700, float(FACE_WIDTH), float(FACE_HEIGHT))
        main = NSScreen.mainScreen() or screens[0]
        vis = main.visibleFrame()
        width = min(float(FACE_WIDTH), max(64.0, vis.size.width - 40.0))
        height = min(float(FACE_HEIGHT), max(56.0, vis.size.height - 40.0))
        x = vis.origin.x + (vis.size.width - width) / 2.0
        y = vis.origin.y + vis.size.height - height - float(FACE_MARGIN_TOP)
        return NSMakeRect(x, y, width, height)

    def _draw_text(self, text: str, x: float, y: float, font, color) -> None:
        NSString = self._NSString
        if NSString is None:
            return
        s = NSString.stringWithString_(text)
        s.drawAtPoint_withAttributes_((x, y), {"NSFont": font, "NSColor": color})

    def _draw(self, view) -> None:
        NSBezierPath = self._NSBezierPath
        NSColor = self._NSColor
        NSFont = self._NSFont
        if NSBezierPath is None or NSColor is None:
            return

        bounds = view.bounds()
        w = float(bounds.size.width)
        h = float(bounds.size.height)
        t = time.monotonic() - self._t0
        mood = self._mood

        pad = 6.0
        card = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            self._NSMakeRect(pad, pad, w - 2 * pad, h - 2 * pad),
            22.0,
            22.0,
        )
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.08, 0.10, 0.16, 0.82).setFill()
        card.fill()
        card.setClip()

        # Eyes only (centered). Flipped coords: +y is down.
        cx = w / 2.0
        eye_y = h * 0.50
        eye_dx = min(22.0, w * 0.16)
        eye_r = min(9.0, w * 0.07)

        if mood == "sleep":
            NSColor.colorWithCalibratedWhite_alpha_(0.92, 0.95).setStroke()
            for side in (-1.0, 1.0):
                path = NSBezierPath.bezierPath()
                path.setLineWidth_(2.4)
                path.setLineCapStyle_(1)
                ex = cx + side * eye_dx
                path.moveToPoint_((ex - eye_r, eye_y))
                path.curveToPoint_controlPoint1_controlPoint2_(
                    (ex + eye_r, eye_y),
                    (ex - eye_r * 0.3, eye_y + 3.5),
                    (ex + eye_r * 0.3, eye_y + 3.5),
                )
                path.stroke()
            try:
                font = NSFont.systemFontOfSize_weight_(13.0, 0.4)
            except Exception:
                font = NSFont.systemFontOfSize_(13.0)
            for i, ch in enumerate("zzz"):
                phase = t * 1.3 + i * 0.85
                zx = cx + 28.0 + i * 9.0 + 2.0 * math.sin(phase)
                zy = eye_y - 18.0 - i * 11.0 - 4.0 * abs(math.sin(phase * 0.7))
                alpha = 0.35 + 0.45 * (0.5 + 0.5 * math.sin(phase))
                color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    0.55, 0.75, 1.0, alpha
                )
                self._draw_text(ch, zx, zy, font, color)
            return

        blink = 0.0
        if mood == "think":
            # Thoughtful blink loop: mostly open, blink ~every 2.6s (with a
            # quick double-blink sometimes).
            period = 2.6
            phase = t % period
            if phase < 0.08:
                blink = phase / 0.08
            elif phase < 0.16:
                blink = 1.0 - (phase - 0.08) / 0.08
            elif 0.38 <= phase < 0.45:
                blink = (phase - 0.38) / 0.07
            elif 0.45 <= phase < 0.52:
                blink = 1.0 - (phase - 0.45) / 0.07
            else:
                blink = 0.0
        elif mood == "listen":
            blink = max(0.0, math.sin(t * 1.4) ** 30)
        # Speaking: soft pulse on eye size instead of a mouth.
        speak_pulse = 1.0
        if mood == "speak":
            speak_pulse = 1.0 + 0.12 * abs(math.sin(t * 10.0))
        eye_h = max(1.5, eye_r * speak_pulse * (1.0 - 0.92 * blink))
        eye_w = eye_r * speak_pulse
        look_x = 0.0
        look_y = 0.0
        pupil_dx = 0.0
        pupil_dy = 0.0
        if mood == "think":
            # Gaze upward (flipped coords: smaller y) and slightly aside.
            look_x = 1.2 + 0.6 * math.sin(t * 0.35)
            look_y = -2.8 + 0.35 * math.sin(t * 0.5)
            pupil_dx = look_x * 0.4
            pupil_dy = look_y * 0.55
        elif mood == "listen":
            look_y = -0.8
            pupil_dy = look_y * 0.3
        elif mood == "speak":
            look_y = 0.6 * math.sin(t * 8.0)
            pupil_dy = look_y * 0.25

        for side in (-1.0, 1.0):
            ex = cx + side * eye_dx + look_x * 0.15
            ey = eye_y + look_y * 0.15
            NSColor.colorWithCalibratedWhite_alpha_(0.95, 0.98).setFill()
            white = NSBezierPath.bezierPathWithOvalInRect_(
                self._NSMakeRect(ex - eye_w, ey - eye_h, eye_w * 2, eye_h * 2)
            )
            white.fill()
            if eye_h > 2.0:
                NSColor.colorWithCalibratedRed_green_blue_alpha_(0.15, 0.55, 0.95, 1.0).setFill()
                pr = min(3.4, eye_w * 0.45)
                pupil = NSBezierPath.bezierPathWithOvalInRect_(
                    self._NSMakeRect(
                        ex - pr + pupil_dx,
                        ey - pr + pupil_dy,
                        pr * 2,
                        pr * 2,
                    )
                )
                pupil.fill()
                NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.9).setFill()
                highlight = NSBezierPath.bezierPathWithOvalInRect_(
                    self._NSMakeRect(
                        ex - 1.2 + pupil_dx * 0.3,
                        ey - pr - 0.5 + pupil_dy * 0.3,
                        2.4,
                        2.4,
                    )
                )
                highlight.fill()

        if mood == "think":
            try:
                font = NSFont.systemFontOfSize_weight_(11.0, 0.5)
            except Exception:
                font = NSFont.systemFontOfSize_(11.0)
            for i in range(3):
                on = int(t * 2.5 + i) % 3 == 0
                alpha = 0.9 if on else 0.25
                self._draw_text(
                    "·",
                    cx + 26.0 + i * 7.0,
                    eye_y - 28.0,
                    font,
                    NSColor.colorWithCalibratedWhite_alpha_(0.9, alpha),
                )

    def hide(self) -> None:
        if self.panel is not None:
            self.panel.orderOut_(None)

    def show(self) -> None:
        if self.panel is None:
            return
        try:
            self.panel.setFrame_display_(self._cocoa_frame(), False)
        except Exception:
            pass
        try:
            self.panel.orderFrontRegardless()
        except Exception:
            pass

    def destroy(self) -> None:
        timer = self._timer
        self._timer = None
        self._timer_target = None
        if timer is not None:
            try:
                timer.invalidate()
            except Exception:
                pass
        panel = self.panel
        self.panel = None
        self.view = None
        if panel is None:
            return
        try:
            panel.orderOut_(None)
        except Exception:
            pass
        try:
            panel.setReleasedWhenClosed_(True)
            panel.close()
        except Exception:
            pass

    def apply_status(self, data: dict[str, Any]) -> None:
        if self.panel is None:
            return
        mood = face_mood_for_state(str(data.get("state") or "idle"), data)
        if mood != self._mood:
            self._mood = mood
            if mood == "listen":
                self._t0 = time.monotonic()
        if not face_should_show(data):
            self.hide()
            return
        self.show()
        if self.view is not None:
            try:
                self.view.setNeedsDisplay_(True)
            except Exception:
                pass
