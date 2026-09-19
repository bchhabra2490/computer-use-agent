"""
macOS Accessibility (AX) helpers — read on-screen UI text without screenshots.

Requires System Settings → Privacy & Security → Accessibility for the terminal/IDE.
Many Electron/WebGL/CAD apps expose little or no AX tree; fall back to screenshots then.

Also exposes :func:`capture_ui_snapshot` for structured UI trees used by the
optional Jev fast path (step 2). Existing callers of :func:`read_ui_text` and
focused-edit helpers are unchanged.
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from dataclasses import dataclass
from typing import Any

from jev.models import ElementFrame, UIElement, UISnapshot

MAX_NODES = int(os.environ.get("AX_MAX_NODES", "400"))
MAX_DEPTH = int(os.environ.get("AX_MAX_DEPTH", "12"))
MAX_CHARS = int(os.environ.get("AX_MAX_CHARS", "12000"))

_VALUE_MAX = 240
_LABEL_MAX = 120
_DESC_MAX = 160

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

# Prioritized for structured snapshots (lower = keep first when truncating).
_ACTIONABLE_ROLES = {
    "AXButton": 0,
    "AXLink": 1,
    "AXTextField": 2,
    "AXSecureTextField": 2,
    "AXSearchField": 2,
    "AXTextArea": 3,
    "AXCheckBox": 4,
    "AXRadioButton": 5,
    "AXComboBox": 6,
    "AXPopUpButton": 7,
    "AXMenuItem": 8,
    "AXMenuButton": 8,
    "AXTab": 9,
    "AXCell": 10,
    "AXRow": 11,
    "AXHeading": 40,
    "AXStaticText": 50,
}

_STATIC_ROLES = frozenset({"AXStaticText", "AXHeading"})


def accessibility_available() -> tuple[bool, str]:
    if sys.platform != "darwin":
        return False, "Accessibility UI text is only supported on macOS."
    try:
        from ApplicationServices import AXIsProcessTrusted
    except ImportError:
        return (
            False,
            "Missing pyobjc ApplicationServices. Install: " "pip install pyobjc-framework-ApplicationServices",
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


def frontmost_app_name() -> str | None:
    """Localized name of the frontmost macOS app, or None."""
    try:
        app = _frontmost_app()
        if app is None:
            return None
        return (app.localizedName() or "").strip() or None
    except Exception:
        return None


_EDITABLE_ROLES = frozenset(
    {
        "AXTextField",
        "AXTextArea",
        "AXComboBox",
        "AXSearchField",
        "AXWebArea",  # many browsers / Electron focus web area while typing
        "AXGroup",  # contenteditable often surfaces as a group
    }
)


def focused_edit_info() -> dict[str, Any]:
    """Describe the focused UI element for dictation guardrails.

    Returns keys: role, title, secure, editable, app. When Accessibility is
    unavailable, returns editable=True so dictation can still try paste.
    """
    out: dict[str, Any] = {
        "role": "",
        "title": "",
        "secure": False,
        "editable": True,
        "app": frontmost_app_name() or "",
    }
    ok, _msg = accessibility_available()
    if not ok:
        return out
    try:
        app = _frontmost_app()
        if app is None:
            return out
        pid = int(app.processIdentifier())
        root = _create_app_element(pid)
        focused = _ax_get(root, "AXFocusedUIElement")
        if focused is None:
            out["editable"] = False
            return out
        role = _ax_str(_ax_get(focused, "AXRole"))
        subrole = _ax_str(_ax_get(focused, "AXSubrole"))
        title = _ax_str(_ax_get(focused, "AXTitle")) or _ax_str(
            _ax_get(focused, "AXDescription")
        )
        out["role"] = role or subrole
        out["title"] = title
        if role == "AXSecureTextField" or "secure" in (subrole or "").lower():
            out["secure"] = True
            out["editable"] = False
            return out
        # AXTextField / AXTextArea / combo / search — always treat as editable.
        if role in _EDITABLE_ROLES or "Text" in role:
            out["editable"] = True
            return out
        # Some apps expose AXValue + AXFocused without a classic text role.
        if _ax_get(focused, "AXValue") is not None and role not in {
            "AXButton",
            "AXCheckBox",
            "AXRadioButton",
            "AXMenuItem",
            "AXStaticText",
        }:
            out["editable"] = True
            return out
        out["editable"] = False
        return out
    except Exception:
        return out


def replace_focused_inserted_tail(old_tail: str, new_tail: str) -> bool:
    """If the focused field's AXValue ends with ``old_tail``, swap that suffix.

    Used by live dictation when the transcript revises (not just grows).
    Returns True when the value was updated via Accessibility.
    """
    old_tail = old_tail or ""
    new_tail = new_tail or ""
    if old_tail == new_tail:
        return True
    ok, _msg = accessibility_available()
    if not ok:
        return False
    try:
        from ApplicationServices import (
            AXUIElementSetAttributeValue,
            kAXErrorSuccess,
        )

        app = _frontmost_app()
        if app is None:
            return False
        root = _create_app_element(int(app.processIdentifier()))
        focused = _ax_get(root, "AXFocusedUIElement")
        if focused is None:
            return False
        cur = _ax_str(_ax_get(focused, "AXValue"))
        if old_tail:
            if not cur.endswith(old_tail):
                return False
            prefix = cur[: -len(old_tail)]
        else:
            prefix = cur
        err = AXUIElementSetAttributeValue(focused, "AXValue", prefix + new_tail)
        return err == kAXErrorSuccess
    except Exception:
        return False


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


def _create_app_element(pid: int):
    """Build the AX application root for ``pid`` (patched in unit tests)."""
    from ApplicationServices import AXUIElementCreateApplication

    return AXUIElementCreateApplication(pid)


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
    if interesting and (
        text_bits
        or role in {"AXWindow", "AXButton", "AXTextField", "AXTextArea", "AXStaticText", "AXLink", "AXMenuItem"}
    ):
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

    target = _find_app(app)
    if target is None:
        return f"Error: no running app matched {app!r}."

    name = target.localizedName() or "Unknown"
    bid = target.bundleIdentifier() or ""
    pid = int(target.processIdentifier())
    root = _create_app_element(pid)

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


# ---------------------------------------------------------------------------
# Structured UI snapshots (Jev step 2)
# ---------------------------------------------------------------------------


def _bound_text(value: str, limit: int) -> str:
    """Treat AX strings as untrusted: strip controls and bound length."""
    from text_sanitize import sanitize_utf8

    text = sanitize_utf8(_ax_str(value))
    cleaned = "".join(ch if (ch >= " " or ch in "\t\n") else " " for ch in text)
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > limit:
        return cleaned[:limit] + "…"
    return cleaned


def _ax_bool(element, attr: str, default: bool = False) -> bool:
    value = _ax_get(element, attr)
    if value is None:
        return default
    return bool(value)


def _ax_action_names(element) -> tuple[str, ...]:
    """Return supported AX action names; empty on failure."""
    try:
        from ApplicationServices import AXUIElementCopyActionNames, kAXErrorSuccess

        err, names = AXUIElementCopyActionNames(element, None)
        if err == kAXErrorSuccess and names:
            out = tuple(_ax_str(n) for n in list(names) if _ax_str(n))
            if out:
                return out
    except Exception:
        pass
    raw = _ax_get(element, "AXActions")
    if not raw:
        return ()
    try:
        return tuple(_ax_str(n) for n in list(raw) if _ax_str(n))
    except TypeError:
        return ()


def _is_sensitive_role(role: str, subrole: str = "") -> bool:
    role_l = (role or "").lower()
    sub_l = (subrole or "").lower()
    return role == "AXSecureTextField" or "secure" in role_l or "secure" in sub_l


def _role_priority(role: str, actions: tuple[str, ...]) -> int | None:
    if role in _ACTIONABLE_ROLES:
        return _ACTIONABLE_ROLES[role]
    if actions:
        return 30
    if role in _STATIC_ROLES:
        return _ACTIONABLE_ROLES.get(role, 50)
    return None


def _should_include_element(
    *,
    role: str,
    label: str,
    value: str,
    description: str,
    actions: tuple[str, ...],
    focused: bool,
) -> bool:
    if focused:
        return True
    priority = _role_priority(role, actions)
    if priority is None:
        return False
    if role in _STATIC_ROLES:
        return bool(label or value or description)
    return True


def _opaque_element_id(
    *,
    role: str,
    label: str,
    frame: ElementFrame | None,
    path: tuple[int, ...],
    sensitive: bool,
) -> str:
    """Deterministic opaque id — no raw memory addresses."""
    frame_part = ""
    if frame is not None:
        frame_part = (
            f"{round(frame.x)}:{round(frame.y)}:"
            f"{round(frame.width)}:{round(frame.height)}"
        )
    material = "|".join(
        (
            role,
            label,
            frame_part,
            ".".join(str(p) for p in path),
            "s" if sensitive else "p",
        )
    )
    digest = hashlib.blake2b(material.encode("utf-8"), digest_size=6).hexdigest()
    return f"ax_{digest}"


def _element_fingerprint(el: UIElement) -> str:
    frame = ""
    if el.frame is not None:
        f = el.frame
        frame = f"{round(f.x)}:{round(f.y)}:{round(f.width)}:{round(f.height)}"
    return "|".join(
        (
            el.id,
            el.role,
            el.label,
            el.safe_value(),
            el.description,
            "1" if el.enabled else "0",
            "1" if el.focused else "0",
            "1" if el.selected else "0",
            "1" if el.sensitive else "0",
            frame,
            ",".join(el.supported_actions),
        )
    )


def snapshot_revision(
    *,
    app_name: str,
    bundle_id: str,
    window_title: str,
    focused_element_id: str | None,
    elements: tuple[UIElement, ...] | list[UIElement],
) -> int:
    """Stable fingerprint int from safe, relevant public properties."""
    lines = [
        f"app={app_name}",
        f"bundle={bundle_id}",
        f"window={window_title}",
        f"focus={focused_element_id or ''}",
    ]
    lines.extend(_element_fingerprint(el) for el in elements)
    digest = hashlib.blake2b("\n".join(lines).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


@dataclass
class _RawNode:
    handle: Any
    role: str
    label: str
    value: str
    description: str
    enabled: bool
    focused: bool
    selected: bool
    sensitive: bool
    frame: ElementFrame | None
    actions: tuple[str, ...]
    path: tuple[int, ...]
    priority: int


def _child_elements(element) -> list[Any]:
    children = _ax_get(element, "AXChildren") or []
    kids = list(children) if children else []
    contents = _ax_get(element, "AXContents")
    if contents:
        try:
            for child in list(contents):
                if child not in kids:
                    kids.append(child)
        except TypeError:
            pass
    return kids


def _collect_snapshot_nodes(
    element,
    *,
    depth: int,
    max_depth: int,
    path: tuple[int, ...],
    focused_handle: Any,
    visited: int,
    hard_cap: int,
    out: list[_RawNode],
) -> int:
    """Walk the AX tree; ``visited`` counts every inspected node (depth/node limits)."""
    if visited >= hard_cap or depth > max_depth:
        return visited
    visited += 1

    role = _ax_str(_ax_get(element, "AXRole")) or "AXUnknown"
    subrole = _ax_str(_ax_get(element, "AXSubrole"))
    title = _bound_text(_ax_str(_ax_get(element, "AXTitle")), _LABEL_MAX)
    raw_value = _ax_str(_ax_get(element, "AXValue"))
    desc = _bound_text(_ax_str(_ax_get(element, "AXDescription")), _DESC_MAX)
    label_attr = _bound_text(_ax_str(_ax_get(element, "AXLabel")), _LABEL_MAX)
    label = label_attr or title or desc
    sensitive = _is_sensitive_role(role, subrole)
    value = "" if sensitive else _bound_text(raw_value, _VALUE_MAX)
    actions = _ax_action_names(element)
    focused = focused_handle is not None and element is focused_handle
    if not focused:
        # Some trees expose AXFocused on the element itself.
        focused = _ax_bool(element, "AXFocused", default=False)
    enabled = _ax_bool(element, "AXEnabled", default=True)
    selected = _ax_bool(element, "AXSelected", default=False)
    frame_t = _ax_frame(element)
    frame = (
        None
        if frame_t is None
        else ElementFrame(x=frame_t[0], y=frame_t[1], width=frame_t[2], height=frame_t[3])
    )

    if _should_include_element(
        role=role,
        label=label,
        value=value,
        description=desc,
        actions=actions,
        focused=focused,
    ):
        priority = _role_priority(role, actions)
        if priority is None:
            priority = 0 if focused else 99
        out.append(
            _RawNode(
                handle=element,
                role=role,
                label=label,
                value=value,
                description=desc if desc != label else "",
                enabled=enabled,
                focused=focused,
                selected=selected,
                sensitive=sensitive,
                frame=frame,
                actions=actions,
                path=path,
                priority=priority,
            )
        )

    for index, child in enumerate(_child_elements(element)):
        if visited >= hard_cap:
            break
        visited = _collect_snapshot_nodes(
            child,
            depth=depth + 1,
            max_depth=max_depth,
            path=path + (index,),
            focused_handle=focused_handle,
            visited=visited,
            hard_cap=hard_cap,
            out=out,
        )
    return visited


def _ordered_windows(root) -> list[Any]:
    windows = _ax_get(root, "AXWindows") or []
    main = _ax_get(root, "AXMainWindow")
    ordered: list[Any] = []
    if main is not None:
        ordered.append(main)
    try:
        window_list = list(windows)
    except TypeError:
        window_list = []
    for window in window_list:
        if window not in ordered:
            ordered.append(window)
    return ordered


def _window_title(root) -> str:
    main = _ax_get(root, "AXMainWindow")
    if main is not None:
        title = _bound_text(_ax_str(_ax_get(main, "AXTitle")), _LABEL_MAX)
        if title:
            return title
    focused_window = _ax_get(root, "AXFocusedWindow")
    if focused_window is not None:
        title = _bound_text(_ax_str(_ax_get(focused_window, "AXTitle")), _LABEL_MAX)
        if title:
            return title
    return ""


def _maybe_mark_ax_latency(capture_ms: float) -> None:
    """Record capture duration on the active latency trace when one exists."""
    try:
        from latency_report import current_trace_id, mark

        trace_id = current_trace_id()
        if not trace_id:
            return
        mark(
            trace_id,
            "ax_snapshot",
            metadata={"capture_ms": round(capture_ms, 2)},
        )
    except Exception:
        pass


def _select_raw_nodes(raw_nodes: list[_RawNode], nodes: int) -> list[_RawNode]:
    """Keep highest-priority candidates within ``nodes``, always retaining focus."""
    raw_nodes = sorted(raw_nodes, key=lambda n: (n.priority, n.path))
    focused = [n for n in raw_nodes if n.focused]
    chosen: list[_RawNode] = []
    seen: set[int] = set()
    for node in raw_nodes:
        if len(chosen) >= nodes:
            break
        ident = id(node.handle)
        if ident in seen:
            continue
        seen.add(ident)
        chosen.append(node)
    for node in focused:
        ident = id(node.handle)
        if ident in seen:
            continue
        chosen.append(node)
        seen.add(ident)
    chosen.sort(key=lambda n: (n.priority, n.path))
    return chosen


def capture_ui_snapshot(
    *,
    app: str | None = None,
    max_depth: int | None = None,
    max_nodes: int | None = None,
) -> UISnapshot:
    """Capture a structured Accessibility snapshot for the frontmost or named app.

    Returns an empty/unavailable :class:`UISnapshot` (with ``error`` set) when
    Accessibility is missing, the app cannot be found, or traversal fails.
    Never raises for normal startup/agent paths. Native AX handles stay in the
    snapshot's local-only registry and are omitted from public serialization.
    """
    started = time.perf_counter()
    ok, msg = accessibility_available()
    if not ok:
        capture_ms = (time.perf_counter() - started) * 1000.0
        return UISnapshot(error=msg, capture_ms=capture_ms)

    try:
        target = _find_app(app)
        if target is None:
            capture_ms = (time.perf_counter() - started) * 1000.0
            return UISnapshot(
                error=f"no running app matched {app!r}",
                capture_ms=capture_ms,
            )

        name = _bound_text(target.localizedName() or "Unknown", _LABEL_MAX)
        bid = _bound_text(target.bundleIdentifier() or "", _LABEL_MAX)
        pid = int(target.processIdentifier())
        root = _create_app_element(pid)

        depth = MAX_DEPTH if max_depth is None else max(1, int(max_depth))
        nodes = MAX_NODES if max_nodes is None else max(1, int(max_nodes))
        # Walk a bit past the include budget so prioritization can prefer buttons.
        hard_cap = max(nodes * 4, nodes + 50, 64)

        focused_handle = _ax_get(root, "AXFocusedUIElement")
        window_title = _window_title(root)

        raw_nodes: list[_RawNode] = []
        visited = 0
        ordered = _ordered_windows(root)
        roots = ordered if ordered else [root]
        for index, tree_root in enumerate(roots):
            if visited >= hard_cap:
                break
            visited = _collect_snapshot_nodes(
                tree_root,
                depth=0,
                max_depth=depth,
                path=(index,),
                focused_handle=focused_handle,
                visited=visited,
                hard_cap=hard_cap,
                out=raw_nodes,
            )

        unique = _select_raw_nodes(raw_nodes, nodes)

        elements: list[UIElement] = []
        handles: dict[str, Any] = {}
        focused_id: str | None = None
        for node in unique:
            element_id = _opaque_element_id(
                role=node.role,
                label=node.label,
                frame=node.frame,
                path=node.path,
                sensitive=node.sensitive,
            )
            el = UIElement(
                id=element_id,
                role=node.role,
                label=node.label,
                value=node.value,
                description=node.description,
                enabled=node.enabled,
                focused=node.focused,
                selected=node.selected,
                frame=node.frame,
                supported_actions=node.actions,
                sensitive=node.sensitive,
            )
            elements.append(el)
            handles[element_id] = node.handle
            if node.focused:
                focused_id = element_id

        element_tuple = tuple(elements)
        revision = snapshot_revision(
            app_name=name,
            bundle_id=bid,
            window_title=window_title,
            focused_element_id=focused_id,
            elements=element_tuple,
        )
        capture_ms = (time.perf_counter() - started) * 1000.0
        snap = UISnapshot(
            revision=revision,
            app_name=name,
            bundle_id=bid,
            process_id=pid,
            window_title=window_title,
            focused_element_id=focused_id,
            elements=element_tuple,
            capture_ms=capture_ms,
        )
        for element_id, handle in handles.items():
            snap.register_handle(element_id, handle)
        _maybe_mark_ax_latency(capture_ms)
        return snap
    except Exception as exc:
        capture_ms = (time.perf_counter() - started) * 1000.0
        return UISnapshot(
            error=f"accessibility snapshot failed: {type(exc).__name__}",
            capture_ms=capture_ms,
        )


def ax_perform_action(handle: Any, action_name: str) -> bool:
    """Perform a native AX action on a local handle. Returns False on failure."""
    if handle is None or not action_name:
        return False
    try:
        from ApplicationServices import AXUIElementPerformAction, kAXErrorSuccess
    except Exception:
        return False
    try:
        err = AXUIElementPerformAction(handle, action_name)
        return err == kAXErrorSuccess
    except Exception:
        return False
