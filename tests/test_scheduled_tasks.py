"""Durable scheduled task queue tests."""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scheduled_tasks as sq  # noqa: E402
import tools_registry as tr  # noqa: E402


class ScheduledTaskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = self.root / ".runtime"
        self.runtime.mkdir(parents=True)
        self.queue_path = self.runtime / "scheduled-tasks.json"
        self.p1 = patch.object(sq, "RUNTIME_DIR", self.runtime)
        self.p2 = patch.object(sq, "QUEUE_PATH", self.queue_path)
        self.p1.start()
        self.p2.start()

    def tearDown(self) -> None:
        self.p2.stop()
        self.p1.stop()
        self.tmp.cleanup()

    def test_schedule_list_cancel(self) -> None:
        row = sq.schedule_task(
            "Open Notes later",
            run_at=time.time() + 120,
            source="user",
        )
        listed = sq.list_scheduled_tasks()
        self.assertEqual([item.id for item in listed], [row.id])
        out = sq.cancel_scheduled_task(task_id=row.id)
        self.assertTrue(out["ok"])
        self.assertEqual(sq.list_scheduled_tasks(), [])

    def test_claim_due_orders_by_run_time(self) -> None:
        first = sq.schedule_task("First", run_at=time.time() + 30, source="user")
        second = sq.schedule_task("Second", run_at=time.time() + 60, source="user")
        claimed = sq.claim_due_task(now=first.run_at + 1)
        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.id, first.id)
        still_waiting = sq.list_scheduled_tasks(include_finished=True)
        self.assertEqual([row.id for row in still_waiting if row.status == "queued"], [second.id])

    def test_recover_pending_running_tasks(self) -> None:
        row = sq.schedule_task("Retry this", run_at=time.time() + 45, source="agent")
        claimed = sq.claim_due_task(now=row.run_at + 1)
        self.assertEqual(claimed.status, "running")
        repaired = sq.recover_pending_tasks()
        self.assertEqual(repaired, 1)
        listed = sq.list_scheduled_tasks(include_finished=True)
        self.assertEqual(listed[0].status, "queued")
        self.assertIn("Recovered after restart", listed[0].last_error or "")

    def test_agent_can_schedule_follow_up_task(self) -> None:
        when = time.time() + 300
        outcome = tr.run_tool(
            "schedule_task",
            {
                "task": "Check the deployment again",
                "run_at_epoch": when,
                "source": "agent",
                "parent_task_id": "job123",
                "note": "Follow-up after deploy",
            },
            brain="agent",
        )
        self.assertFalse(outcome.is_error)
        rows = sq.list_scheduled_tasks()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].task, "Check the deployment again")
        self.assertEqual(rows[0].parent_task_id, "job123")


if __name__ == "__main__":
    unittest.main()
