"""Prior session tasks injected into the computer-use agent prompt."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent import format_prior_tasks  # noqa: E402


class FormatPriorTasksTests(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual(format_prior_tasks(None), "")
        self.assertEqual(format_prior_tasks([]), "")

    def test_includes_request_and_result(self) -> None:
        text = format_prior_tasks(
            [
                {
                    "task": "Show a map of Nepal",
                    "result": "completed\nResult:\nOpened maps for Nepal.",
                }
            ]
        )
        self.assertIn("Prior computer tasks", text)
        self.assertIn("Show a map of Nepal", text)
        self.assertIn("Opened maps for Nepal", text)
        self.assertIn("do not redo", text.lower())

    def test_keeps_only_recent_entries(self) -> None:
        history = [
            {"task": f"task-{i}", "result": f"result-{i}"} for i in range(8)
        ]
        text = format_prior_tasks(history, max_entries=3)
        self.assertNotIn("task-0", text)
        self.assertNotIn("task-4", text)
        self.assertIn("task-5", text)
        self.assertIn("task-7", text)

    def test_truncates_long_result(self) -> None:
        text = format_prior_tasks(
            [{"task": "x", "result": "y" * 2000}],
            max_result_chars=80,
        )
        self.assertIn("…", text)
        self.assertLess(len(text), 500)


if __name__ == "__main__":
    unittest.main()
