"""Session compaction for orchestrator context limits."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import session_compact as sc  # noqa: E402


class FormatTaskHistoryTests(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual(
            sc.format_task_history_block([]),
            "(no computer tasks run yet in this session)",
        )

    def test_summary_plus_tasks(self) -> None:
        history = [
            {"task": "open maps", "result": "done"},
            {"task": "screenshot", "result": "saved"},
        ]
        text = sc.format_task_history_block(history, task_summary="Earlier: opened Chrome.")
        self.assertIn("Earlier tasks (summarized)", text)
        self.assertIn("Earlier: opened Chrome.", text)
        self.assertIn("open maps", text)
        self.assertIn("screenshot", text)


class FoldTaskHistoryTests(unittest.TestCase):
    def test_keeps_last_three(self) -> None:
        state = sc.SessionCompactState()
        client = MagicMock()
        client.responses.create.return_value = MagicMock(
            output=[
                MagicMock(
                    type="message",
                    content=[MagicMock(type="output_text", text="Summarized older tasks.")],
                )
            ]
        )
        history = [
            {"task": f"t{i}", "result": f"r{i}"}
            for i in range(5)
        ]
        with patch.object(sc, "TASK_HISTORY_KEEP", 3):
            folded = sc.fold_task_history(client, state, history)
        self.assertEqual(len(folded), 3)
        self.assertEqual(folded[0]["task"], "t2")
        self.assertEqual(folded[-1]["task"], "t4")
        self.assertTrue(state.task_summary)


class CheckpointTests(unittest.TestCase):
    def test_after_task_folds(self) -> None:
        state = sc.SessionCompactState()
        client = MagicMock()
        client.responses.create.return_value = MagicMock(
            output=[
                MagicMock(
                    type="message",
                    content=[MagicMock(type="output_text", text="Merged.")],
                )
            ]
        )
        history = [{"task": f"t{i}", "result": "ok"} for i in range(4)]
        with patch.object(sc, "TASK_HISTORY_KEEP", 3):
            out, reset = sc.maybe_compact_checkpoint(
                client,
                state,
                history,
                after_task=True,
            )
        self.assertFalse(reset)
        self.assertEqual(len(out), 3)

    def test_turn_threshold_resets_thread(self) -> None:
        state = sc.SessionCompactState(turn_count=25, turn_log=["User: hi\nStep 1"])
        client = MagicMock()
        client.responses.create.return_value = MagicMock(
            output=[
                MagicMock(
                    type="message",
                    content=[MagicMock(type="output_text", text="Session recap.")],
                )
            ]
        )
        with patch.object(sc, "TURN_COMPACT_EVERY", 25):
            out, reset = sc.maybe_compact_checkpoint(client, state, [], after_task=False)
        self.assertTrue(reset)
        self.assertEqual(out, [])
        self.assertEqual(state.turn_count, 0)
        self.assertEqual(state.session_summary, "Session recap.")


class OverflowTests(unittest.TestCase):
    def test_detects_context_errors(self) -> None:
        self.assertTrue(sc.is_context_overflow_error(Exception("context_length exceeded")))
        self.assertFalse(sc.is_context_overflow_error(Exception("network timeout")))

    def test_recovery_once(self) -> None:
        state = sc.SessionCompactState(overflow_recovery_used=False)
        client = MagicMock()
        client.responses.create.return_value = MagicMock(
            output=[
                MagicMock(
                    type="message",
                    content=[MagicMock(type="output_text", text="Recovered.")],
                )
            ]
        )
        history, reset = sc.recover_from_overflow(client, state, [])
        self.assertTrue(reset)
        self.assertTrue(state.overflow_recovery_used)
        history2, reset2 = sc.recover_from_overflow(client, state, history)
        self.assertFalse(reset2)


if __name__ == "__main__":
    unittest.main()
