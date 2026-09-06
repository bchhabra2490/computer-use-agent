"""Scheduled queue payloads exposed to the chat bridge."""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import chat_bridge as cb  # noqa: E402
import scheduled_tasks as sq  # noqa: E402


class ChatBridgeQueueTests(unittest.TestCase):
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

    def test_queue_payload_lists_scheduled_tasks(self) -> None:
        sq.schedule_task("Open dashboard", run_at=time.time() + 180, source="user")
        data = cb.scheduled_queue_payload()
        self.assertTrue(data["ok"])
        self.assertEqual(data["queued_count"], 1)
        self.assertEqual(data["scheduled_tasks"][0]["task"], "Open dashboard")

    def test_cancel_queue_item_returns_updated_payload(self) -> None:
        row = sq.schedule_task("Check deploy", run_at=time.time() + 180, source="agent")
        data = cb.cancel_scheduled_queue_item({"id": row.id})
        self.assertEqual(data["queued_count"], 0)
        self.assertEqual(data["cancelled"], [row.id])


if __name__ == "__main__":
    unittest.main()
