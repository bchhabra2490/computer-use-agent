"""Placement and text for the click-through log overlay (no AppKit)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from log_overlay import (  # noqa: E402
    format_overlay_text,
    overlay_enabled,
    overlay_frame_top_left,
    overlay_owner_alive,
    overlay_should_show,
    overlay_target_monitor,
    pause_overlay_for_capture,
    should_hide_overlay_for_capture,
)


DUAL = [
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
        "name": "Studio Display",
        "main": True,
        "x": 1440,
        "y": 0,
        "width": 2560,
        "height": 1440,
    },
]


class OverlayPlacementTests(unittest.TestCase):
    def test_prefers_non_primary_display(self) -> None:
        mon = overlay_target_monitor(DUAL)
        self.assertIsNotNone(mon)
        self.assertEqual(mon["name"], "Built-in")
        self.assertFalse(mon["main"])

    def test_falls_back_to_primary_when_alone(self) -> None:
        only = [DUAL[1]]
        mon = overlay_target_monitor(only)
        self.assertEqual(mon["name"], "Studio Display")

    def test_frame_sits_bottom_left_of_target(self) -> None:
        mon = overlay_target_monitor(DUAL)
        frame = overlay_frame_top_left(mon, width=440, height=300, margin=18)
        self.assertEqual(frame["x"], 18)
        self.assertEqual(frame["y"], 900 - 18 - 300)
        self.assertEqual(frame["width"], 440)
        self.assertEqual(frame["height"], 300)


class OverlayTextTests(unittest.TestCase):
    def test_includes_state_and_logs(self) -> None:
        text = format_overlay_text(
            {
                "state": "agent",
                "detail": "opening Chrome",
                "task": "open hn",
                "logs": ["click", "type news.ycombinator.com"],
                "agents": [{"id": "a1", "kind": "computer", "task": "open hn", "status": "running"}],
            }
        )
        self.assertIn("Jarvis · agent", text)
        self.assertIn("opening Chrome", text)
        self.assertIn("type news.ycombinator.com", text)

    def test_overlay_enabled_defaults_on(self) -> None:
        self.assertTrue(overlay_enabled({}))
        self.assertTrue(overlay_enabled({"overlay_enabled": True}))
        self.assertFalse(overlay_enabled({"overlay_enabled": False}))

    def test_overlay_toggle_persists(self) -> None:
        import tempfile
        from unittest.mock import patch

        import app_status as st

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            with patch.object(st, "STATUS_PATH", path):
                self.assertTrue(overlay_enabled())
                st.set_overlay_enabled(False)
                self.assertFalse(overlay_enabled())
                st.set_overlay_enabled(True)
                self.assertTrue(overlay_enabled())


class OverlayHideForCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        from unittest.mock import patch

        enabled = patch("log_overlay.overlay_enabled", return_value=True)
        enabled.start()
        self.addCleanup(enabled.stop)

    def test_hides_on_single_display(self) -> None:
        self.assertTrue(should_hide_overlay_for_capture([DUAL[1]]))

    def test_hides_on_dual_display(self) -> None:
        self.assertTrue(should_hide_overlay_for_capture(DUAL))

    def test_disabled_overlay_never_hides(self) -> None:
        from unittest.mock import patch

        with (
            patch("log_overlay.overlay_enabled", return_value=False),
            patch("face_overlay.face_overlay_enabled", return_value=False),
        ):
            self.assertFalse(should_hide_overlay_for_capture([DUAL[1]]))

    def test_hides_when_only_face_enabled(self) -> None:
        from unittest.mock import patch

        with (
            patch("log_overlay.overlay_enabled", return_value=False),
            patch("face_overlay.face_overlay_enabled", return_value=True),
        ):
            self.assertTrue(should_hide_overlay_for_capture([DUAL[1]]))

    def test_pause_hides_on_dual_when_tray_alive(self) -> None:
        from unittest.mock import patch

        with (
            patch("log_overlay.set_overlay_hidden") as hidden,
            patch(
                "log_overlay.read_status",
                return_value={"tray_pid": 1, "overlay_ack_hidden": True},
            ),
            patch("log_overlay.pid_alive", return_value=True),
            patch("log_overlay._post_overlay_note"),
        ):
            with pause_overlay_for_capture(monitors=DUAL):
                hidden.assert_called_with(True)
        hidden.assert_called_with(False)

    def test_pause_skips_when_tray_not_running(self) -> None:
        from unittest.mock import patch

        with (
            patch("log_overlay.set_overlay_hidden") as hidden,
            patch("log_overlay.read_status", return_value={"tray_pid": None}),
        ):
            with pause_overlay_for_capture(monitors=[DUAL[1]]):
                pass
        hidden.assert_not_called()

    def test_pause_hides_then_restores_when_tray_alive(self) -> None:
        from unittest.mock import patch

        with (
            patch("log_overlay.set_overlay_hidden") as hidden,
            patch(
                "log_overlay.read_status",
                return_value={"tray_pid": 1, "overlay_ack_hidden": True},
            ),
            patch("log_overlay.pid_alive", return_value=True),
            patch("log_overlay._post_overlay_note"),
        ):
            with pause_overlay_for_capture(monitors=[DUAL[1]]):
                hidden.assert_called_with(True)
        hidden.assert_called_with(False)


class OverlayLifetimeTests(unittest.TestCase):
    def test_hidden_when_no_owner_process(self) -> None:
        from unittest.mock import patch

        data = {"orchestrator_pid": None, "agent_pid": None, "overlay_hidden": False}
        with patch("log_overlay.pid_alive", return_value=False):
            self.assertFalse(overlay_owner_alive(data))
            self.assertFalse(overlay_should_show(data))

    def test_shown_when_orchestrator_alive(self) -> None:
        from unittest.mock import patch

        data = {"orchestrator_pid": 42, "agent_pid": None, "overlay_hidden": False}
        with patch("log_overlay.pid_alive", side_effect=lambda pid: pid == 42):
            self.assertTrue(overlay_owner_alive(data))
            self.assertTrue(overlay_should_show(data))

    def test_stays_hidden_during_capture(self) -> None:
        from unittest.mock import patch

        data = {"orchestrator_pid": 42, "overlay_hidden": True}
        with patch("log_overlay.pid_alive", return_value=True):
            self.assertFalse(overlay_should_show(data))

    def test_hidden_when_toggled_off(self) -> None:
        from unittest.mock import patch

        data = {
            "orchestrator_pid": 42,
            "overlay_hidden": False,
            "overlay_enabled": False,
        }
        with patch("log_overlay.pid_alive", return_value=True):
            self.assertFalse(overlay_should_show(data))


if __name__ == "__main__":
    unittest.main()
