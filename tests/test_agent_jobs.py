"""Background computer-agent job supervisor."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_jobs import AgentJob, start_agent_thread  # noqa: E402


class AgentJobTests(unittest.TestCase):
    def test_start_thread_runs_and_clears_agent(self) -> None:
        job = AgentJob("Open Notes", "fc_test")
        run = MagicMock(return_value="completed")
        with (
            patch("agent_jobs.upsert_agent") as upsert,
            patch("agent_jobs.remove_agent") as remove,
            patch("agent_jobs.AgentMessageInbox"),
            patch("latency_report.finish_trace"),
        ):
            start_agent_thread(
                job,
                auto=True,
                max_steps=3,
                ask_bridge=MagicMock(),
                run_agent=run,
            )
            self.assertTrue(job.done.wait(timeout=2.0))
        upsert.assert_called_once()
        remove.assert_called_once_with("fc_test")
        self.assertEqual(job.result, "completed")
        run.assert_called_once()

    def test_done_set_when_finish_trace_fails(self) -> None:
        job = AgentJob("Open Notes", "fc_trace")
        run = MagicMock(return_value="completed")
        with (
            patch("agent_jobs.upsert_agent"),
            patch("agent_jobs.remove_agent") as remove,
            patch("agent_jobs.AgentMessageInbox"),
            patch("latency_report.finish_trace", side_effect=RuntimeError("trace")),
        ):
            start_agent_thread(
                job,
                auto=True,
                max_steps=3,
                ask_bridge=MagicMock(),
                run_agent=run,
            )
            self.assertTrue(job.done.wait(timeout=2.0))
        self.assertEqual(job.result, "completed")
        self.assertIsNone(job.error)
        remove.assert_called_once_with("fc_trace")

    def test_done_set_when_inbox_fails(self) -> None:
        job = AgentJob("Open Notes", "fc_inbox")
        with (
            patch("agent_jobs.upsert_agent"),
            patch("agent_jobs.remove_agent") as remove,
            patch("agent_jobs.AgentMessageInbox", side_effect=RuntimeError("inbox")),
            patch("latency_report.finish_trace"),
        ):
            start_agent_thread(
                job,
                auto=True,
                max_steps=3,
                ask_bridge=MagicMock(),
                run_agent=MagicMock(return_value="completed"),
            )
            self.assertTrue(job.done.wait(timeout=2.0))
        self.assertIsNotNone(job.error)
        remove.assert_called_once_with("fc_inbox")


if __name__ == "__main__":
    unittest.main()
