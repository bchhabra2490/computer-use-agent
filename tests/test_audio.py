"""AudioSession coordinates wake / STT / TTS without opening devices in tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audio import AudioSession  # noqa: E402
from session import Session  # noqa: E402


class AudioSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sess = Session(strict=True, project_status=False)
        self.sess.enter("ready")
        self.audio = AudioSession(MagicMock(), session=self.sess)

    def test_speak_without_barge_returns_none(self) -> None:
        with patch("audio.speak", return_value=False) as speak:
            result = self.audio.speak("Hello.")
        speak.assert_called_once()
        self.assertIsNone(result)
        self.assertEqual(self.sess.phase, "speaking")
        self.assertEqual(self.audio.mic_owner, "wake")

    def test_speak_barge_listens(self) -> None:
        with (
            patch("audio.speak", return_value=True),
            patch.object(self.audio, "listen_after_barge", return_value="stop"),
        ):
            result = self.audio.speak("Hello.")
        self.assertEqual(result, "stop")
        self.assertEqual(self.sess.phase, "listening")

    def test_listen_command_uses_wake_then_stt(self) -> None:
        with (
            patch("audio.wait_for_wake", return_value=True),
            patch("audio.get_last_wake", return_value=MagicMock(label="Hey Jarvis")),
            patch("audio.get_wake_remainder", return_value=None),
            patch("audio.listen_for_utterance", return_value="open notes"),
        ):
            cmd = self.audio.listen_command()
        self.assertEqual(cmd, "open notes")
        self.assertEqual(self.sess.phase, "listening")


if __name__ == "__main__":
    unittest.main()
