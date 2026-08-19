"""Native timers: schedule, cancel, notify; speak queue is not user STT."""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app_status as st  # noqa: E402
import timers as tm  # noqa: E402
import tools_registry as tr  # noqa: E402


class TimerToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "status.json"
        self.patcher = patch.object(st, "STATUS_PATH", self.path)
        self.patcher.start()
        tm.reset()

    def tearDown(self) -> None:
        tm.reset()
        self.patcher.stop()
        self.tmp.cleanup()

    def test_set_list_cancel(self) -> None:
        with patch.object(tm, "notify_macos"):
            result = tm.set_timer(30, label="pasta", speak=False)
            self.assertTrue(result["ok"])
            rows = tm.list_timers()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["label"], "pasta")
            cancelled = tm.cancel_timer(timer_id=result["id"])
            self.assertTrue(cancelled["ok"])
            self.assertEqual(tm.list_timers(), [])

    def test_cancel_by_label(self) -> None:
        with patch.object(tm, "notify_macos"):
            tm.set_timer(60, label="oven")
            out = tm.cancel_timer(label="oven")
            self.assertTrue(out["ok"])
            self.assertEqual(tm.list_timers(), [])

    def test_rejects_too_short(self) -> None:
        result = tm.set_timer(0.1, label="x")
        self.assertFalse(result["ok"])

    def test_fire_queues_speak_not_utterance(self) -> None:
        with patch.object(tm, "notify_macos") as notify:
            tm.set_timer(1.05, label="oven", speak=True, message="Check the oven.")
            deadline = time.time() + 3.0
            while time.time() < deadline and not st.speak_pending():
                time.sleep(0.05)
            self.assertTrue(st.speak_pending())
            self.assertFalse(st.utterance_pending())
            self.assertEqual(st.consume_speak(), "Check the oven.")
            self.assertIsNone(st.consume_utterance())
            notify.assert_called()

    def test_fire_without_speak_does_not_queue_tts(self) -> None:
        with patch.object(tm, "notify_macos"):
            tm.set_timer(1.05, label="tea", speak=False)
            deadline = time.time() + 3.0
            while time.time() < deadline and tm.list_timers():
                time.sleep(0.05)
        self.assertEqual(tm.list_timers(), [])
        self.assertFalse(st.speak_pending())
        self.assertFalse(st.utterance_pending())

    def test_shared_tool_set_timer(self) -> None:
        with patch.object(tm, "notify_macos"):
            out = tr.run_shared_tool(
                "set_timer",
                {"seconds": 12, "label": "tea", "speak": False, "message": None},
            )
        self.assertIn("t", out.lower())
        self.assertIn("tea", out)
        self.assertIn("Do not wait", out)

    def test_registry_both_brains(self) -> None:
        with patch("mcp_client.mcp_openai_tools", return_value=[]):
            orch = [t.get("name") or t.get("type") for t in tr.orchestrator_tools()]
            agent = [t.get("name") or t.get("type") for t in tr.agent_tools()]
        self.assertIn("set_timer", orch)
        self.assertIn("list_timers", orch)
        self.assertIn("cancel_timer", orch)
        self.assertIn("set_timer", agent)
        self.assertIn("cancel_timer", agent)


if __name__ == "__main__":
    unittest.main()
