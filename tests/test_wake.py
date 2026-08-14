"""Wake-phrase stripping and listen-end spotting (no ONNX required)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

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


if __name__ == "__main__":
    unittest.main()
