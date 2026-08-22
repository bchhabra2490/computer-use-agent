"""Face overlay mood mapping and placement (no AppKit)."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from face_overlay import (  # noqa: E402
    face_frame_top_center,
    face_mood_for_state,
    face_overlay_enabled,
    face_should_show,
)


PRIMARY = {
    "index": 0,
    "name": "Built-in",
    "main": True,
    "x": 0,
    "y": 0,
    "width": 1440,
    "height": 900,
}


class FaceMoodTests(unittest.TestCase):
    def test_sleep_states(self) -> None:
        for state in ("idle", "ready", "waiting", "done", "error"):
            self.assertEqual(face_mood_for_state(state), "sleep", state)

    def test_listen_on_wake(self) -> None:
        self.assertEqual(face_mood_for_state("listening"), "listen")
        self.assertEqual(face_mood_for_state("ask"), "listen")

    def test_speak_and_think(self) -> None:
        self.assertEqual(face_mood_for_state("speaking"), "speak")
        self.assertEqual(face_mood_for_state("thinking"), "think")
        self.assertEqual(face_mood_for_state("agent"), "think")

    def test_tts_playing_overrides_waiting(self) -> None:
        self.assertEqual(
            face_mood_for_state("waiting", {"tts_playing": True}),
            "speak",
        )
        self.assertEqual(
            face_mood_for_state("waiting", {"tts_playing": False}),
            "sleep",
        )


class FacePlacementTests(unittest.TestCase):
    def test_top_center(self) -> None:
        frame = face_frame_top_center(PRIMARY, width=132, height=110, margin_top=10)
        self.assertEqual(frame["y"], 10)
        self.assertEqual(frame["width"], 132)
        self.assertEqual(frame["height"], 110)
        self.assertEqual(frame["x"], (1440 - 132) // 2)


class FaceVisibilityTests(unittest.TestCase):
    def test_enabled_defaults_on(self) -> None:
        with patch.dict(os.environ, {"FACE_OVERLAY": "1"}, clear=False):
            self.assertTrue(face_overlay_enabled({}))
            self.assertTrue(face_overlay_enabled({"face_overlay_enabled": True}))
            self.assertFalse(face_overlay_enabled({"face_overlay_enabled": False}))

    def test_env_disables(self) -> None:
        with patch.dict(os.environ, {"FACE_OVERLAY": "0"}, clear=False):
            self.assertFalse(face_overlay_enabled({"face_overlay_enabled": True}))

    def test_hides_during_capture(self) -> None:
        self.assertFalse(
            face_should_show(
                {
                    "orchestrator_pid": 1,
                    "face_overlay_enabled": True,
                    "overlay_hidden": True,
                }
            )
        )
        self.assertTrue(
            face_should_show(
                {
                    "orchestrator_pid": None,
                    "agent_pid": None,
                    "face_overlay_enabled": True,
                    "overlay_hidden": False,
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
