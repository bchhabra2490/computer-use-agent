"""Tests for mark-done utterances and status flags."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app_status as st  # noqa: E402


class UtteranceTests(unittest.TestCase):
    def test_positive(self) -> None:
        for text in (
            "Mark it done",
            "mark done",
            "that's done",
            "no other action is required",
            "no further actions required",
            "nothing else needed",
            "that's all",
            "stop the task",
        ):
            self.assertTrue(st.is_mark_done_utterance(text), text)

    def test_negative(self) -> None:
        for text in (
            "open notes",
            "mark this unread",
            "I'm not done yet",
            "continue the task",
        ):
            self.assertFalse(st.is_mark_done_utterance(text), text)


class FlagTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "status.json"
        self.patcher = patch.object(st, "STATUS_PATH", self.path)
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()
        self.tmp.cleanup()

    def test_request_and_consume(self) -> None:
        self.assertFalse(st.mark_done_pending("abc"))
        st.request_mark_done("abc")
        self.assertTrue(st.mark_done_pending("abc"))
        self.assertTrue(st.mark_done_pending())
        self.assertFalse(st.mark_done_pending("other"))
        self.assertTrue(st.consume_mark_done("abc"))
        self.assertFalse(st.mark_done_pending("abc"))

    def test_all_agents(self) -> None:
        st.request_mark_done(None)
        self.assertTrue(st.consume_mark_done("any-id"))


if __name__ == "__main__":
    unittest.main()
