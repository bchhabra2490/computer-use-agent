"""Planner task must not become a UI screenplay for the actor."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from task_spec import is_procedure_brief, resolve_agent_task  # noqa: E402


class ProcedureBriefTests(unittest.TestCase):
    def test_user_goal_is_not_a_brief(self) -> None:
        self.assertFalse(is_procedure_brief("Show Togo on a map and screenshot it"))

    def test_chrome_screenplay_is_a_brief(self) -> None:
        text = (
            "Open Google Chrome, create a new tab, and navigate to "
            "https://www.google.com/maps/place/Togo. Wait for the page to finish "
            "loading and ensure the map is centered on the country of Togo."
        )
        self.assertTrue(is_procedure_brief(text))

    def test_numbered_steps_are_a_brief(self) -> None:
        self.assertTrue(
            is_procedure_brief("1. Open Chrome\n2. Search Togo\n3. Screenshot")
        )


class ResolveTests(unittest.TestCase):
    def test_drops_brief_keeps_utterance_for_match_and_goal(self) -> None:
        spec = resolve_agent_task(
            user_said="show me togo on a map",
            planner_task=(
                "Open Google Chrome, create a new tab, and navigate to "
                "https://www.google.com/maps/place/Togo."
            ),
        )
        self.assertEqual(spec.match_text, "show me togo on a map")
        self.assertEqual(spec.goal, "show me togo on a map")

    def test_keeps_short_planner_restatement(self) -> None:
        spec = resolve_agent_task(
            user_said="that one",
            planner_task="Open a map of Togo",
        )
        self.assertEqual(spec.match_text, "that one")
        self.assertEqual(spec.goal, "Open a map of Togo")

    def test_leftover_step_is_the_goal(self) -> None:
        spec = resolve_agent_task(
            user_said="now screenshot it",
            planner_task="Screenshot the map that is already open",
        )
        self.assertEqual(spec.goal, "Screenshot the map that is already open")


if __name__ == "__main__":
    unittest.main()
