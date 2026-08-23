"""Media playing yes/no for the agent (no AppleScript in tests)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import speaker_output as so  # noqa: E402


class SpeakerOutputBlockTests(unittest.TestCase):
    def test_disabled(self) -> None:
        with patch.object(so, "ENABLED", False):
            self.assertEqual(so.speaker_output_block(), "")

    def test_playing(self) -> None:
        with (
            patch.object(so, "ENABLED", True),
            patch.object(so, "media_playing", return_value=True),
        ):
            self.assertEqual(so.speaker_output_block(), "Media playing: yes")

    def test_not_playing(self) -> None:
        with (
            patch.object(so, "ENABLED", True),
            patch.object(so, "media_playing", return_value=False),
        ):
            self.assertEqual(so.speaker_output_block(), "Media playing: no")


if __name__ == "__main__":
    unittest.main()
