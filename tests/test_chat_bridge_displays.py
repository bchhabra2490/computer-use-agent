"""Chat screenshot display selection helpers."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import chat_bridge as cb  # noqa: E402
from chat_store import ChatStore  # noqa: E402


class ScreenshotDisplayPrefTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ChatStore(db_path=Path(self.tmp.name) / "chats.sqlite3")
        self.patcher = patch.object(cb, "get_store", return_value=self.store)
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()
        self.tmp.cleanup()

    def test_parse_and_roundtrip(self) -> None:
        self.assertIsNone(cb._parse_display_indexes(None))
        self.assertIsNone(cb._parse_display_indexes([]))
        self.assertIsNone(cb._parse_display_indexes("all"))
        self.assertEqual(cb._parse_display_indexes([0, "2", 2]), [0, 2, 2])

        self.assertIsNone(cb.screenshot_display_indexes(self.store))
        self.assertEqual(cb.set_screenshot_display_indexes([1, 0, 1], self.store), [0, 1])
        self.assertEqual(cb.screenshot_display_indexes(self.store), [0, 1])
        self.assertIsNone(cb.set_screenshot_display_indexes(None, self.store))
        self.assertIsNone(cb.screenshot_display_indexes(self.store))

    def test_displays_payload_marks_selection(self) -> None:
        monitors = [
            {"index": 0, "name": "Built-in", "main": True, "width": 1512, "height": 982},
            {"index": 1, "name": "LG", "main": False, "width": 2560, "height": 1440},
        ]
        cb.set_screenshot_display_indexes([1], self.store)
        with patch("actions.list_monitors", return_value=monitors):
            payload = cb.displays_payload()
        self.assertFalse(payload["all"])
        self.assertEqual(payload["selected"], [1])
        by_idx = {d["index"]: d for d in payload["displays"]}
        self.assertFalse(by_idx[0]["selected"])
        self.assertTrue(by_idx[1]["selected"])


if __name__ == "__main__":
    unittest.main()
