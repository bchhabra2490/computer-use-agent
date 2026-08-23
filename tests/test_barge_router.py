"""Barge-in classification and orchestrator redirect."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import barge_router as br  # noqa: E402
import orchestrator as orch  # noqa: E402


class BargeRouterParseTests(unittest.TestCase):
    def test_is_new_task(self) -> None:
        d = br.BargeDecision("new_task", "Open the diagram in Chrome", "redirect")
        self.assertTrue(d.is_new_task)

    def test_empty_goal_not_new_task(self) -> None:
        d = br.BargeDecision("new_task", "", "missing goal")
        self.assertFalse(d.is_new_task)


class ResolveBargeTests(unittest.TestCase):
    def test_new_task_launches_agent(self) -> None:
        client = MagicMock()
        publisher = MagicMock()
        ask_bridge = MagicMock()
        with (
            patch(
                "orchestrator.classify_barge_utterance",
                return_value=br.BargeDecision(
                    "new_task",
                    "Recheck and open the diagram in the browser",
                    "user redirected",
                ),
            ),
            patch("orchestrator.active_agents", return_value=[]),
            patch("orchestrator._launch_agent_job") as launch,
        ):
            launch.return_value = orch.AgentJob("goal", "fc_1")
            output, job = orch._resolve_barge_utterance(
                client,
                "I don't see the diagram — open it in Chrome",
                spoken_context="Here is what I found about Apex Pixel…",
                user_said="Tell me about Apex Pixel",
                task_history=[{"task": "Apex Pixel research", "result": "done"}],
                publisher=publisher,
                auto=True,
                max_steps=20,
                ask_bridge=ask_bridge,
                tool_call_id="fc_give_1",
            )
        self.assertIsNone(output)
        self.assertIsNotNone(job)
        launch.assert_called_once()
        self.assertEqual(launch.call_args.kwargs["goal"], "Recheck and open the diagram in the browser")
        self.assertEqual(launch.call_args.kwargs["user_said"], "I don't see the diagram — open it in Chrome")
        self.assertEqual(launch.call_args.kwargs["call_id"], "fc_give_1")
        self.assertTrue(launch.call_args.kwargs["redirected_from_barge"])

    def test_new_task_forwards_when_agent_busy(self) -> None:
        client = MagicMock()
        with (
            patch(
                "orchestrator.classify_barge_utterance",
                return_value=br.BargeDecision("new_task", "Open Chrome diagram tab", "redirect"),
            ),
            patch("orchestrator.active_agents", return_value=[{"id": "a1"}]),
            patch("orchestrator._forward_to_agent") as forward,
        ):
            output, job = orch._resolve_barge_utterance(
                client,
                "open the diagram",
                spoken_context="summary",
                user_said="old task",
                task_history=[],
                publisher=MagicMock(),
                auto=True,
                max_steps=20,
                ask_bridge=MagicMock(),
                tool_call_id="fc_1",
            )
        self.assertIsNone(job)
        self.assertIn("Forwarded", output or "")
        forward.assert_called_once_with(ANY, "Open Chrome diagram tab")

    def test_answer_keeps_tool_output(self) -> None:
        client = MagicMock()
        with patch(
            "orchestrator.classify_barge_utterance",
            return_value=br.BargeDecision("answer", "", "yes/no"),
        ):
            output, job = orch._resolve_barge_utterance(
                client,
                "yes please",
                spoken_context="May I save the diagram?",
                user_said="diagram task",
                task_history=[],
                publisher=MagicMock(),
                auto=True,
                max_steps=20,
                ask_bridge=MagicMock(),
                tool_call_id="fc_1",
            )
        self.assertIsNone(job)
        self.assertIn("Speech interrupted", output or "")
        self.assertIn("yes please", output or "")


if __name__ == "__main__":
    unittest.main()
