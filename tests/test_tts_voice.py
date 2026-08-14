"""Wake-word → Sarvam TTS speaker mapping."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tts import active_tts_voice  # noqa: E402
from wake import WakeHit  # noqa: E402


class ActiveTtsVoiceTests(unittest.TestCase):
    @patch("tts._use_sarvam", return_value=True)
    @patch("wake.get_last_wake")
    def test_rekha_uses_priya(self, mock_wake, _sarvam) -> None:
        mock_wake.return_value = WakeHit(
            label="Hey Rekha",
            key="Hey_Rekha",
            source="model",
        )
        self.assertEqual(active_tts_voice(), "priya")

    @patch("tts._use_sarvam", return_value=True)
    @patch("wake.get_last_wake")
    def test_jarvis_uses_shubh(self, mock_wake, _sarvam) -> None:
        mock_wake.return_value = WakeHit(
            label="Hey Jarvis",
            key="hey_jarvis_v0.1",
            source="model",
        )
        self.assertEqual(active_tts_voice(), "shubh")

    @patch("tts._use_sarvam", return_value=True)
    @patch("wake.get_last_wake", return_value=None)
    def test_no_wake_uses_default(self, _wake, _sarvam) -> None:
        from tts import TTS_VOICE

        self.assertEqual(active_tts_voice(), TTS_VOICE)


if __name__ == "__main__":
    unittest.main()
