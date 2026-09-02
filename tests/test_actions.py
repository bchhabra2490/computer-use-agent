"""Tests for desktop action helpers (typing, modifiers)."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import ANY, MagicMock, patch

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import actions as act  # noqa: E402


class TypeModeTests(unittest.TestCase):
    def test_default_unicode_on_darwin(self) -> None:
        with patch.object(act.sys, "platform", "darwin"):
            with patch.dict("os.environ", {}, clear=True):
                self.assertEqual(act._type_mode(), "unicode")

    def test_env_override(self) -> None:
        with patch.dict("os.environ", {"CUA_TYPE_MODE": "keys"}):
            self.assertEqual(act._type_mode(), "keys")


class ReleaseModifiersTests(unittest.TestCase):
    def test_releases_all_mac_modifiers(self) -> None:
        with patch.object(act.pyautogui, "keyUp") as key_up:
            act.release_stuck_modifiers()
        self.assertEqual(key_up.call_count, len(act._MAC_MODIFIER_KEYS))
        released = {c.args[0] for c in key_up.call_args_list}
        self.assertEqual(released, set(act._MAC_MODIFIER_KEYS))


class TypeTextTests(unittest.TestCase):
    def test_unicode_mode_releases_modifiers_and_posts_events(self) -> None:
        quartz = MagicMock()
        with (
            patch.object(act, "_type_mode", return_value="unicode"),
            patch.object(act.sys, "platform", "darwin"),
            patch.object(act, "release_stuck_modifiers") as release,
            patch.dict("sys.modules", {"Quartz": quartz}),
        ):
            act.type_text("hi")
        release.assert_called_once()
        self.assertEqual(quartz.CGEventCreateKeyboardEvent.call_count, 4)  # 2 chars × down/up
        quartz.CGEventKeyboardSetUnicodeString.assert_any_call(ANY, 1, "h")
        quartz.CGEventKeyboardSetUnicodeString.assert_any_call(ANY, 1, "i")

    def test_newline_uses_enter_in_unicode_mode(self) -> None:
        quartz = MagicMock()
        with (
            patch.object(act, "_type_mode", return_value="unicode"),
            patch.object(act.sys, "platform", "darwin"),
            patch.object(act, "release_stuck_modifiers"),
            patch.object(act.pyautogui, "press") as press,
            patch.dict("sys.modules", {"Quartz": quartz}),
        ):
            act.type_text("a\nb")
        press.assert_called_once_with("enter")
        self.assertEqual(quartz.CGEventCreateKeyboardEvent.call_count, 4)  # a and b only

    def test_keys_mode_uses_typewrite(self) -> None:
        with (
            patch.object(act, "_type_mode", return_value="keys"),
            patch.object(act.pyautogui, "typewrite") as typewrite,
        ):
            act.type_text("hello")
        typewrite.assert_called_once_with("hello", interval=0.01)

    def test_paste_mode_uses_pbcopy_and_cmd_v(self) -> None:
        with (
            patch.object(act, "_type_mode", return_value="paste"),
            patch.object(act.sys, "platform", "darwin"),
            patch.object(act, "_mac_type_paste") as paste,
        ):
            act.type_text("paste me")
        paste.assert_called_once_with("paste me")


class KeypressBlockTests(unittest.TestCase):
    def test_fn_key_blocked(self) -> None:
        ctrl = act.DesktopController()
        with (
            patch.object(act.pyautogui, "press") as press,
            patch.object(act, "release_stuck_modifiers"),
        ):
            ctrl._run_one({"type": "keypress", "keys": ["FN"]})
        press.assert_not_called()


class FocusPreservationTests(unittest.TestCase):
    def test_type_does_not_press_escape_before_typing(self) -> None:
        ctrl = act.DesktopController()
        with (
            patch.object(act.pyautogui, "press") as press,
            patch.object(act, "release_stuck_modifiers"),
            patch.object(act, "type_text") as type_text,
        ):
            ctrl._run_one({"type": "type", "text": "hello"})

        press.assert_not_called()
        type_text.assert_called_once()

    def test_keypress_tab_does_not_dismiss_current_surface(self) -> None:
        ctrl = act.DesktopController()
        with (
            patch.object(act.pyautogui, "press") as press,
            patch.object(act, "release_stuck_modifiers"),
        ):
            ctrl._run_one({"type": "keypress", "keys": ["TAB"]})

        press.assert_called_once_with("tab")

    def test_explicit_escape_still_works(self) -> None:
        ctrl = act.DesktopController()
        with (
            patch.object(act.pyautogui, "press") as press,
            patch.object(act, "release_stuck_modifiers"),
        ):
            ctrl._run_one({"type": "keypress", "keys": ["ESC"]})

        press.assert_called_once_with("esc")


class ScreenshotPublishTests(unittest.TestCase):
    def test_capture_publishes_png_to_phone(self) -> None:
        from contextlib import nullcontext

        from PIL import Image

        ctrl = act.DesktopController(screenshot_max_width=1568)
        img = Image.new("RGB", (40, 20), (9, 8, 7))
        with (
            patch.dict("os.environ", {"CU_ALL_DISPLAYS": "0"}),
            patch.object(act.pyautogui, "screenshot", return_value=img),
            patch("log_overlay.pause_overlay_for_capture", return_value=nullcontext()),
            patch("app_status.publish_phone_screen") as publish,
        ):
            png = ctrl.capture_screenshot()
        self.assertTrue(png.startswith(b"\x89PNG"))
        publish.assert_called_once()
        self.assertEqual(publish.call_args.args[0], png)


class MultiDisplayTests(unittest.TestCase):
    def test_click_on_left_monitor_uses_negative_x(self) -> None:
        monitors = [
            {
                "index": 0,
                "name": "Built-in",
                "main": False,
                "x": 0,
                "y": 0,
                "width": 1440,
                "height": 900,
            },
            {
                "index": 1,
                "name": "Studio",
                "main": True,
                "x": 1440,
                "y": 0,
                "width": 2560,
                "height": 1440,
            },
        ]
        self.assertEqual(act.to_pyautogui_coords(100, 200, monitors), (-1340, 200))
        self.assertEqual(act.to_pyautogui_coords(1540, 200, monitors), (100, 200))

    def test_screenshot_coords_map_through_virtual_desktop(self) -> None:
        ctrl = act.DesktopController()
        ctrl._model_w, ctrl._model_h = 4000, 1440
        ctrl._desk_w, ctrl._desk_h = 4000, 1440
        ctrl._desk_ox, ctrl._desk_oy = 0, 0
        ctrl._monitors = [
            {"index": 0, "name": "Built-in", "main": False, "x": 0, "y": 0, "width": 1440, "height": 900},
            {"index": 1, "name": "Studio", "main": True, "x": 1440, "y": 0, "width": 2560, "height": 1440},
        ]
        self.assertEqual(ctrl._to_screen_coords(100, 200), (-1340, 200))
        self.assertEqual(ctrl._to_screen_coords(1540, 80), (100, 80))

    def test_stitch_places_monitors_side_by_side(self) -> None:
        from PIL import Image

        monitors = [
            {"index": 0, "name": "A", "main": False, "x": 0, "y": 0, "width": 40, "height": 40},
            {"index": 1, "name": "B", "main": True, "x": 40, "y": 0, "width": 80, "height": 40},
        ]
        images = {
            0: Image.new("RGB", (40, 40), (255, 0, 0)),
            1: Image.new("RGB", (80, 40), (0, 255, 0)),
        }
        canvas, dw, dh = act.stitch_monitor_screenshots(monitors, images, max_width=1000)
        self.assertEqual((dw, dh), (120, 40))
        self.assertEqual(canvas.size, (120, 40))
        self.assertEqual(canvas.getpixel((8, 30)), (255, 0, 0))
        self.assertEqual(canvas.getpixel((70, 30)), (0, 255, 0))

    def test_display_context_mentions_every_screen(self) -> None:
        text = act.format_display_context(
            [
                {"index": 0, "name": "Built-in", "main": False, "x": 0, "y": 0, "width": 1440, "height": 900, "scale": 2, "native_width": 2880, "native_height": 1800},
                {"index": 1, "name": "Studio", "main": True, "x": 1440, "y": 0, "width": 2560, "height": 1440, "scale": 2, "native_width": 5120, "native_height": 2880},
            ]
        )
        self.assertIn("EVERY attached display", text)
        self.assertIn("screen N", text)


if __name__ == "__main__":
    unittest.main()
