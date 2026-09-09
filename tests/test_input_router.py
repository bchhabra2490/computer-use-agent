"""Input router: scheduled / queue / timer / voice decision tree."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from input_router import collect_next_input  # noqa: E402


class InputRouterTests(unittest.TestCase):
    def test_pending_wins(self) -> None:
        result = collect_next_input(
            "already pending",
            claim_scheduled=lambda: (None, None),
            drain_next_run=list,
            speak_pending=lambda: False,
            service_timer_speech=lambda: None,
            listen=lambda: None,
            quit_requested=lambda: False,
            on_quit=lambda: None,
        )
        self.assertEqual(result.action, "ready")
        self.assertEqual(result.utterance, "already pending")

    def test_scheduled_before_listen(self) -> None:
        result = collect_next_input(
            None,
            claim_scheduled=lambda: ("do the thing", "abc"),
            drain_next_run=list,
            speak_pending=lambda: False,
            service_timer_speech=lambda: None,
            listen=lambda: "should not listen",
            quit_requested=lambda: False,
            on_quit=lambda: None,
        )
        self.assertEqual(result.action, "ready")
        self.assertEqual(result.utterance, "do the thing")
        self.assertEqual(result.scheduled_id, "abc")

    def test_next_run_queue(self) -> None:
        result = collect_next_input(
            None,
            claim_scheduled=lambda: (None, None),
            drain_next_run=lambda: [SimpleNamespace(text="later")],
            speak_pending=lambda: False,
            service_timer_speech=lambda: None,
            listen=lambda: None,
            quit_requested=lambda: False,
            on_quit=lambda: None,
        )
        self.assertEqual(result.utterance, "later")


if __name__ == "__main__":
    unittest.main()
