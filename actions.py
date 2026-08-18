"""
Translates OpenAI computer-use actions into real mouse/keyboard input via pyautogui,
and captures screenshots of the actual desktop.

Handles the Retina/HiDPI coordinate mismatch: on macOS, pyautogui.screenshot() returns
an image at native pixel resolution (e.g. 2880x1800), but pyautogui.moveTo/click expect
logical point coordinates (e.g. 1440x900). All model-generated coordinates are given
relative to the (possibly downscaled) screenshot we send it, so we track two scale
factors and compose them before ever moving the mouse.
"""

import os
import signal
import sys
import threading
import time
import pyautogui

# Safety: pyautogui's fail-safe (slam mouse to a screen corner to abort) stays on.
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


class ActionStopped(Exception):
    """Raised when should_stop() fires mid-batch (wake word / quit)."""


KEY_MAP = {
    "ENTER": "enter",
    "RETURN": "enter",
    "ESC": "esc",
    "ESCAPE": "esc",
    "TAB": "tab",
    "SPACE": "space",
    "BACKSPACE": "backspace",
    "DELETE": "delete",
    "DEL": "delete",
    "HOME": "home",
    "END": "end",
    "PAGEUP": "pageup",
    "PAGEDOWN": "pagedown",
    "UP": "up",
    "ARROWUP": "up",
    "DOWN": "down",
    "ARROWDOWN": "down",
    "LEFT": "left",
    "ARROWLEFT": "left",
    "RIGHT": "right",
    "ARROWRIGHT": "right",
    "CTRL": "ctrl",
    "CONTROL": "ctrl",
    "SHIFT": "shift",
    "OPTION": "option",
    "ALT": "option",
    "META": "command",
    "CMD": "command",
    "COMMAND": "command",
}

# Combos that hit the agent's own terminal (SIGINT / suspend / quit) instead of
# the focused app. Cmd+C (copy) is intentionally allowed.
_BLOCKED_CHORDS = {
    frozenset({"ctrl", "c"}),
    frozenset({"ctrl", "z"}),
    frozenset({"ctrl", "\\"}),
    frozenset({"ctrl", "d"}),
}

# Globe / Fn triggers dictation and emoji UI on modern Mac keyboards.
_BLOCKED_KEYS = frozenset({"fn", "function"})

_MAC_MODIFIER_KEYS = ("command", "shift", "option", "ctrl", "fn")


def _type_mode() -> str:
    """How to inject text for computer-use ``type`` actions."""
    raw = (os.environ.get("CUA_TYPE_MODE") or "").strip().lower()
    if raw in {"unicode", "keys", "paste"}:
        return raw
    return "unicode" if sys.platform == "darwin" else "keys"


def release_stuck_modifiers() -> None:
    """Release common modifiers so the next keys go to the focused field, not shortcuts."""
    for key in _MAC_MODIFIER_KEYS:
        try:
            pyautogui.keyUp(key)
        except Exception:
            pass


def _dismiss_suggestion_overlay() -> None:
    """Best-effort dismiss for browser autocomplete/suggestion dropdowns."""
    try:
        pyautogui.press("esc")
    except Exception:
        pass
    # Let UI react (avoid immediately typing/pressing Enter/Tab into overlay).
    time.sleep(0.02)


def _mac_type_unicode(text: str, *, interval: float = 0.0) -> None:
    """Type via Unicode events — avoids virtual-key shortcuts (dictation, emoji picker)."""
    import Quartz

    for ch in text:
        if ch == "\r":
            continue
        if ch == "\n":
            pyautogui.press("enter")
            if interval:
                time.sleep(interval)
            continue
        if ch == "\t":
            pyautogui.press("tab")
            if interval:
                time.sleep(interval)
            continue
        for key_down in (True, False):
            event = Quartz.CGEventCreateKeyboardEvent(None, 0, key_down)
            Quartz.CGEventKeyboardSetUnicodeString(event, len(ch), ch)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        if interval:
            time.sleep(interval)


def _mac_type_paste(text: str) -> None:
    """Paste via clipboard — fallback when Unicode injection fails in a field."""
    import subprocess

    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
    release_stuck_modifiers()
    pyautogui.hotkey("command", "v")


def type_text(text: str, *, interval: float = 0.01) -> None:
    """Inject text into the focused control."""
    mode = _type_mode()
    if mode == "paste" and sys.platform == "darwin":
        _mac_type_paste(text)
        return
    if mode == "unicode" and sys.platform == "darwin":
        release_stuck_modifiers()
        _mac_type_unicode(text, interval=interval)
        return
    pyautogui.typewrite(text, interval=interval)


def normalize_key(key: str) -> str:
    return KEY_MAP.get(key.upper(), key.lower())


def _is_blocked_chord(keys: list[str]) -> bool:
    return frozenset(keys) in _BLOCKED_CHORDS


def _mac_scroll_pixels(dx: int, dy: int) -> None:
    """
    Post trackpad-like continuous pixel scroll events via Quartz.

    pyautogui's line-based CGScrollEvent is often ignored by browsers/WebKit
    and modern AppKit scroll views. Continuous + scroll-phase events match a
    real trackpad and are accepted.
    """
    import Quartz

    dx = int(dx)
    dy = int(dy)
    if dx == 0 and dy == 0:
        return

    max_step = 80

    def _emit(wx: int, wy: int, phase: int) -> None:
        # wheel1 = vertical, wheel2 = horizontal (pixel units).
        event = Quartz.CGEventCreateScrollWheelEvent(
            None,
            Quartz.kCGScrollEventUnitPixel,
            2,
            wy,
            wx,
        )
        Quartz.CGEventSetIntegerValueField(event, Quartz.kCGScrollWheelEventIsContinuous, 1)
        Quartz.CGEventSetIntegerValueField(event, Quartz.kCGScrollWheelEventScrollPhase, phase)
        Quartz.CGEventSetIntegerValueField(event, Quartz.kCGScrollWheelEventPointDeltaAxis1, wy)
        Quartz.CGEventSetIntegerValueField(event, Quartz.kCGScrollWheelEventPointDeltaAxis2, wx)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    remaining_x, remaining_y = dx, dy
    first = True
    while remaining_x != 0 or remaining_y != 0:
        step_x = max(-max_step, min(max_step, remaining_x))
        step_y = max(-max_step, min(max_step, remaining_y))
        remaining_x -= step_x
        remaining_y -= step_y
        phase = Quartz.kCGScrollPhaseBegan if first else Quartz.kCGScrollPhaseChanged
        first = False
        _emit(step_x, step_y, phase)
        time.sleep(0.008)

    _emit(0, 0, Quartz.kCGScrollPhaseEnded)


def _scroll(dx: int, dy: int) -> None:
    """Scroll by approximate pixel deltas. dy>0 scrolls content up (wheel up)."""
    import sys

    if sys.platform == "darwin":
        _mac_scroll_pixels(dx, dy)
        return
    # Other platforms: pyautogui clicks ≈ lines; scale pixels down.
    if dy:
        pyautogui.scroll(int(round(dy / 40)) or (1 if dy > 0 else -1))
    if dx:
        pyautogui.hscroll(int(round(dx / 40)) or (1 if dx > 0 else -1))


def list_monitors() -> list[dict]:
    """Return attached displays with logical geometry (top-left origin).

    On macOS uses AppKit (names, scale, layout). Falls back to a single
    pyautogui primary display elsewhere.
    """
    try:
        from AppKit import NSScreen
    except ImportError:
        w, h = pyautogui.size()
        return [
            {
                "index": 0,
                "name": "Primary",
                "main": True,
                "x": 0,
                "y": 0,
                "width": w,
                "height": h,
                "scale": 1.0,
                "native_width": w,
                "native_height": h,
            }
        ]

    screens = list(NSScreen.screens())
    main = NSScreen.mainScreen()
    cocoa = []
    for s in screens:
        f = s.frame()
        cocoa.append((f.origin.x, f.origin.y, f.size.width, f.size.height, s))

    min_x = min(c[0] for c in cocoa)
    max_y = max(c[1] + c[3] for c in cocoa)

    monitors = []
    for i, (ox, oy, w, h, s) in enumerate(cocoa):
        scale = float(s.backingScaleFactor())
        name = s.localizedName() if hasattr(s, "localizedName") else f"Display {i}"
        # Cocoa origin is bottom-left; convert to top-left desktop coords.
        monitors.append(
            {
                "index": i,
                "name": name,
                "main": s == main,
                "x": int(round(ox - min_x)),
                "y": int(round(max_y - (oy + h))),
                "width": int(round(w)),
                "height": int(round(h)),
                "scale": scale,
                "native_width": int(round(w * scale)),
                "native_height": int(round(h * scale)),
                "display_id": _ns_display_id(s),
            }
        )
    return monitors


def _ns_display_id(screen) -> int | None:
    """CGDirectDisplayID from an NSScreen, if available."""
    try:
        raw = screen.deviceDescription().objectForKey_("NSScreenNumber")
        if raw is None:
            return None
        return int(raw)
    except Exception:
        return None


def format_display_context(
    monitors: list[dict] | None = None,
    screenshot_size: tuple[int, int] | None = None,
) -> str:
    """Human-readable display summary for the model’s starting context."""
    monitors = monitors if monitors is not None else list_monitors()
    lines = [f"Attached displays ({len(monitors)}):"]
    for m in monitors:
        role = "main / primary" if m["main"] else "secondary"
        lines.append(
            f"  [{m['index']}] {m['name']} ({role}): "
            f"logical {m['width']}x{m['height']} at top-left ({m['x']}, {m['y']}), "
            f"scale {m['scale']:.0f}x, native {m['native_width']}x{m['native_height']}"
        )

    primary = next((m for m in monitors if m["main"]), monitors[0])
    lines.append(
        f"Screenshots and action coordinates are relative to the primary display "
        f"({primary['name']}, {primary['width']}x{primary['height']} logical). "
        f"Other monitors are not in the screenshot."
    )
    if screenshot_size:
        lines.append(
            f"Last / expected screenshot pixel size sent to you: " f"{screenshot_size[0]}x{screenshot_size[1]}."
        )
    return "\n".join(lines)


class DesktopController:
    """Wraps pyautogui with coordinate remapping between screenshot space and
    actual screen (logical point) space."""

    def __init__(self, screenshot_max_width: int = 1568):
        # Logical screen size pyautogui uses for mouse coordinates.
        self.screen_w, self.screen_h = pyautogui.size()
        self.screenshot_max_width = screenshot_max_width
        # Populated on each capture_screenshot() call.
        self._model_w, self._model_h = self.screen_w, self.screen_h

    def _to_screen_coords(self, x: int, y: int) -> tuple[int, int]:
        """Map coordinates the model gave us (relative to the last screenshot we
        sent it) into real logical screen coordinates."""
        scale_x = self.screen_w / self._model_w
        scale_y = self.screen_h / self._model_h
        return round(x * scale_x), round(y * scale_y)

    def capture_screenshot(self) -> bytes:
        """Capture the real screen, downscale for the API, return PNG bytes.
        Records the resulting image size so future action coordinates (which are
        relative to this image) can be remapped correctly."""
        from log_overlay import pause_overlay_for_capture

        with pause_overlay_for_capture():
            img = pyautogui.screenshot()  # native pixel resolution
        if img.width > self.screenshot_max_width:
            ratio = self.screenshot_max_width / img.width
            img = img.resize((self.screenshot_max_width, round(img.height * ratio)))
        self._model_w, self._model_h = img.size

        import io

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def run_actions(self, actions: list, *, should_stop=None) -> None:
        # Synthetic Ctrl+C from the model still delivers SIGINT to this process
        # (the terminal's foreground group). Ignore it for the duration of the
        # batch; user abort remains available via the mouse-corner fail-safe.
        # signal.signal() is main-thread-only — the agent may run in a worker
        # thread under the orchestrator, so skip SIGINT masking there.
        on_main = threading.current_thread() is threading.main_thread()
        prev_sigint = None
        if on_main:
            prev_sigint = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            for action in actions:
                if should_stop is not None and should_stop():
                    raise ActionStopped("stopped before action")
                self._run_one(action, should_stop=should_stop)
        finally:
            if on_main and prev_sigint is not None:
                signal.signal(signal.SIGINT, prev_sigint)

    def _run_one(self, action, *, should_stop=None) -> None:
        # SDK returns Pydantic models (Click, Screenshot, …); accept plain dicts too.
        if not isinstance(action, dict):
            action = action.model_dump() if hasattr(action, "model_dump") else dict(action)

        atype = action["type"]

        if atype == "click":
            x, y = self._to_screen_coords(action["x"], action["y"])
            button = action.get("button", "left")
            keys = [normalize_key(k) for k in action.get("keys") or []]
            try:
                for k in keys:
                    pyautogui.keyDown(k)
                pyautogui.click(x, y, button="right" if button == "right" else "left")
            finally:
                for k in reversed(keys):
                    pyautogui.keyUp(k)

        elif atype == "double_click":
            x, y = self._to_screen_coords(action["x"], action["y"])
            pyautogui.doubleClick(x, y)

        elif atype == "move":
            x, y = self._to_screen_coords(action["x"], action["y"])
            pyautogui.moveTo(x, y)

        elif atype == "scroll":
            x, y = self._to_screen_coords(action["x"], action["y"])
            pyautogui.moveTo(x, y)
            # Model scroll_* are in screenshot pixels. Positive scroll_y means
            # scroll the page down (wheel down) — invert for Quartz/pyautogui
            # where positive dy is wheel-up.
            scroll_y = int(action.get("scroll_y") or 0)
            scroll_x = int(action.get("scroll_x") or 0)
            if scroll_x or scroll_y:
                print(f"[scroll] at ({x},{y}) dx={scroll_x} dy={-scroll_y}")
                _scroll(scroll_x, -scroll_y)
            else:
                print("[scroll] skipped — zero delta")

        elif atype == "keypress":
            keys = [normalize_key(k) for k in action["keys"]]
            if any(k in _BLOCKED_KEYS for k in keys):
                print(f"[skip] blocked keypress {keys} — would trigger system UI")
                return
            if _is_blocked_chord(keys):
                print(f"[skip] blocked keypress {keys} — would interrupt this agent")
                return
            # Chrome form dropdowns often steal Tab/Enter. ESC usually dismisses them.
            if ("tab" in keys or "enter" in keys) and "esc" not in keys:
                _dismiss_suggestion_overlay()
            release_stuck_modifiers()
            if len(keys) > 1:
                pyautogui.hotkey(*keys)
            else:
                pyautogui.press(keys[0])

        elif atype == "type":
            _dismiss_suggestion_overlay()
            release_stuck_modifiers()
            type_text(action["text"], interval=0.01)

        elif atype == "drag":
            path = action["path"]
            if len(path) < 2:
                return

            def point_xy(p):
                if isinstance(p, dict):
                    return p["x"], p["y"]
                if hasattr(p, "x"):
                    return p.x, p.y
                return p[0], p[1]

            start = self._to_screen_coords(*point_xy(path[0]))
            pyautogui.moveTo(*start)
            pyautogui.mouseDown()
            for point in path[1:]:
                x, y = self._to_screen_coords(*point_xy(point))
                pyautogui.moveTo(x, y, duration=0.1)
            pyautogui.mouseUp()

        elif atype == "wait":
            ms = action.get("ms")
            seconds = 2.0 if ms is None else max(0.0, float(ms) / 1000.0)
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                if should_stop is not None and should_stop():
                    raise ActionStopped("stopped during wait")
                time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))

        elif atype == "screenshot":
            pass  # handled by the caller, which always screenshots after a batch

        else:
            raise ValueError(f"Unsupported action type: {atype}")
