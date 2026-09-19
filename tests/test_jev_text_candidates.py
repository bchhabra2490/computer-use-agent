"""Tests for ax-pilot-inspired text candidate extraction."""

from __future__ import annotations

import unittest

from jev.text_candidates import (
    arithmetic_facts,
    extract_text_candidates,
    goal_names_destructive,
    label_looks_destructive,
)


class TextCandidateTests(unittest.TestCase):
    def test_quoted_and_url(self) -> None:
        cands = extract_text_candidates(
            'In Safari open a new tab and go to "https://typesafe.ai"'
        )
        self.assertTrue(any("typesafe" in c.lower() for c in cands))

    def test_titled(self) -> None:
        cands = extract_text_candidates(
            'Create a new note titled Grocery list in Notes'
        )
        self.assertTrue(any("Grocery" in c for c in cands))

    def test_arithmetic_facts(self) -> None:
        facts = arithmetic_facts(["48*12", "hello"])
        self.assertEqual(facts.get("48*12 equals"), "576")
        self.assertNotIn("hello equals", facts)

    def test_destructive_goal(self) -> None:
        self.assertTrue(goal_names_destructive("delete the draft"))
        self.assertFalse(goal_names_destructive("open Settings"))
        self.assertTrue(label_looks_destructive("Empty Trash"))
        self.assertFalse(label_looks_destructive("Save"))


if __name__ == "__main__":
    unittest.main()
