"""Live per-monitor window occupancy for agent context.

On macOS, Quartz window bounds are matched to ``list_monitors()`` geometry so
the computer-use agent knows what is already open on each display. Running
apps and browser tabs (AppleScript / JXA; browsers are not launched) are
included in the same snapshot. Ephemeral (prompt + ``.runtime/desktop.txt``),
not durable memory.
"""

from __future__ import annotations

import json
import os
import subprocess
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
_MAX_APPS = 40
_MAX_TABS = 40
_MAX_TAB_URL = 90
_MIN_WINDOW_PX = 80
_BROWSER_SCRIPT_TIMEOUT = float(os.environ.get("DESKTOP_TAB_TIMEOUT", "8"))


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


def frontmost_window_info(
    app: str,
    *,
    windows: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """First on-screen layer-0 window for ``app`` (CG list is front-to-back)."""
    needle = (app or "").strip().lower()
    if not needle:
        return None
    raw = windows if windows is not None else _cg_window_list()
    for info in raw:
        if not _keep_window(info):
            continue
        if _window_owner(info).lower() == needle:
            return info
    return None


def monitor_for_window(
    info: dict[str, Any],
    monitors: list[dict],
) -> dict | None:
    bounds = _window_bounds(info)
    if bounds is None:
        return None
    center = window_center_in_desktop(bounds, monitors)
    if center is None:
        return None
    return monitor_containing_point(center[0], center[1], monitors)


def monitor_for_app_window(
    app: str,
    *,
    windows: list[dict[str, Any]] | None = None,
    monitors: list[dict] | None = None,
) -> dict | None:
    """Display that currently holds ``app``'s frontmost window."""
    info = frontmost_window_info(app, windows=windows)
    if info is None:
        return None
    if monitors is None:
        from actions import list_monitors

        monitors = list_monitors()
    return monitor_for_window(info, monitors)


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


def list_tabs_enabled() -> bool:
    return os.environ.get("DESKTOP_LIST_TABS", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def list_open_apps() -> list[str]:
    """User-facing running apps (regular activation policy), unique names."""
    if sys.platform != "darwin":
        return []
    try:
        from AppKit import NSWorkspace
    except ImportError:
        return []
    try:
        apps = list(NSWorkspace.sharedWorkspace().runningApplications())
    except Exception:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for app in apps:
        try:
            if int(app.activationPolicy()) != 0:
                continue
        except Exception:
            continue
        name = (app.localizedName() or "").strip()
        if not name or name.lower() in _SKIP_OWNERS:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    names.sort(key=str.lower)
    return names[:_MAX_APPS]


_BROWSER_TABS_JXA = r"""
function run() {
  const chromeLike = ["Google Chrome", "Chromium", "Brave Browser", "Microsoft Edge"];
  const MAX_DETAIL = 40;
  let remaining = MAX_DETAIL;
  const result = [];

  function takeTab(title, url, active) {
    if (remaining <= 0) return null;
    remaining -= 1;
    return { title: title, url: url, active: active };
  }

  function chromeFamily(name) {
    try {
      const app = Application(name);
      if (!app.running()) return;
      const windows = app.windows();
      const wins = [];
      for (let wi = 0; wi < windows.length; wi++) {
        const w = windows[wi];
        let tabs, activeIndex;
        try {
          tabs = w.tabs();
          activeIndex = w.activeTabIndex();
        } catch (e) {
          continue;
        }
        const list = [];
        const tabCount = tabs.length;
        const limit = Math.min(tabCount, remaining);
        for (let ti = 0; ti < limit; ti++) {
          const t = tabs[ti];
          let title = "";
          let url = "";
          try { title = String(t.title() || ""); } catch (e) {}
          try { url = String(t.url() || ""); } catch (e) {}
          const row = takeTab(title, url, (ti + 1) === activeIndex);
          if (row) list.push(row);
        }
        wins.push({ index: wi + 1, tab_count: tabCount, tabs: list });
      }
      result.push({ browser: name, windows: wins });
    } catch (e) {}
  }

  chromeLike.forEach(chromeFamily);

  try {
    const app = Application("Safari");
    if (app.running()) {
      const windows = app.windows();
      const wins = [];
      for (let wi = 0; wi < windows.length; wi++) {
        const w = windows[wi];
        let tabs;
        try { tabs = w.tabs(); } catch (e) { continue; }
        let currentId = null;
        try { currentId = w.currentTab().id(); } catch (e) {}
        const list = [];
        const tabCount = tabs.length;
        const limit = Math.min(tabCount, remaining);
        for (let ti = 0; ti < limit; ti++) {
          const t = tabs[ti];
          let title = "";
          let url = "";
          let id = null;
          try { title = String(t.name() || ""); } catch (e) {}
          try { url = String(t.url() || ""); } catch (e) {}
          try { id = t.id(); } catch (e) {}
          const row = takeTab(
            title,
            url,
            currentId !== null && id !== null && id === currentId
          );
          if (row) list.push(row);
        }
        wins.push({ index: wi + 1, tab_count: tabCount, tabs: list });
      }
      result.push({ browser: "Safari", windows: wins });
    }
  } catch (e) {}

  return JSON.stringify(result);
}
"""


def parse_browser_tabs_payload(payload: Any) -> list[dict[str, Any]]:
    """Normalize JXA JSON into ``[{browser, windows:[{index, tabs:[...]}]}]``."""
    if isinstance(payload, str):
        blob = payload.strip()
        if not blob:
            return []
        try:
            payload = json.loads(blob)
        except json.JSONDecodeError:
            return []
    if not isinstance(payload, list):
        return []
    browsers: list[dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        name = str(row.get("browser") or "").strip()
        windows_raw = row.get("windows") or []
        if not name or not isinstance(windows_raw, list):
            continue
        windows: list[dict[str, Any]] = []
        for win in windows_raw:
            if not isinstance(win, dict):
                continue
            try:
                index = int(win.get("index") or 0)
            except (TypeError, ValueError):
                index = 0
            try:
                tab_count = int(win.get("tab_count") or 0)
            except (TypeError, ValueError):
                tab_count = 0
            tabs_raw = win.get("tabs") or []
            if not isinstance(tabs_raw, list):
                continue
            tabs: list[dict[str, Any]] = []
            for tab in tabs_raw:
                if not isinstance(tab, dict):
                    continue
                title = str(tab.get("title") or "").strip()
                url = str(tab.get("url") or "").strip()
                if not title and not url:
                    continue
                tabs.append(
                    {
                        "title": title,
                        "url": url,
                        "active": bool(tab.get("active")),
                    }
                )
            windows.append(
                {
                    "index": index or (len(windows) + 1),
                    "tab_count": tab_count or len(tabs),
                    "tabs": tabs,
                }
            )
        browsers.append({"browser": name, "windows": windows})
    return browsers


def list_browser_tabs() -> list[dict[str, Any]]:
    """Open tabs for running Chrome-family browsers and Safari. Does not launch them."""
    if sys.platform != "darwin" or not list_tabs_enabled():
        return []
    try:
        proc = subprocess.run(
            ["osascript", "-l", "JavaScript"],
            input=_BROWSER_TABS_JXA,
            capture_output=True,
            text=True,
            timeout=_BROWSER_SCRIPT_TIMEOUT,
        )
    except OSError:
        return []
    except subprocess.TimeoutExpired:
        print("[desktop] browser tab listing timed out", flush=True)
        return []
    if proc.returncode != 0:
        err = (proc.stderr or "").strip().splitlines()
        if err:
            print(f"[desktop] browser tab listing failed: {err[-1][:160]}", flush=True)
        return []
    return parse_browser_tabs_payload(proc.stdout or "")


def format_running_apps(apps: list[str], *, frontmost: str = "") -> str:
    if not apps:
        return "Running apps: (none)"
    fm = (frontmost or "").strip().lower()
    lines = ["Running apps:"]
    extra = max(0, len(apps) - _MAX_APPS)
    for name in apps[:_MAX_APPS]:
        mark = " (frontmost)" if fm and name.lower() == fm else ""
        lines.append(f"  - {name}{mark}")
    if extra:
        lines.append(f"  - … {extra} more")
    return "\n".join(lines)


def _clip_url(url: str) -> str:
    url = (url or "").strip()
    if len(url) <= _MAX_TAB_URL:
        return url
    return url[: _MAX_TAB_URL - 1] + "…"


def format_browser_tabs(browsers: list[dict[str, Any]]) -> str:
    if not browsers:
        return "Browser tabs: (none listed — Chrome/Safari/Brave/Edge not running, or Automation permission missing)"
    lines = ["Browser tabs:"]
    shown = 0
    truncated = False
    for browser in browsers:
        name = str(browser.get("browser") or "Browser")
        windows = list(browser.get("windows") or [])
        tab_total = 0
        for win in windows:
            try:
                tab_total += int(win.get("tab_count") or 0)
            except (TypeError, ValueError):
                pass
            if not win.get("tab_count"):
                tab_total += len(win.get("tabs") or [])
        if tab_total == 0:
            lines.append(f"  {name}: (no tabs)")
            continue
        lines.append(f"  {name} ({tab_total} tab{'s' if tab_total != 1 else ''}):")
        multi_win = len(windows) > 1
        for win in windows:
            if shown >= _MAX_TABS:
                truncated = True
                break
            tabs = list(win.get("tabs") or [])
            if multi_win:
                lines.append(f"    window {win.get('index') or '?'}:")
            indent = "      " if multi_win else "    "
            for tab in tabs:
                if shown >= _MAX_TABS:
                    truncated = True
                    break
                title = str(tab.get("title") or "").strip() or "(untitled)"
                if len(title) > 80:
                    title = title[:77] + "…"
                url = _clip_url(str(tab.get("url") or ""))
                mark = "*" if tab.get("active") else "-"
                extra = f" — {url}" if url else ""
                lines.append(f"{indent}{mark} {title}{extra}")
                shown += 1
        if truncated:
            break
    if truncated:
        lines.append(f"  - … more tabs (showing first {_MAX_TABS})")
    return "\n".join(lines)


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
    apps: list[str] | None = None,
    tabs: list[dict[str, Any]] | None = None,
) -> str:
    """Compact per-display window list, running apps, and browser tabs."""
    live = occupancy is None
    if monitors is None:
        from actions import list_monitors

        monitors = list_monitors()
    if occupancy is None:
        occupancy = list_windows_by_monitor(monitors=monitors)
    if frontmost is None:
        frontmost = _frontmost_name()
    if apps is None and live:
        apps = list_open_apps()
    if tabs is None and live and list_tabs_enabled():
        tabs = list_browser_tabs()

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
    if apps is not None:
        lines.append("")
        lines.append(format_running_apps(apps, frontmost=frontmost or ""))
    if tabs is not None:
        lines.append("")
        lines.append(format_browser_tabs(tabs))
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
    """Return live occupancy. Does not write durable memory (see context.py)."""
    del memory_dir  # previously wrote memory/apps/displays.md
    if occupancy_text is not None:
        return occupancy_text
    return format_monitor_occupancy(monitors=monitors)
