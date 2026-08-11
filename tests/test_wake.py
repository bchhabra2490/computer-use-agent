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
