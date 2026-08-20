"""Mid-task route: related → CU, unrelated → sidekick, new UI → inbox."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jobs as jobq  # noqa: E402
import midtask  # noqa: E402
import orchestrator  # noqa: E402


PI_GOAL = "Flash Raspberry Pi OS to the SD card with Raspberry Pi Imager"


class HeuristicRouteTests(unittest.TestCase):
    def test_click_is_cu_update(self) -> None:
        self.assertEqual(
            midtask.heuristic_route(PI_GOAL, "click Write"),
            "cu_update",
        )

    def test_status_is_cu_update(self) -> None:
        self.assertEqual(
            midtask.heuristic_route(PI_GOAL, "is it done yet"),
            "cu_update",
        )

    def test_timer_is_sidekick(self) -> None:
        self.assertEqual(
            midtask.heuristic_route(PI_GOAL, "set a 5 minute tea timer"),
            "sidekick",
        )

    def test_math_is_sidekick(self) -> None:
        self.assertEqual(
            midtask.heuristic_route(PI_GOAL, "what's 12 times 8"),
            "sidekick",
        )

    def test_whatsapp_is_cu_new(self) -> None:
        self.assertEqual(
            midtask.heuristic_route(PI_GOAL, "open WhatsApp and message mom"),
            "cu_new",
        )


class ClassifyMdtaskTests(unittest.TestCase):
    def test_llm_route(self) -> None:
        client = MagicMock()
        client.responses.create.return_value = SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="message",
                    content=[SimpleNamespace(type="output_text", text='{"route":"sidekick","reason":"math"}')],
                )
            ]
        )
        self.assertEqual(
            midtask.classify_midtask(PI_GOAL, "what's 12 times 8", client=client),
            "sidekick",
        )

    def test_llm_failure_uses_heuristic(self) -> None:
        client = MagicMock()
        client.responses.create.side_effect = RuntimeError("boom")
        self.assertEqual(
            midtask.classify_midtask(PI_GOAL, "click Write", client=client),
            "cu_update",
        )


class DispatchBusyTests(unittest.TestCase):
    def setUp(self) -> None:
        jobq.reset()
        self.job = orchestrator.AgentJob(PI_GOAL, "call-1")
        self.pub = MagicMock()
        self.kwargs = dict(
            job=self.job,
            publisher=self.pub,
            auto=True,
            max_steps=5,
            task_history=[],
            ask_bridge=MagicMock(),
            llm_tts=None,
            turn=None,
        )

    def tearDown(self) -> None:
        jobq.reset()

    def test_cu_update_goes_to_bus(self) -> None:
        with patch("orchestrator.classify_midtask", return_value="cu_update"):
            orchestrator._dispatch_busy_utterance(
                MagicMock(), "click Write", **self.kwargs
            )
        self.pub.send.assert_called_once_with("click Write")

    def test_cu_new_queues_and_skips_bus(self) -> None:
        with (
            patch("orchestrator.classify_midtask", return_value="cu_new"),
            patch("orchestrator._speak_later"),
        ):
            orchestrator._dispatch_busy_utterance(
                MagicMock(), "open WhatsApp", **self.kwargs
            )
        self.pub.send.assert_not_called()
        queued = jobq.peek_inbox()
        self.assertEqual(len(queued), 1)
        self.assertIn("WhatsApp", queued[0].goal)

    def test_sidekick_does_not_notify_cu(self) -> None:
        with (
            patch("orchestrator.classify_midtask", return_value="sidekick"),
            patch("orchestrator._run_sidekick") as sidekick,
        ):
            orchestrator._dispatch_busy_utterance(
                MagicMock(), "what's 12 times 8", **self.kwargs
            )
        self.pub.send.assert_not_called()
        sidekick.assert_called_once()
        self.assertEqual(jobq.peek_inbox(), [])
