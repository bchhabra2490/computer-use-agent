"""Chat-origin reply streaming helpers."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app_status as st  # noqa: E402


class ChatStreamTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "status.json"
        self.patcher = patch.object(st, "STATUS_PATH", self.path)
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()
        self.tmp.cleanup()

    def test_turn_source_from_chat_utterance(self) -> None:
        st.enqueue_utterance("hello", source="chat")
        self.assertEqual(st.consume_utterance(), "hello")
        self.assertTrue(st.reply_to_chat())
        st.set_chat_stream("Hel", force=True)
        st.set_chat_stream("Hello", force=True)
        payload = st.chat_stream_payload()
        self.assertEqual(payload["text"], "Hello")
        self.assertFalse(payload["done"])
        st.set_last_spoken("Hello there")
        payload = st.chat_stream_payload()
        self.assertEqual(payload["text"], "Hello there")
        self.assertTrue(payload["done"])

    def test_voice_turn_clears_stream(self) -> None:
        st.set_chat_stream("partial", force=True)
        st.set_turn_source("voice")
        self.assertFalse(st.reply_to_chat())
        self.assertIsNone(st.chat_stream_payload())

    def test_chat_text_only_when_tts_off(self) -> None:
        st.enqueue_utterance("hello", source="chat", tts=False)
        st.consume_utterance()
        self.assertTrue(st.reply_to_chat())
        self.assertFalse(st.reply_tts_enabled())
        self.assertTrue(st.chat_text_only())

    def test_chat_text_only_false_when_tts_on(self) -> None:
        st.enqueue_utterance("hello", source="chat", tts=True)
        st.consume_utterance()
        self.assertTrue(st.reply_to_chat())
        self.assertTrue(st.reply_tts_enabled())
        self.assertFalse(st.chat_text_only())


if __name__ == "__main__":
    unittest.main()
