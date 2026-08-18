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


class BrowserOverlayDismissTests(unittest.TestCase):
    def test_type_sends_esc_before_typing(self) -> None:
        ctrl = act.DesktopController()
        with (
            patch.object(act.pyautogui, "press") as press,
            patch.object(act, "release_stuck_modifiers"),
            patch.object(act, "type_text") as type_text,
            patch.object(act.time, "sleep"),
        ):
            ctrl._run_one({"type": "type", "text": "hello"})

        press.assert_called_once_with("esc")
        type_text.assert_called_once()

    def test_keypress_tab_dismisses_overlay_then_presses_tab(self) -> None:
        ctrl = act.DesktopController()
        with (
            patch.object(act.pyautogui, "press") as press,
            patch.object(act, "release_stuck_modifiers"),
            patch.object(act.time, "sleep"),
        ):
            ctrl._run_one({"type": "keypress", "keys": ["TAB"]})

        self.assertGreaterEqual(press.call_count, 2)
        self.assertEqual(press.call_args_list[0].args[0], "esc")
        self.assertEqual(press.call_args_list[1].args[0], "tab")


if __name__ == "__main__":
    unittest.main()
