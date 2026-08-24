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
    blob_outline_points,
    blobatar_ids,
    current_blobatar,
    face_frame_top_center,
    face_mood_for_state,
    face_overlay_enabled,
    face_should_show,
    hsl_to_rgb,
    mood_eye_pose,
    resolve_blobatar,
    set_blobatar,
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

    def test_ask_user_is_unsure(self) -> None:
        self.assertEqual(face_mood_for_state("ask"), "unsure")
        self.assertEqual(face_mood_for_state("ask_user"), "unsure")
        self.assertEqual(
            face_mood_for_state("ask", {"tts_playing": True}),
            "unsure",
        )
        self.assertEqual(
            face_mood_for_state("ask", {"stt_active": True}),
            "unsure",
        )

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

    def test_stt_active_is_listen(self) -> None:
        self.assertEqual(
            face_mood_for_state("waiting", {"stt_active": True}),
            "listen",
        )
        self.assertEqual(
            face_mood_for_state("waiting", {"stt_active": True, "tts_playing": True}),
            "speak",
        )


class FacePlacementTests(unittest.TestCase):
    def test_top_center(self) -> None:
        frame = face_frame_top_center(PRIMARY, width=132, height=110, margin_top=10)
        self.assertEqual(frame["y"], 10)
        self.assertEqual(frame["width"], 132)
        self.assertEqual(frame["height"], 110)
        self.assertEqual(frame["x"], (1440 - 132) // 2)


class BlobatarStyleTests(unittest.TestCase):
    def test_hsl_pure_red(self) -> None:
        r, g, b = hsl_to_rgb(0, 1.0, 0.5)
        self.assertAlmostEqual(r, 1.0, places=5)
        self.assertAlmostEqual(g, 0.0, places=5)
        self.assertAlmostEqual(b, 0.0, places=5)

    def test_sleep_lids_flatter_than_listen(self) -> None:
        sleep = mood_eye_pose("sleep", 0.0)
        listen = mood_eye_pose("listen", 1.0)
        self.assertLess(sleep["eye_h"], listen["eye_h"])
        self.assertGreater(sleep["body_dy"], listen["body_dy"])

    def test_think_seesaw_is_asymmetric(self) -> None:
        pose = mood_eye_pose("think", 0.225)
        self.assertNotAlmostEqual(pose["left_dy"], pose["right_dy"], places=4)
        self.assertAlmostEqual(pose["left_dy"], -pose["right_dy"], places=4)

    def test_speak_tilts_both_capsules(self) -> None:
        pose = mood_eye_pose("speak", 0.0)
        self.assertGreater(pose["left_tilt"], 0.0)
        self.assertEqual(pose["left_tilt"], pose["right_tilt"])
        self.assertGreater(pose["eye_h"], mood_eye_pose("listen", 1.0)["eye_h"])

    def test_unsure_squeezes_one_eye(self) -> None:
        pose = mood_eye_pose("unsure", 0.0)
        self.assertLess(pose["right_eye_h"], pose["left_eye_h"])
        self.assertNotAlmostEqual(pose["left_tilt"], pose["right_tilt"], places=4)
        self.assertLess(abs(pose["body_dy"]), abs(mood_eye_pose("sleep", 0.0)["body_dy"]))

    def test_blob_outline_is_closed_loop(self) -> None:
        pts = blob_outline_points(0.0, 0.0, 40.0, 36.0)
        self.assertEqual(len(pts), 8)
        self.assertNotEqual(pts[0], pts[2])


class BlobatarPresetTests(unittest.TestCase):
    def test_four_named_blobatars(self) -> None:
        self.assertEqual(blobatar_ids(), ("pebble", "droplet", "cloud", "sun"))

    def test_resolve_aliases(self) -> None:
        self.assertEqual(resolve_blobatar("drop").id, "droplet")
        self.assertEqual(resolve_blobatar("amber").id, "sun")
        self.assertIsNone(resolve_blobatar(""))
        self.assertIsNone(resolve_blobatar("nope/slash"))

    def test_any_name_hashes_stably(self) -> None:
        a = resolve_blobatar("jarvis")
        b = resolve_blobatar("JARVIS")
        assert a is not None and b is not None
        self.assertEqual(a.id, "jarvis")
        self.assertEqual(a.hue, b.hue)
        self.assertEqual(a.shape, b.shape)
        self.assertTrue(a.blurb.startswith("hashed "))
        other = resolve_blobatar("jarvus")
        assert other is not None
        self.assertNotEqual((a.hue, a.blurb), (other.hue, other.blurb))

    def test_presets_differ_in_hue_and_shape(self) -> None:
        hues = {resolve_blobatar(n).hue for n in blobatar_ids()}
        self.assertEqual(len(hues), 4)
        self.assertGreater(len(resolve_blobatar("sun").extras), len(resolve_blobatar("pebble").extras))
        self.assertGreater(resolve_blobatar("droplet").ry, resolve_blobatar("pebble").ry)

    def test_status_snapshot_selects_preset(self) -> None:
        spec = current_blobatar({"face_preset": "cloud"})
        self.assertEqual(spec.id, "cloud")

    def test_status_snapshot_accepts_hashed_name(self) -> None:
        spec = current_blobatar({"face_preset": "Jarvis"})
        self.assertEqual(spec.id, "jarvis")
        self.assertTrue(spec.blurb.startswith("hashed "))

    def test_set_blobatar_writes_file(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "face_preset"
            with (
                patch("face_overlay.PRESET_PATH", path),
                patch("app_status.set_face_preset") as persist,
            ):
                spec = set_blobatar("sun")
            self.assertEqual(spec.id, "sun")
            self.assertEqual(path.read_text(encoding="utf-8").strip(), "sun")
            persist.assert_called_once_with("sun")

    def test_set_blobatar_accepts_any_seed(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "face_preset"
            with (
                patch("face_overlay.PRESET_PATH", path),
                patch("app_status.set_face_preset") as persist,
            ):
                spec = set_blobatar("Rekha")
            self.assertEqual(spec.id, "rekha")
            self.assertEqual(path.read_text(encoding="utf-8").strip(), "rekha")
            persist.assert_called_once_with("rekha")


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
