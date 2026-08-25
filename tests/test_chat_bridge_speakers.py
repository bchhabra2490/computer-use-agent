"""Speaker list payload for the Electron manage-speakers page."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from chat_bridge import list_speaker_payload  # noqa: E402


class SpeakerPayloadTests(unittest.TestCase):
    def test_passages_match_enrollment(self) -> None:
        from speaker_id import ENROLLMENT_PASSAGES

        payload = list_speaker_payload()
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["passages"]), len(ENROLLMENT_PASSAGES))
        self.assertEqual(payload["required_samples"], len(ENROLLMENT_PASSAGES))
        self.assertEqual(payload["passages"][0]["title"], ENROLLMENT_PASSAGES[0][0])
        self.assertTrue(payload["passages"][-1]["short"])
        self.assertIsInstance(payload["speakers"], list)


if __name__ == "__main__":
    unittest.main()
