"""Evaluator prompt context from the task log."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import evaluator as ev  # noqa: E402
from task_log import TaskLog  # noqa: E402


class EvalContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.log = TaskLog("flash the ESP32", logs_dir=Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_steps_for_eval_keeps_head_and_tail(self) -> None:
        self.log.record("read_skill", "esp32-s3-enter-download-mode", {"name": "esp32-s3-enter-download-mode"})
        for i in range(30):
            self.log.record("computer_actions", f"{i} action(s)", {"actions": [{"type": "click"}]})
        self.log.record("zmq_message", "use the other cable", {"text": "use the other cable"})
        blob = self.log.steps_for_eval(head=2, tail=3, max_chars=20_000)
        self.assertIn("read_skill", blob)
        self.assertIn("use the other cable", blob)
        self.assertIn("omitted", blob)

    def test_eval_highlights(self) -> None:
        self.log.record("read_skill", "esp32-probe", {"name": "esp32-probe"})
        self.log.record(
            "recipe_handoff",
            "youtube-search",
            {"leftover": "screenshot the results", "params": {}},
        )
        self.log.record("zmq_message", "skip ads", {"text": "skip ads"})
        hi = self.log.eval_highlights()
        self.assertEqual(hi["skills_loaded"], ["esp32-probe"])
        self.assertTrue(any("screenshot" in r for r in hi["recipes"]))
        self.assertEqual(hi["user_midtask"], ["skip ads"])

    def test_coach_includes_highlights(self) -> None:
        self.log.record("read_skill", "esp32-probe", {"name": "esp32-probe"})
        client = MagicMock()
        response = MagicMock()
        response.output = [
            MagicMock(
                type="message",
                content=[MagicMock(type="output_text", text='{"status":"on_track","guidance":["ok"],"next_focus":"click BOOT"}')],
            )
        ]
        client.responses.create.return_value = response
        with patch.object(ev, "EVAL_EVERY", 5):
            tip = ev.coach_agent(
                client,
                task="enter download mode",
                log=self.log,
                screenshot_b64=None,
                step_n=5,
                user_said="put the ESP32 in flash mode",
                display_context="screen 1: Terminal",
            )
        self.assertIsNotNone(tip)
        self.assertIn("on_track", tip or "")
        kwargs = client.responses.create.call_args.kwargs
        prompt = kwargs["input"][0]["content"][0]["text"]
        self.assertIn("esp32-probe", prompt)
        self.assertIn("put the ESP32 in flash mode", prompt)
        self.assertIn("Terminal", prompt)


if __name__ == "__main__":
    unittest.main()
