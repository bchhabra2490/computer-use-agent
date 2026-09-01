"""Harness-inspired events, queues, checkpoint, and tool runtime."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import checkpoint as cp  # noqa: E402
import events as ev  # noqa: E402
import input_queues as iq  # noqa: E402
import tools_registry as tr  # noqa: E402
from context import TurnDesktopContext  # noqa: E402
from session_compact import SessionCompactState  # noqa: E402


class EventSinkTests(unittest.TestCase):
    def test_emit_and_listener(self) -> None:
        sink = ev.EventSink()
        seen: list[ev.Event] = []
        sink.on(seen.append)
        sink.emit("turn_start", utterance="hello")
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].type, "turn_start")
        self.assertEqual(seen[0].payload["utterance"], "hello")

    def test_throwing_listener_does_not_break_others(self) -> None:
        sink = ev.EventSink()
        ok: list[str] = []

        def bad(_e: ev.Event) -> None:
            raise RuntimeError("boom")

        def good(e: ev.Event) -> None:
            ok.append(e.type)

        sink.on(bad)
        sink.on(good)
        sink.emit("speak", text="hi")
        self.assertIn("speak", ok)
        self.assertIn("handler_error", ok)


class InputQueueTests(unittest.TestCase):
    def test_normalize_bus_kind(self) -> None:
        self.assertEqual(iq.normalize_bus_kind("user_message"), "steer")
        self.assertEqual(iq.normalize_bus_kind("follow_up"), "follow_up")
        self.assertEqual(iq.normalize_bus_kind("next-run"), "next_run")

    def test_classify_utterance(self) -> None:
        self.assertEqual(iq.classify_utterance_for_agent("click the button"), "steer")
        self.assertEqual(
            iq.classify_utterance_for_agent("when you're done open notes"),
            "follow_up",
        )
        self.assertEqual(
            iq.classify_utterance_for_agent("for later remind me to stretch"),
            "next_run",
        )

    def test_next_run_queue(self) -> None:
        q = iq.NextRunQueue()
        q.enqueue("do this next")
        items = q.drain()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "next_run")
        self.assertEqual(q.drain(), [])


class ToolRuntimeTests(unittest.TestCase):
    def test_prepare_unknown(self) -> None:
        out = tr.prepare_tool_call("not_a_real_tool", {})
        self.assertIsInstance(out, tr.ImmediateToolOutcome)
        assert isinstance(out, tr.ImmediateToolOutcome)
        self.assertTrue(out.outcome.is_error)

    def test_run_shared_list_open_apps(self) -> None:
        with patch(
            "displays.format_monitor_occupancy",
            return_value="Running apps:\n  - Notes",
        ):
            text = tr.run_shared_tool("list_open_apps", {"unused": False})
        self.assertIn("Running apps", text)

    def test_read_screen_in_shared(self) -> None:
        self.assertIn("read_screen", tr.SHARED_TOOL_NAMES)
        with patch.object(
            tr,
            "_execute_read_screen",
            return_value=tr.ToolOutcome(output="Screen read", screenshot_png=b"PNG"),
        ):
            out = tr.run_tool("read_screen", {"unused": False})
        self.assertEqual(out.output, "Screen read")
        self.assertEqual(out.screenshot_png, b"PNG")


class CheckpointTests(unittest.TestCase):
    def test_checkpoint_order(self) -> None:
        state = SessionCompactState()
        history = [{"task": "a", "result": "ok"}]
        desktop = TurnDesktopContext("desk", b"\x89PNG")
        q = iq.NextRunQueue()
        q.enqueue("later work")
        with (
            patch.object(cp, "maybe_compact_checkpoint", return_value=(history, False)) as compact,
            patch.object(cp, "capture_turn_desktop_context", return_value=desktop),
        ):
            result = cp.run_orchestrator_checkpoint(
                MagicMock(),
                state,
                history,
                pending_fn_outputs=[{"type": "function_call_output"}],
                next_run_queue=q,
                capture_desktop=True,
            )
        compact.assert_called_once()
        self.assertEqual(len(result.pending_fn_outputs), 1)
        self.assertEqual(len(result.next_run_messages), 1)
        self.assertEqual(result.desktop.text, "desk")
        self.assertFalse(result.reset_thread)


class PromptExtractTests(unittest.TestCase):
    def test_build_system_prompt(self) -> None:
        from orchestrator_prompts import build_system_prompt

        text = build_system_prompt(
            skills="skills",
            memories="memories",
            displays="Chrome {tab}",
            mcp="",
            not_to_do="don't",
            mcp_rule="",
            session_summary="Earlier: opened maps",
        )
        self.assertIn("Chrome {tab}", text)
        self.assertIn("Earlier: opened maps", text)
        self.assertIn("skills", text)
        self.assertIn("refer to memory first", text)
        self.assertIn("read_memory", text)

    def test_local_datetime_line_is_readable(self) -> None:
        from orchestrator_prompts import local_datetime_line

        line = local_datetime_line()
        self.assertTrue(line.startswith("Current local date and time:"))
        self.assertIn("202", line)  # year fragment


if __name__ == "__main__":
    unittest.main()
