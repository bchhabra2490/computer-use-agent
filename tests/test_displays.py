"""Per-monitor window occupancy without requiring Quartz."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import displays as disp  # noqa: E402
import memory as mem  # noqa: E402


def _monitor(
    index: int,
    name: str,
    *,
    main: bool,
    x: int,
    y: int,
    width: int,
    height: int,
) -> dict:
    return {
        "index": index,
        "name": name,
        "main": main,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "scale": 2.0,
        "native_width": width * 2,
        "native_height": height * 2,
    }


# Laptop on the left; Studio Display is the main screen on the right.
DUAL = [
    _monitor(0, "Built-in", main=False, x=0, y=0, width=1440, height=900),
    _monitor(1, "Studio Display", main=True, x=1440, y=0, width=2560, height=1440),
]


def _cg_window(
    owner: str,
    title: str,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    layer: int = 0,
) -> dict:
    return {
        "kCGWindowOwnerName": owner,
        "kCGWindowName": title,
        "kCGWindowLayer": layer,
        "kCGWindowBounds": {"X": x, "Y": y, "Width": w, "Height": h},
    }


class WindowGeometryTests(unittest.TestCase):
    def test_maps_cg_origin_from_main_display(self) -> None:
        # Window on the left (non-main) laptop: CG X is negative of main origin.
        left = disp.window_center_in_desktop(
            {"X": -1400, "Y": 100, "Width": 800, "Height": 600},
            DUAL,
        )
        self.assertIsNotNone(left)
        assert left is not None
        mon = disp.monitor_containing_point(left[0], left[1], DUAL)
        self.assertEqual(mon["index"], 0)

        right = disp.window_center_in_desktop(
            {"X": 100, "Y": 100, "Width": 1200, "Height": 800},
            DUAL,
        )
        self.assertIsNotNone(right)
        assert right is not None
        mon = disp.monitor_containing_point(right[0], right[1], DUAL)
        self.assertEqual(mon["index"], 1)

    def test_assigns_apps_and_skips_chrome_ui_chrome(self) -> None:
        windows = [
            _cg_window("Google Chrome", "YouTube", x=200, y=80, w=1800, h=1200),
            _cg_window("Slack", "Engineering", x=-1300, y=40, w=900, h=700),
            _cg_window("Dock", "", x=0, y=1400, w=400, h=80),
            _cg_window("Notes", "Scratch", x=40, y=40, w=40, h=40),
            _cg_window("Menu Bar", "hidden", x=0, y=0, w=200, h=200, layer=25),
        ]
        rows = disp.assign_windows_to_monitors(windows, DUAL)
        apps = {(r["app"], r["monitor_index"]) for r in rows}
        self.assertEqual(apps, {("Google Chrome", 1), ("Slack", 0)})

    def test_frontmost_window_is_first_in_z_order_not_largest(self) -> None:
        windows = [
            _cg_window("Code", "observe.py", x=200, y=80, w=400, h=300),
            _cg_window("Code", "huge", x=-1400, y=0, w=1400, h=900),
        ]
        info = disp.frontmost_window_info("Code", windows=windows)
        self.assertIsNotNone(info)
        self.assertEqual(disp._window_title(info), "observe.py")

    def test_monitor_for_app_window_is_the_focused_display(self) -> None:
        windows = [
            _cg_window("Safari", "Mail", x=-1400, y=100, w=800, h=600),
        ]
        mon = disp.monitor_for_app_window("Safari", windows=windows, monitors=DUAL)
        self.assertIsNotNone(mon)
        self.assertEqual(mon["index"], 0)
        self.assertFalse(mon["main"])


class OccupancyFormatTests(unittest.TestCase):
    def test_lists_windows_per_display(self) -> None:
        occupancy = [
            {
                "monitor_index": 1,
                "monitor_name": "Studio Display",
                "main": True,
                "app": "Google Chrome",
                "title": "YouTube - AC/DC",
                "area": 2_000_000,
            },
            {
                "monitor_index": 0,
                "monitor_name": "Built-in",
                "main": False,
                "app": "Slack",
                "title": "Engineering",
                "area": 500_000,
            },
        ]
        text = disp.format_monitor_occupancy(
            monitors=DUAL,
            occupancy=occupancy,
            frontmost="Google Chrome",
        )
        self.assertIn("Open windows by display (2 attached)", text)
        self.assertIn("[0] Built-in (secondary)", text)
        self.assertIn("Slack — Engineering", text)
        self.assertIn("[1] Studio Display (main / primary)", text)
        self.assertIn("Google Chrome — YouTube - AC/DC", text)
        self.assertIn("Frontmost app: Google Chrome", text)
        self.assertIn("primary display only", text)
        self.assertNotIn("Running apps:", text)
        self.assertNotIn("Browser tabs:", text)

    def test_empty_monitor_and_single_display_omits_move_hint(self) -> None:
        single = [_monitor(0, "Built-in", main=True, x=0, y=0, width=1440, height=900)]
        text = disp.format_monitor_occupancy(
            monitors=single,
            occupancy=[],
            frontmost="",
        )
        self.assertIn("(no regular windows)", text)
        self.assertNotIn("primary display only", text)

    def test_remember_does_not_write_durable_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text = disp.remember_monitor_layout(
                memory_dir=root,
                occupancy_text="Open windows by display (2 attached):\n  [0] Built-in",
            )
            self.assertIn("Open windows by display", text)
            self.assertFalse((root / "apps" / "displays.md").exists())


class RunningAppsAndTabsTests(unittest.TestCase):
    def test_parse_browser_tabs_payload(self) -> None:
        raw = json.dumps(
            [
                {
                    "browser": "Google Chrome",
                    "windows": [
                        {
                            "index": 1,
                            "tab_count": 2,
                            "tabs": [
                                {
                                    "title": "YouTube",
                                    "url": "https://www.youtube.com/watch?v=abc",
                                    "active": True,
                                },
                                {
                                    "title": "GitHub",
                                    "url": "https://github.com/bchhabra2490/computer-use-agent",
                                    "active": False,
                                },
                            ],
                        }
                    ],
                }
            ]
        )
        browsers = disp.parse_browser_tabs_payload(raw)
        self.assertEqual(len(browsers), 1)
        tabs = browsers[0]["windows"][0]["tabs"]
        self.assertEqual(tabs[0]["title"], "YouTube")
        self.assertTrue(tabs[0]["active"])
        self.assertEqual(len(tabs), 2)

    def test_format_includes_apps_and_tabs_when_provided(self) -> None:
        single = [_monitor(0, "Built-in", main=True, x=0, y=0, width=1440, height=900)]
        tabs = [
            {
                "browser": "Google Chrome",
                "windows": [
                    {
                        "index": 1,
                        "tabs": [
                            {
                                "title": "YouTube - AC/DC",
                                "url": "https://www.youtube.com/watch?v=l482T0yNkeo",
                                "active": True,
                            },
                            {
                                "title": "Linear",
                                "url": "https://linear.app/team/issue/ABC-1",
                                "active": False,
                            },
                        ],
                    }
                ],
            }
        ]
        text = disp.format_monitor_occupancy(
            monitors=single,
            occupancy=[],
            frontmost="Google Chrome",
            apps=["Cursor", "Google Chrome", "Slack"],
            tabs=tabs,
        )
        self.assertIn("Running apps:", text)
        self.assertIn("Google Chrome (frontmost)", text)
        self.assertIn("Browser tabs:", text)
        self.assertIn("Google Chrome (2 tabs)", text)
        self.assertIn("* YouTube - AC/DC", text)
        self.assertIn("- Linear", text)
        self.assertNotIn("primary display only", text)

    def test_list_tabs_disabled(self) -> None:
        with patch.dict("os.environ", {"DESKTOP_LIST_TABS": "0"}):
            self.assertFalse(disp.list_tabs_enabled())
            self.assertEqual(disp.list_browser_tabs(), [])


class LiveLayoutMemorySkipTests(unittest.TestCase):
    def test_condense_ignores_long_displays_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mem.write_condensed_memory(
                "app",
                "displays",
                "# app / displays\n\n" + ("x" * 3000),
                memory_dir=root,
            )
            notes = mem.list_memories("app", memory_dir=root)
            self.assertFalse(mem.notes_need_condense(notes))
            parsed = mem.parse_extracted_memory_items(
                {
                    "items": [
                        {
                            "kind": "app",
                            "name": "displays",
                            "text": "- Chrome on screen 2",
                        }
                    ]
                }
            )
            self.assertEqual(parsed, [])


if __name__ == "__main__":
    unittest.main()
