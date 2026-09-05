"""Smart Turn audio preparation and fail-open loading tests."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import stt  # noqa: E402
from stt.smart_turn import MODEL_RATE, MODEL_SECONDS, SmartTurnClassifier, ensure_model  # noqa: E402


class SmartTurnTests(unittest.TestCase):
    def test_prepare_audio_resamples_truncates_and_left_pads(self) -> None:
        short = np.ones(24_000, dtype=np.float32)
        prepared = SmartTurnClassifier.prepare_audio(short, 24_000)
        self.assertEqual(prepared.shape, (MODEL_RATE * MODEL_SECONDS,))
        self.assertTrue(np.all(prepared[: -MODEL_RATE] == 0))
        self.assertTrue(np.allclose(prepared[-MODEL_RATE:], 1.0))

        long = np.arange(10 * MODEL_RATE, dtype=np.float32)
        prepared = SmartTurnClassifier.prepare_audio(long, MODEL_RATE)
        np.testing.assert_array_equal(prepared, long[-MODEL_RATE * MODEL_SECONDS :])

    def test_threshold_is_configurable(self) -> None:
        classifier = SmartTurnClassifier(Path("unused.onnx"), threshold=0.7)
        with patch.object(classifier, "probability", return_value=0.69):
            self.assertEqual(classifier.is_complete(np.zeros(1), MODEL_RATE), (False, 0.69))
        with patch.object(classifier, "probability", return_value=0.7):
            self.assertEqual(classifier.is_complete(np.zeros(1), MODEL_RATE), (True, 0.7))

    def test_model_download_is_atomic_and_cached(self) -> None:
        calls = []

        def download(url: str, target: str) -> None:
            calls.append(url)
            Path(target).write_bytes(b"onnx")

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "model.onnx"
            self.assertEqual(ensure_model(target, downloader=download), target)
            self.assertEqual(ensure_model(target, downloader=download), target)
        self.assertEqual(len(calls), 1)

    def test_disabled_classifier_never_loads(self) -> None:
        with (
            patch.object(stt, "SMART_TURN_ENABLED", False),
            patch.object(stt, "_smart_turn_classifier", None),
        ):
            self.assertIsNone(stt._get_smart_turn_classifier())

    def test_load_failure_falls_back(self) -> None:
        with (
            patch.object(stt, "SMART_TURN_ENABLED", True),
            patch.object(stt, "SMART_TURN_MODEL", Path("missing.onnx")),
            patch.object(stt, "_smart_turn_classifier", None),
            patch.object(stt, "_smart_turn_warned", False),
            patch.object(stt, "_smart_turn_failed", False),
            patch("stt.smart_turn.ensure_model", side_effect=OSError("offline")),
        ):
            self.assertIsNone(stt._get_smart_turn_classifier())
            self.assertTrue(stt._smart_turn_failed)


if __name__ == "__main__":
    unittest.main()
