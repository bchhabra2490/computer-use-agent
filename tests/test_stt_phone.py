"""Phone-queued text must be accepted while STT is listening (ask_user)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import stt  # noqa: E402


class ListenOncePhoneTests(unittest.TestCase):
    def test_uses_queue_instead_of_opening_mic(self) -> None:
        with (
            patch("stt._consume_phone_utterance", return_value="skip the ads"),
            patch("stt.listen_realtime") as realtime,
        ):
            heard = stt.listen_once(MagicMock(), prompt="Listening for your answer…")
        self.assertEqual(heard, "skip the ads")
        realtime.assert_not_called()

    def test_aborts_mic_when_phone_arrives_mid_listen(self) -> None:
        with (
            patch("stt.listen_realtime", side_effect=stt.PhoneCommandReady()),
            patch(
                "stt._consume_phone_utterance",
                side_effect=[None, "play something else"],
            ),
        ):
            heard = stt.listen_once(MagicMock(), max_attempts=1)
        self.assertEqual(heard, "play something else")


class AskUserTests(unittest.TestCase):
    def test_empty_transcription_does_not_raise(self) -> None:
        with (
            patch("stt.speak", return_value=False),
            patch(
                "stt.listen_once",
                side_effect=stt.NoSpeechError(
                    "Transcription came back empty — try speaking again."
                ),
            ),
        ):
            out = stt.ask_user(MagicMock(), "Which board?")
        self.assertIn("No speech was captured", out)
        self.assertIn("ask_user", out)
