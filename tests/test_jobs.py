"""In-memory CU inbox."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jobs as jobq  # noqa: E402


class JobsTests(unittest.TestCase):
    def setUp(self) -> None:
        jobq.reset()

    def tearDown(self) -> None:
        jobq.reset()

    def test_enqueue_pop_fifo(self) -> None:
        a = jobq.enqueue_inbox("open WhatsApp", user_said="message mom on WhatsApp")
        b = jobq.enqueue_inbox("play thunderstruck")
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        self.assertEqual(len(jobq.peek_inbox()), 2)
        first = jobq.pop_inbox()
        self.assertEqual(first.goal, "open WhatsApp")
        self.assertEqual(first.user_said, "message mom on WhatsApp")
        second = jobq.pop_inbox()
        self.assertEqual(second.goal, "play thunderstruck")
        self.assertIsNone(jobq.pop_inbox())

    def test_skip_empty(self) -> None:
        self.assertIsNone(jobq.enqueue_inbox("  "))
        self.assertEqual(jobq.peek_inbox(), [])

    def test_running(self) -> None:
        jobq.set_running("c1", "flash the SD card")
        self.assertEqual(jobq.running_id(), "c1")
        self.assertEqual(jobq.running_goal(), "flash the SD card")
        jobq.clear_running()
        self.assertIsNone(jobq.running_goal())

    def test_sidequest_log(self) -> None:
        jobq.record_sidequest(
            "what's the weather today",
            "Tool: web_search Mohali weather → No search results.\nSpoken: Search failed.",
        )
        blob = jobq.format_sidequests()
        self.assertIn("Side quests this session", blob)
        self.assertIn("what's the weather today", blob)
        self.assertIn("web_search", blob)
        jobq.reset()
        self.assertEqual(jobq.format_sidequests(), "")
