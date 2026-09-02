"""AppKit window and animation controller for the face overlay.

The blobatar model, mood mapping, and rendering math live in :mod:`face_overlay`;
this module owns only the macOS panel lifecycle and drawing surface.
"""

from __future__ import annotations

import math
import os
import time
from typing import Any

from face_overlay import (
    FACE_FPS,
    FACE_HEIGHT,
    FACE_MARGIN_TOP,
    FACE_WIDTH,
    BlobatarSpec,
    blob_outline_points,
    current_blobatar,
    face_mood_for_state,
    face_should_show,
    hsl_to_rgb,
    mood_eye_pose,
    read_status,
    resolve_blobatar,
)


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
        self._NSMakeRect = None
        self._NSAffineTransform = None
        self._preset_id = current_blobatar().id
        self._build()

    def _build(self) -> None:
        import objc
        from AppKit import (  # type: ignore
            NSAffineTransform,
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
            NSWindowStyleMaskBorderless,
            NSWindowStyleMaskNonactivatingPanel,
        )
        from Foundation import NSTimer  # type: ignore

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
        self._NSMakeRect = NSMakeRect
        self._NSAffineTransform = NSAffineTransform
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

    def _body_path(self, cx: float, cy: float, rx: float, ry: float, spec: BlobatarSpec):
        NSBezierPath = self._NSBezierPath
        NSMakeRect = self._NSMakeRect
        kind = spec.shape
        if kind == "round":
            path = NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(cx - rx, cy - ry, rx * 2.0, ry * 2.0)
            )
        elif kind in {"boxy", "capsule"}:
            rad = min(rx, ry) * (0.95 if kind == "capsule" else 0.28)
            path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(cx - rx, cy - ry, rx * 2.0, ry * 2.0),
                rad,
                rad,
            )
        else:
            path = self._closed_spline(
                blob_outline_points(
                    cx,
                    cy,
                    rx,
                    ry,
                    n=max(3, len(spec.perturb)),
                    perturb=spec.perturb,
                )
            )
        if abs(spec.rot) > 0.2:
            xf = self._NSAffineTransform.transform()
            xf.translateXBy_yBy_(cx, cy)
            xf.rotateByDegrees_(spec.rot)
            xf.translateXBy_yBy_(-cx, -cy)
            path.transformUsingAffineTransform_(xf)
        return path

    def _closed_spline(self, points: list[tuple[float, float]]):
        NSBezierPath = self._NSBezierPath
        n = len(points)
        path = NSBezierPath.bezierPath()
        path.moveToPoint_(points[0])
        for i in range(n):
            p0 = points[(i - 1) % n]
            p1 = points[i]
            p2 = points[(i + 1) % n]
            p3 = points[(i + 2) % n]
            c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
            c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
            path.curveToPoint_controlPoint1_controlPoint2_(p2, c1, c2)
        path.closePath()
        return path

    def _fill_capsule(
        self,
        cx: float,
        cy: float,
        hw: float,
        hh: float,
        tilt_deg: float,
        color,
    ) -> None:
        NSBezierPath = self._NSBezierPath
        NSMakeRect = self._NSMakeRect
        if hw <= 0.4 or hh <= 0.4:
            return
        rect = NSMakeRect(cx - hw, cy - hh, hw * 2.0, hh * 2.0)
        rad = min(hw, hh)
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, rad, rad)
        if abs(tilt_deg) > 0.2:
            xf = self._NSAffineTransform.transform()
            xf.translateXBy_yBy_(cx, cy)
            xf.rotateByDegrees_(tilt_deg)
            xf.translateXBy_yBy_(-cx, -cy)
            path.transformUsingAffineTransform_(xf)
        color.setFill()
        path.fill()

    def _draw(self, view) -> None:
        NSBezierPath = self._NSBezierPath
        NSColor = self._NSColor
        NSMakeRect = self._NSMakeRect
        if NSBezierPath is None or NSColor is None or NSMakeRect is None:
            return

        bounds = view.bounds()
        w = float(bounds.size.width)
        h = float(bounds.size.height)
        t = time.monotonic() - self._t0
        spec = resolve_blobatar(self._preset_id) or current_blobatar()
        pose = mood_eye_pose(self._mood, t)

        cx = w / 2.0
        cy = h / 2.0 + pose["body_dy"]
        span = min(w, h)
        rx = span * spec.rx * pose["body_scale"]
        ry = span * spec.ry * pose["body_scale"]

        hue = spec.hue + pose["hue_shift"]
        env_hue = (os.environ.get("FACE_OVERLAY_HUE") or "").strip()
        if env_hue:
            try:
                hue = float(env_hue) + pose["hue_shift"]
            except ValueError:
                pass
        br, bg, bb = hsl_to_rgb(hue, spec.sat, pose["light"])
        lum = 0.2126 * br + 0.7152 * bg + 0.0722 * bb
        if lum > 0.45:
            er, eg, eb = 0.12, 0.13, 0.16
        else:
            er, eg, eb = 0.96, 0.97, 0.98

        # Soft ground shadow (keeps the pebble readable on light desktops).
        shadow = NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(cx - rx * 0.72, cy + ry * 0.55, rx * 1.44, ry * 0.38)
        )
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.08, 0.10, 0.14, 0.22).setFill()
        shadow.fill()

        fill = NSColor.colorWithCalibratedRed_green_blue_alpha_(br, bg, bb, 1.0)
        body = self._body_path(cx, cy, rx, ry, spec)
        fill.setFill()
        body.fill()

        rot = spec.rot
        for dx, dy, ew, eh in spec.extras:
            ex = cx + dx * rx
            ey = cy + dy * ry
            if abs(rot) > 0.2:
                ang = math.radians(rot)
                ox, oy = ex - cx, ey - cy
                ex = cx + ox * math.cos(ang) - oy * math.sin(ang)
                ey = cy + ox * math.sin(ang) + oy * math.cos(ang)
            extra = NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(ex - (ew * rx) / 2.0, ey - (eh * ry) / 2.0, ew * rx, eh * ry)
            )
            fill.setFill()
            extra.fill()

        shine = NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(cx - rx * 0.42, cy - ry * 0.62, rx * 0.38, ry * 0.28)
        )
        NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 1.0, 1.0, 0.22).setFill()
        shine.fill()

        eye_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(er, eg, eb, 1.0)
        base_y = cy + ry * (pose["pair_dy"] + spec.pair_dy)
        glance = pose["glance"]
        pair_dx = pose["pair_dx"] + spec.pair_dx - 0.30
        for side, tilt, extra_dy, ew, eh in (
            (-1.0, pose["left_tilt"], pose["left_dy"], pose["left_eye_w"], pose["left_eye_h"]),
            (1.0, pose["right_tilt"], pose["right_dy"], pose["right_eye_w"], pose["right_eye_h"]),
        ):
            ex = cx + side * rx * pair_dx + glance
            ey = base_y + extra_dy * ry
            self._fill_capsule(ex, ey, rx * ew, ry * eh, tilt, eye_color)

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
        preset = current_blobatar(data).id
        if mood != self._mood:
            self._mood = mood
            if mood == "listen":
                self._t0 = time.monotonic()
        self._preset_id = preset
        if not face_should_show(data):
            self.hide()
            return
        self.show()
        if self.view is not None:
            try:
                self.view.setNeedsDisplay_(True)
            except Exception:
                pass
