"""Live per-monitor window occupancy for agent context.

On macOS, Quartz window bounds are matched to ``list_monitors()`` geometry so
the computer-use agent knows what is already open on each display. The same
snapshot is stored under ``memory/apps/displays.md``.
"""

from __future__ import annotations

import sys
from typing import Any

_SKIP_OWNERS = {
    "window server",
    "dock",
    "control center",
    "notification centre",
    "notification center",
    "systemuiservice",
    "spotlight",
    "wallpaper",
    "loginwindow",
    "screenshot",
    "cursoruiviewservice",
    "item-count",
    "wifi",
    "clock",
    "controlcentre",
}

_MAX_WINDOWS_PER_MONITOR = 8
_MIN_WINDOW_PX = 80


def _cg_window_list() -> list[dict[str, Any]]:
    if sys.platform != "darwin":
        return []
    try:
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListExcludeDesktopElements,
            kCGWindowListOptionOnScreenOnly,
        )
    except ImportError:
        return []
    raw = CGWindowListCopyWindowInfo(
        kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
        kCGNullWindowID,
    )
    return [dict(item) for item in (raw or [])]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def window_center_in_desktop(
    bounds: dict[str, Any],
    monitors: list[dict],
) -> tuple[float, float] | None:
    """Map a CGWindow bounds dict into ``list_monitors()`` top-left desktop space."""
    if not monitors:
        return None
    x = _num(bounds.get("X", bounds.get("x")))
    y = _num(bounds.get("Y", bounds.get("y")))
    w = _num(bounds.get("Width", bounds.get("width")))
    h = _num(bounds.get("Height", bounds.get("height")))
    if w < 1 or h < 1:
        return None
    main = next((m for m in monitors if m.get("main")), monitors[0])
    # CGWindow origin is the top-left of the main display.
    return x + main["x"] + w / 2.0, y + main["y"] + h / 2.0


def monitor_containing_point(
    x: float,
    y: float,
    monitors: list[dict],
) -> dict | None:
    for m in monitors:
        if m["x"] <= x < m["x"] + m["width"] and m["y"] <= y < m["y"] + m["height"]:
            return m
    best = None
    best_d = None
    for m in monitors:
        cx = m["x"] + m["width"] / 2.0
        cy = m["y"] + m["height"] / 2.0
        d = (cx - x) ** 2 + (cy - y) ** 2
        if best_d is None or d < best_d:
            best, best_d = m, d
    return best


def _window_layer(info: dict[str, Any]) -> int:
    for key in ("kCGWindowLayer", "Layer"):
        if key in info:
            try:
                return int(info[key])
            except (TypeError, ValueError):
                return -1
    return 0


def _window_owner(info: dict[str, Any]) -> str:
    for key in ("kCGWindowOwnerName", "OwnerName"):
        val = info.get(key)
        if val:
            return str(val).strip()
    return ""


def _window_title(info: dict[str, Any]) -> str:
    for key in ("kCGWindowName", "Name"):
        val = info.get(key)
        if val:
            return str(val).strip()
    return ""


def _as_mapping(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    try:
        return dict(value)
    except (TypeError, ValueError):
        return None


def _window_bounds(info: dict[str, Any]) -> dict[str, Any] | None:
    return _as_mapping(info.get("kCGWindowBounds") or info.get("Bounds"))


def _keep_window(info: dict[str, Any]) -> bool:
    if _window_layer(info) != 0:
        return False
    owner = _window_owner(info)
    if not owner or owner.lower() in _SKIP_OWNERS:
        return False
    bounds = _window_bounds(info)
    if not bounds:
        return False
    w = _num(bounds.get("Width", bounds.get("width")))
    h = _num(bounds.get("Height", bounds.get("height")))
    return w >= _MIN_WINDOW_PX and h >= _MIN_WINDOW_PX


def assign_windows_to_monitors(
    windows: list[dict[str, Any]],
    monitors: list[dict],
) -> list[dict[str, Any]]:
    """Return occupancy records: monitor index/name plus app/title/area."""
    rows: list[dict[str, Any]] = []
    for info in windows:
        if not _keep_window(info):
            continue
        bounds = _window_bounds(info)
        if bounds is None:
            continue
        center = window_center_in_desktop(bounds, monitors)
        if center is None:
            continue
        mon = monitor_containing_point(center[0], center[1], monitors)
        if mon is None:
            continue
        w = _num(bounds.get("Width", bounds.get("width")))
        h = _num(bounds.get("Height", bounds.get("height")))
        owner = _window_owner(info)
        title = _window_title(info)
        rows.append(
            {
                "monitor_index": mon["index"],
                "monitor_name": mon["name"],
                "main": bool(mon.get("main")),
                "app": owner,
                "title": title,
                "area": w * h,
            }
        )
    rows.sort(key=lambda r: (r["monitor_index"], -r["area"]))
    return rows


def list_windows_by_monitor(
    *,
    monitors: list[dict] | None = None,
    windows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if monitors is None:
        from actions import list_monitors

        monitors = list_monitors()
    raw = windows if windows is not None else _cg_window_list()
    return assign_windows_to_monitors(raw, monitors)


def _frontmost_name() -> str:
    try:
        from accessibility import frontmost_app_name

        return (frontmost_app_name() or "").strip()
    except Exception:
        return ""


def format_monitor_occupancy(
    *,
    monitors: list[dict] | None = None,
    occupancy: list[dict[str, Any]] | None = None,
    frontmost: str | None = None,
) -> str:
    """Compact per-display window list for the model prompt."""
    if monitors is None:
        from actions import list_monitors

        monitors = list_monitors()
    if occupancy is None:
        occupancy = list_windows_by_monitor(monitors=monitors)
    if frontmost is None:
        frontmost = _frontmost_name()

    lines = [f"Open windows by display ({len(monitors)} attached):"]
    by_index: dict[int, list[dict[str, Any]]] = {m["index"]: [] for m in monitors}
    for row in occupancy:
        by_index.setdefault(row["monitor_index"], []).append(row)

    for m in monitors:
        role = "main / primary" if m.get("main") else "secondary"
        lines.append(f"  [{m['index']}] {m['name']} ({role}):")
        seen: set[tuple[str, str]] = set()
        count = 0
        for row in by_index.get(m["index"], []):
            key = (row["app"], row["title"])
            if key in seen:
                continue
            seen.add(key)
            label = row["app"]
            if row["title"] and row["title"] != row["app"]:
                title = row["title"]
                if len(title) > 80:
                    title = title[:77] + "…"
                label = f"{row['app']} — {title}"
            lines.append(f"    - {label}")
            count += 1
            if count >= _MAX_WINDOWS_PER_MONITOR:
                extra = len(by_index.get(m["index"], [])) - count
                if extra > 0:
                    lines.append(f"    - … {extra} more")
                break
        if count == 0:
            lines.append("    - (no regular windows)")

    if frontmost and frontmost.lower() not in _SKIP_OWNERS:
        lines.append(f"Frontmost app: {frontmost}")
    if len(monitors) > 1:
        lines.append(
            "Screenshots and click coordinates are the primary display only. "
            "If the target app is already on another monitor, move the pointer "
            "there or activate that window instead of searching the primary screenshot."
        )
    return "\n".join(lines)


def remember_monitor_layout(
    *,
    memory_dir=None,
    occupancy_text: str | None = None,
    monitors: list[dict] | None = None,
) -> str:
    """Snapshot occupancy, persist to memory/apps/displays.md, return the text."""
    text = occupancy_text if occupancy_text is not None else format_monitor_occupancy(monitors=monitors)
    try:
        from memory import write_condensed_memory

        body = "# app / displays\n\n" "Last seen desktop layout (updated automatically):\n\n" f"{text}\n"
        write_condensed_memory("app", "displays", body, memory_dir=memory_dir)
    except Exception as e:
        print(f"[displays] could not save layout memory: {e}", flush=True)
    return text
