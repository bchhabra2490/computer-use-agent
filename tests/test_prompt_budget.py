"""Prompt-budget helpers: garbage STT, screen questions, UTF-8 surrogates."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import text_sanitize as ts  # noqa: E402
import utterance as ut  # noqa: E402


class GarbageUtteranceTests(unittest.TestCase):
    def test_repeated_and(self) -> None:
        self.assertTrue(
            ut.is_garbage_utterance(
                "all not in the room it's not and and and and and and and"
            )
        )

    def test_real_request(self) -> None:
        self.assertFalse(ut.is_garbage_utterance("Send a middle finger emoji to basket."))
        self.assertFalse(ut.is_garbage_utterance("play old hindi songs"))


class ScreenPixelsTests(unittest.TestCase):
    def test_on_screen_questions(self) -> None:
        self.assertTrue(ut.needs_screen_pixels("what is on my screen?"))
        self.assertTrue(ut.needs_screen_pixels("what's this"))
        self.assertTrue(ut.needs_screen_pixels("which window is that"))

    def test_action_requests_skip(self) -> None:
        self.assertFalse(ut.needs_screen_pixels("play old hindi songs"))
        self.assertFalse(ut.needs_screen_pixels("Send a middle finger emoji to basket."))


class Utf8SanitizeTests(unittest.TestCase):
    def test_joins_surrogate_pair(self) -> None:
        raw = "\ud83d\udd95"
        out = ts.sanitize_utf8(raw)
        self.assertEqual(out, "🖕")
        out.encode("utf-8")

    def test_lone_surrogate_encodes(self) -> None:
        out = ts.sanitize_utf8("hello \ud83d world")
        out.encode("utf-8")
        self.assertNotIn("\ud83d", out)

    def test_plain_emoji_unchanged(self) -> None:
        self.assertEqual(ts.sanitize_utf8("hello 🖕"), "hello 🖕")


if __name__ == "__main__":
    unittest.main()
