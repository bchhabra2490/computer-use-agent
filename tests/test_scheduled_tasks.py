"""Durable scheduled task queue tests."""

from __future__ import annotations

import json
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

    def test_invalid_schedule_is_error_outcome(self) -> None:
        outcome = tr.run_tool(
            "schedule_task",
            {"task": "too soon", "run_at_epoch": time.time() - 5, "source": "user"},
            brain="orchestrator",
        )
        self.assertTrue(outcome.is_error)
        self.assertTrue(outcome.output.startswith("Error:"))

    def test_concurrent_schedules_keep_both_tasks(self) -> None:
        import subprocess

        repo = str(ROOT)
        runtime = str(self.runtime)
        self.assertFalse((self.runtime / "scheduled-tasks.db").exists())
        code = (
            "import os, sys, time\n"
            "os.environ['AGENT_RUNTIME_DIR'] = sys.argv[1]\n"
            "sys.path.insert(0, sys.argv[2])\n"
            "import scheduled_tasks as sq\n"
            "sq.schedule_task(sys.argv[3], run_at=time.time() + 90, source='user')\n"
        )
        names = ("alpha-task", "beta-task", "gamma-task", "delta-task")
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", code, runtime, repo, name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for name in names
        ]
        for proc in procs:
            stdout, stderr = proc.communicate(timeout=30)
            self.assertEqual(proc.returncode, 0, stderr or stdout)
        listed = {row.task for row in sq.list_scheduled_tasks()}
        self.assertEqual(listed, set(names))

    def test_migrates_legacy_json_queue(self) -> None:
        now = time.time()
        payload = [
            {
                "id": "legacyjson01",
                "task": "From JSON",
                "run_at": now + 120,
                "created_at": now,
                "source": "user",
                "status": "queued",
            }
        ]
        self.queue_path.write_text(json.dumps(payload), encoding="utf-8")
        listed = sq.list_scheduled_tasks()
        self.assertEqual([row.task for row in listed], ["From JSON"])
        self.assertFalse(self.queue_path.is_file())
        self.assertTrue(self.queue_path.with_suffix(".json.migrated").is_file())

    def test_migrate_keeps_json_if_commit_fails(self) -> None:
        now = time.time()
        payload = [
            {
                "id": "legacyjson02",
                "task": "Keep me",
                "run_at": now + 120,
                "created_at": now,
                "source": "user",
                "status": "queued",
            }
        ]
        self.queue_path.write_text(json.dumps(payload), encoding="utf-8")
        real_import = sq._import_json_queue

        def boom(conn, path):
            real_import(conn, path)
            raise RuntimeError("imported then crash")

        with patch.object(sq, "_import_json_queue", side_effect=boom):
            with self.assertRaises(RuntimeError):
                sq.list_scheduled_tasks()
        self.assertTrue(self.queue_path.is_file())
        self.assertFalse(self.queue_path.with_suffix(".json.migrated").is_file())
        listed = sq.list_scheduled_tasks()
        self.assertEqual([row.task for row in listed], ["Keep me"])
        self.assertFalse(self.queue_path.is_file())

    def test_recovers_stranded_migrated_json(self) -> None:
        now = time.time()
        payload = [
            {
                "id": "strandedjson1",
                "task": "Stranded",
                "run_at": now + 120,
                "created_at": now,
                "source": "user",
                "status": "queued",
            }
        ]
        migrated = self.queue_path.with_suffix(".json.migrated")
        migrated.write_text(json.dumps(payload), encoding="utf-8")
        listed = sq.list_scheduled_tasks()
        self.assertEqual([row.task for row in listed], ["Stranded"])
        again = sq.list_scheduled_tasks()
        self.assertEqual([row.task for row in again], ["Stranded"])


if __name__ == "__main__":
    unittest.main()
