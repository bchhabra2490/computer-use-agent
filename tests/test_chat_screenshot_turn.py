"""Chat-attached screenshots skip live desktop/AX capture."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app_status as st  # noqa: E402


class ChatScreenshotTurnTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patchers = [
            patch.object(st, "STATUS_PATH", self.root / "status.json"),
            patch.object(st, "RUNTIME_DIR", self.root),
            patch.object(st, "CHAT_SCREENSHOTS_DIR", self.root / "chat-shots"),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self) -> None:
        for p in self.patchers:
            p.stop()
        self.tmp.cleanup()

    def test_save_and_take_with_utterance(self) -> None:
        name = st.save_chat_screenshot_png(b"\x89PNG-chat")
        st.enqueue_utterance("Look at the attached screenshot.", source="chat", screenshot_file=name)
        self.assertEqual(st.consume_utterance(), "Look at the attached screenshot.")
        png = st.take_turn_chat_screenshot()
        self.assertEqual(png, b"\x89PNG-chat")
        self.assertIsNone(st.take_turn_chat_screenshot())

    def test_plain_utterance_has_no_shot(self) -> None:
        st.enqueue_utterance("open notes", source="chat")
        self.assertEqual(st.consume_utterance(), "open notes")
        self.assertIsNone(st.take_turn_chat_screenshot())


if __name__ == "__main__":
    unittest.main()
