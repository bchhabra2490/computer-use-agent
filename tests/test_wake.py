"""Wake-phrase stripping and listen-end spotting (no ONNX required)."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import wake  # noqa: E402


class StripTrailingTests(unittest.TestCase):
    def test_trailing_hey_jarvis(self) -> None:
        self.assertEqual(
            wake.strip_trailing_wake_phrase("open chrome hey jarvis"),
            "open chrome",
        )
        self.assertEqual(
            wake.strip_trailing_wake_phrase("open chrome, Hey Jarvis!"),
            "open chrome",
        )

    def test_whole_utterance_is_wake(self) -> None:
        self.assertEqual(wake.strip_trailing_wake_phrase("Hey Jarvis"), "")
        self.assertEqual(wake.strip_trailing_wake_phrase("jarvis"), "")

    def test_short_trailing_kept_unless_include_short(self) -> None:
        self.assertEqual(
            wake.strip_trailing_wake_phrase("open Jarvis"),
            "open Jarvis",
        )
        self.assertEqual(
            wake.strip_trailing_wake_phrase("open Jarvis", include_short=True),
            "open",
        )

    def test_leading_strip_unchanged(self) -> None:
        self.assertEqual(wake.strip_wake_phrase("Hey Jarvis open chrome"), "open chrome")
        self.assertEqual(
            wake.strip_wake_phrase("Hey Rekha open chrome", phrase="Hey Rekha,Rekha"),
            "open chrome",
        )

    def test_trailing_end_phrase_alexa(self) -> None:
        self.assertEqual(
            wake.strip_trailing_wake_phrase(
                "open chrome alexa",
                phrase="Alexa",
                include_short=True,
            ),
            "open chrome",
        )
        self.assertEqual(
            wake.strip_trailing_wake_phrase("Alexa", phrase="Alexa"),
            "",
        )


class WakeIdentityTests(unittest.TestCase):
    def test_label_for_pretrained_key(self) -> None:
        self.assertEqual(wake.label_for_wake_key("hey_jarvis_v0.1"), "Hey Jarvis")
        self.assertEqual(wake.label_for_wake_key("alexa_v0.1"), "Alexa")

    def test_label_for_custom_onnx_key(self) -> None:
        self.assertEqual(wake.label_for_wake_key("Hey_Rekha"), "Hey Rekha")

    def test_matched_phrase_prefers_longest(self) -> None:
        self.assertEqual(
            wake.matched_wake_phrase(
                "Hey Rekha open chrome",
                phrase="Hey Jarvis,Jarvis,Hey Rekha,Rekha",
            ),
            "Hey Rekha",
        )
        self.assertEqual(
            wake.matched_wake_phrase("Rekha", phrase="Hey Rekha,Rekha"),
            "Rekha",
        )
        self.assertIsNone(wake.matched_wake_phrase("hello there"))


class EndModelKeyTests(unittest.TestCase):
    def test_keys_matching_specs_separates_models(self) -> None:
        keys = ["hey_jarvis_v0.1", "alexa_v0.1"]
        self.assertEqual(
            wake.keys_matching_specs(["hey_jarvis"], keys),
            ["hey_jarvis_v0.1"],
        )
        self.assertEqual(
            wake.keys_matching_specs(["alexa"], keys),
            ["alexa_v0.1"],
        )

    def test_default_end_phrase_is_over_and_out(self) -> None:
        self.assertTrue(
            any("over and out" in p.lower() for p in wake.END_LISTEN_PHRASES)
        )
        hint = wake.format_listen_end_hint()
        self.assertIn("over and out", hint.lower())

    def test_over_and_out_onnx_matches_keys(self) -> None:
        keys = ["hey_jarvis_v0.1", "over_and_out"]
        self.assertEqual(
            wake.keys_matching_specs(["Hey_Rekha.onnx"], ["hey_jarvis_v0.1", "Hey_Rekha"]),
            ["Hey_Rekha"],
        )


class OverAndOutChimeTests(unittest.TestCase):
    def test_plays_once_per_listen(self) -> None:
        wake.reset_over_and_out_chime()
        with patch.object(wake, "play_wake_chime") as mocked:
            wake.play_over_and_out_chime()
            wake.play_over_and_out_chime()
            mocked.assert_called_once_with(force=True, blocking=False)
        wake.reset_over_and_out_chime()
        with patch.object(wake, "play_wake_chime") as mocked:
            wake.play_over_and_out_chime()
            mocked.assert_called_once()


class WakeDetectChimeTests(unittest.TestCase):
    def test_notify_plays_nonblocking_tink(self) -> None:
        with patch.object(wake, "play_wake_chime") as mocked:
            wake.notify_wake_detected()
        mocked.assert_called_once_with(blocking=False)

    def test_wake_chime_on_by_default(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=False),
            patch.object(wake, "_afplay", return_value=True) as afplay,
        ):
            os.environ.pop("WAKE_CHIME", None)
            wake.play_wake_chime(blocking=False)
        afplay.assert_called_once()

    def test_wake_chime_can_be_disabled(self) -> None:
        with (
            patch.dict("os.environ", {"WAKE_CHIME": "0"}),
            patch.object(wake, "_afplay", return_value=True) as afplay,
        ):
            wake.play_wake_chime(blocking=False)
        afplay.assert_not_called()


class ResumeWakeTests(unittest.TestCase):
    def test_resume_preserves_pending_hit_when_not_paused(self) -> None:
        mon = wake.WakeMonitor()
        mon.woken.set()
        mon.resume()
        self.assertTrue(mon.woken.is_set())

    def test_resume_clears_hit_after_pause(self) -> None:
        mon = wake.WakeMonitor()
        mon.woken.set()
        mon._paused.set()
        mon.resume()
        self.assertFalse(mon.woken.is_set())
        self.assertFalse(mon._paused.is_set())


class WakeSpotterTests(unittest.TestCase):
    def test_feed_triggers_on_threshold(self) -> None:
        model = MagicMock()
        model.predict.return_value = {"hey_jarvis": 0.95}
        model.reset = MagicMock()
        spotter = wake.WakeSpotter(
            threshold=0.6,
            ignore_seconds=0.0,
            model=model,
            keys=["hey_jarvis"],
        )
        pcm = np.zeros(wake.CHUNK_SAMPLES, dtype=np.float32)
        self.assertTrue(spotter.feed(pcm, wake.WAKE_RATE))
        self.assertTrue(spotter.hit)
        self.assertFalse(spotter.feed(pcm, wake.WAKE_RATE))

    def test_below_threshold_no_hit(self) -> None:
        model = MagicMock()
        model.predict.return_value = {"hey_jarvis": 0.1}
        model.reset = MagicMock()
        spotter = wake.WakeSpotter(
            threshold=0.6,
            ignore_seconds=0.0,
            model=model,
            keys=["hey_jarvis"],
        )
        pcm = np.zeros(wake.CHUNK_SAMPLES, dtype=np.float32)
        self.assertFalse(spotter.feed(pcm, wake.WAKE_RATE))
        self.assertFalse(spotter.hit)

    def test_ignore_window_skips_frames(self) -> None:
        model = MagicMock()
        model.predict.return_value = {"hey_jarvis": 0.99}
        model.reset = MagicMock()
        spotter = wake.WakeSpotter(
            threshold=0.6,
            ignore_seconds=30.0,
            model=model,
            keys=["hey_jarvis"],
        )
        pcm = np.zeros(wake.CHUNK_SAMPLES, dtype=np.float32)
        self.assertFalse(spotter.feed(pcm, wake.WAKE_RATE))
        model.predict.assert_not_called()


class AfplayChimeTests(unittest.TestCase):
    def test_timeout_is_swallowed_when_blocking(self) -> None:
        import subprocess

        with (
            patch.object(wake.sys, "platform", "darwin"),
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(["afplay"], 3),
            ),
        ):
            self.assertTrue(wake._afplay("/System/Library/Sounds/Ping.aiff", blocking=True))


if __name__ == "__main__":
    unittest.main()
