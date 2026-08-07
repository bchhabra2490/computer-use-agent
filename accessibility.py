"""
macOS Accessibility (AX) helpers — read on-screen UI text without screenshots.

Requires System Settings → Privacy & Security → Accessibility for the terminal/IDE.
Many Electron/WebGL/CAD apps expose little or no AX tree; fall back to screenshots then.
"""

from __future__ import annotations

import os
import sys
from typing import Any

MAX_NODES = int(os.environ.get("AX_MAX_NODES", "400"))
MAX_DEPTH = int(os.environ.get("AX_MAX_DEPTH", "12"))
MAX_CHARS = int(os.environ.get("AX_MAX_CHARS", "12000"))

# Roles that usually carry useful text / are interactive.
_INTERESTING_ROLES = {
    "AXButton",
    "AXCheckBox",
    "AXRadioButton",
    "AXPopUpButton",
    "AXComboBox",
    "AXTextField",
    "AXTextArea",
    "AXStaticText",
    "AXLink",
    "AXMenuItem",
    "AXMenuButton",
    "AXTab",
    "AXTabGroup",
    "AXCell",
    "AXRow",
    "AXColumn",
    "AXHeading",
    "AXList",
    "AXOutline",
    "AXTable",
    "AXImage",
    "AXToolbar",
    "AXGroup",
    "AXScrollArea",
    "AXWindow",
    "AXWebArea",
}


def accessibility_available() -> tuple[bool, str]:
    if sys.platform != "darwin":
        return False, "Accessibility UI text is only supported on macOS."
    try:
        from ApplicationServices import AXIsProcessTrusted
    except ImportError:
        return (
            False,
            "Missing pyobjc ApplicationServices. Install: "
            "pip install pyobjc-framework-ApplicationServices",
        )
    if not AXIsProcessTrusted():
        return (
            False,
            "Accessibility permission not granted. Enable it for this terminal/IDE in "
            "System Settings → Privacy & Security → Accessibility, then restart.",
        )
    return True, "ok"


def _ax_get(element, attr: str):
    from ApplicationServices import AXUIElementCopyAttributeValue, kAXErrorSuccess

    err, value = AXUIElementCopyAttributeValue(element, attr, None)
    if err != kAXErrorSuccess:
        return None
    return value


def _ax_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value).strip()


def _ax_frame(element) -> tuple[float, float, float, float] | None:
    """Return (x, y, w, h) in Cocoa screen points if available."""
    from ApplicationServices import (
        AXValueGetType,
        AXValueGetValue,
        kAXValueCGPointType,
        kAXValueCGSizeType,
        kAXValueCGRectType,
    )
    import Quartz

    pos = _ax_get(element, "AXPosition")
    size = _ax_get(element, "AXSize")
    if pos is not None and size is not None:
        try:
            pt = Quartz.CGPoint()
            sz = Quartz.CGSize()
            if AXValueGetType(pos) == kAXValueCGPointType:
                AXValueGetValue(pos, kAXValueCGPointType, pt)
            if AXValueGetType(size) == kAXValueCGSizeType:
                AXValueGetValue(size, kAXValueCGSizeType, sz)
            return float(pt.x), float(pt.y), float(sz.width), float(sz.height)
        except Exception:
            pass

    frame = _ax_get(element, "AXFrame")
    if frame is not None:
        try:
            rect = Quartz.CGRect()
            if AXValueGetType(frame) == kAXValueCGRectType:
                AXValueGetValue(frame, kAXValueCGRectType, rect)
                return (
                    float(rect.origin.x),
                    float(rect.origin.y),
                    float(rect.size.width),
                    float(rect.size.height),
                )
        except Exception:
            pass
    return None


def _frontmost_app():
    from AppKit import NSWorkspace

    return NSWorkspace.sharedWorkspace().frontmostApplication()


def _find_app(name_or_bundle: str | None):
    """Match by localized name or bundle id (case-insensitive substring / exact)."""
    from AppKit import NSWorkspace

    if not name_or_bundle:
        return _frontmost_app()

    needle = name_or_bundle.strip().lower()
    apps = list(NSWorkspace.sharedWorkspace().runningApplications())
    # Prefer exact localized name, then bundle id, then substring.
    for app in apps:
        name = (app.localizedName() or "").lower()
        if name == needle:
            return app
    for app in apps:
        bid = (app.bundleIdentifier() or "").lower()
        if bid == needle:
            return app
    for app in apps:
        name = (app.localizedName() or "").lower()
        bid = (app.bundleIdentifier() or "").lower()
        if needle in name or needle in bid:
            return app
    return None


def _collect_lines(
    element,
    *,
    depth: int,
    max_depth: int,
    max_nodes: int,
    state: dict,
    lines: list[str],
) -> None:
    if state["nodes"] >= max_nodes or depth > max_depth:
        return

    role = _ax_str(_ax_get(element, "AXRole")) or "AXUnknown"
    title = _ax_str(_ax_get(element, "AXTitle"))
    value = _ax_str(_ax_get(element, "AXValue"))
    desc = _ax_str(_ax_get(element, "AXDescription"))
    label = _ax_str(_ax_get(element, "AXLabel"))
    help_text = _ax_str(_ax_get(element, "AXHelp"))
    role_desc = _ax_str(_ax_get(element, "AXRoleDescription"))

    text_bits = [t for t in (title, value, desc, label, help_text) if t]
    # Always emit windows / interesting roles; emit others only if they have text.
    interesting = role in _INTERESTING_ROLES or bool(text_bits)
    if interesting and (text_bits or role in {"AXWindow", "AXButton", "AXTextField", "AXTextArea", "AXStaticText", "AXLink", "AXMenuItem"}):
        state["nodes"] += 1
        indent = "  " * depth
        parts = [f"[{role}]"]
        if role_desc and role_desc.lower() not in {role.lower().removeprefix("ax")}:
            parts.append(f"({role_desc})")
        if title:
            parts.append(f'title="{title}"')
        if value and value != title:
            # Truncate huge text fields.
            v = value if len(value) <= 500 else value[:500] + "…"
            parts.append(f'value="{v}"')
        if desc and desc not in {title, value}:
            parts.append(f'desc="{desc}"')
        if label and label not in {title, value, desc}:
            parts.append(f'label="{label}"')
        frame = _ax_frame(element)
        if frame and role in {
            "AXButton",
            "AXCheckBox",
            "AXRadioButton",
            "AXTextField",
            "AXTextArea",
            "AXLink",
            "AXMenuItem",
            "AXPopUpButton",
            "AXComboBox",
            "AXTab",
            "AXImage",
            "AXStaticText",
        }:
            x, y, w, h = frame
            cx, cy = x + w / 2, y + h / 2
            parts.append(f"center=({cx:.0f},{cy:.0f})")
        lines.append(indent + " ".join(parts))

    children = _ax_get(element, "AXChildren") or []
    # Some containers expose contents instead of / in addition to children.
    contents = _ax_get(element, "AXContents")
    kids = list(children) if children else []
    if contents:
        try:
            for c in list(contents):
                if c not in kids:
                    kids.append(c)
        except TypeError:
            pass

    for child in kids:
        if state["nodes"] >= max_nodes:
            break
        _collect_lines(
            child,
            depth=depth + 1,
            max_depth=max_depth,
            max_nodes=max_nodes,
            state=state,
            lines=lines,
        )


def read_ui_text(
    *,
    app: str | None = None,
    max_depth: int | None = None,
    max_nodes: int | None = None,
    max_chars: int | None = None,
) -> str:
    """
    Dump a compact accessibility text tree for the frontmost (or named) app.

    Returns a plain-text report the agent can read instead of OCR'ing a screenshot.
    """
    ok, msg = accessibility_available()
    if not ok:
        return f"Error: {msg}"

    from ApplicationServices import AXUIElementCreateApplication

    target = _find_app(app)
    if target is None:
        return f"Error: no running app matched {app!r}."

    name = target.localizedName() or "Unknown"
    bid = target.bundleIdentifier() or ""
    pid = int(target.processIdentifier())
    root = AXUIElementCreateApplication(pid)

    depth = MAX_DEPTH if max_depth is None else max(1, int(max_depth))
    nodes = MAX_NODES if max_nodes is None else max(10, int(max_nodes))
    chars = MAX_CHARS if max_chars is None else max(500, int(max_chars))

    lines: list[str] = [
        f"App: {name}" + (f" ({bid})" if bid else "") + f" pid={pid}",
        "Coordinates are Cocoa screen points (top-left origin); centers are for clicking hints.",
        "",
    ]
    state = {"nodes": 0}

    focused = _ax_get(root, "AXFocusedUIElement")
    if focused is not None:
        role = _ax_str(_ax_get(focused, "AXRole"))
        title = _ax_str(_ax_get(focused, "AXTitle"))
        value = _ax_str(_ax_get(focused, "AXValue"))
        bits = [b for b in (role, title, value) if b]
        if bits:
            lines.append("Focused: " + " | ".join(bits)[:300])
            lines.append("")

    windows = _ax_get(root, "AXWindows") or []
    main = _ax_get(root, "AXMainWindow")
    ordered = []
    if main is not None:
        ordered.append(main)
    for w in list(windows):
        if w not in ordered:
            ordered.append(w)

    if not ordered:
        # Some apps only expose the app element tree.
        _collect_lines(
            root,
            depth=0,
            max_depth=depth,
            max_nodes=nodes,
            state=state,
            lines=lines,
        )
    else:
        for w in ordered:
            if state["nodes"] >= nodes:
                break
            _collect_lines(
                w,
                depth=0,
                max_depth=depth,
                max_nodes=nodes,
                state=state,
                lines=lines,
            )

    if state["nodes"] == 0:
        lines.append(
            "(No accessibility text nodes found. This app may be Electron/WebGL/custom-drawn "
            "and not expose an AX tree — use screenshots instead.)"
        )

    text = "\n".join(lines)
    if len(text) > chars:
        text = text[:chars] + "\n… (truncated)"
    return text
