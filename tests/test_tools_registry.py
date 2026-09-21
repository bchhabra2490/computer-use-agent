"""Shared tool registry."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import tools_registry as tr  # noqa: E402


class ToolRegistryTests(unittest.TestCase):
    def test_orchestrator_has_start_task_not_computer(self) -> None:
        with (
            patch.dict("os.environ", {"COMPUTER_USE": "1"}, clear=False),
            patch("mcp_client.mcp_openai_tools", return_value=[]),
        ):
            names = [t.get("name") or t.get("type") for t in tr.orchestrator_tools()]
        self.assertIn("start_task", names)
        self.assertIn("give_response_to_user", names)
        self.assertIn("send_chat_message", names)
        self.assertIn("who_am_i", names)
        self.assertIn("ask_user", names)
        self.assertIn("list_open_apps", names)
        self.assertIn("read_screen", names)
        self.assertIn("set_timer", names)
        self.assertIn("schedule_task", names)
        self.assertIn("list_scheduled_tasks", names)
        self.assertIn("cancel_scheduled_task", names)
        self.assertIn("send_chat_message", names)
        self.assertNotIn("computer", names)
        self.assertNotIn("mark_done", names)

    def test_stt_repair_is_in_ask_user_and_start_task(self) -> None:
        self.assertIn(
            "speech-to-text mishear",
            tr.ASK_USER_TOOL["description"].lower(),
        )
        self.assertIn(
            "Ashtavakra Gita",
            tr.START_TASK_TOOL["parameters"]["properties"]["task"]["description"],
        )

    def test_orchestrator_hides_start_task_when_computer_use_off(self) -> None:
        with (
            patch.dict("os.environ", {"COMPUTER_USE": "0"}, clear=False),
            patch("mcp_client.mcp_openai_tools", return_value=[]),
        ):
            names = [t.get("name") or t.get("type") for t in tr.orchestrator_tools()]
            self.assertNotIn("start_task", names)
            self.assertIn("give_response_to_user", names)
            self.assertFalse(tr.computer_use_enabled())

    def test_agent_has_computer_not_start_task(self) -> None:
        with patch("mcp_client.mcp_openai_tools", return_value=[]):
            names = [t.get("name") or t.get("type") for t in tr.agent_tools()]
        self.assertIn("computer", names)
        self.assertIn("mark_done", names)
        self.assertIn("who_am_i", names)
        self.assertIn("list_open_apps", names)
        self.assertIn("read_screen", names)
        self.assertIn("set_timer", names)
        self.assertIn("schedule_task", names)
        self.assertIn("list_scheduled_tasks", names)
        self.assertIn("cancel_scheduled_task", names)
        self.assertIn("jev_choose", names)
        self.assertNotIn("start_task", names)
        self.assertNotIn("give_response_to_user", names)
        self.assertNotIn("desktop_actions", names)

    def test_jev_choose_hidden_when_disabled(self) -> None:
        with (
            patch("mcp_client.mcp_openai_tools", return_value=[]),
            patch("jev.config.jev_choose_tool_enabled", return_value=False),
        ):
            names = [t.get("name") or t.get("type") for t in tr.agent_tools()]
        self.assertNotIn("jev_choose", names)
    def test_agent_deepseek_uses_desktop_actions(self) -> None:
        with patch("mcp_client.mcp_openai_tools", return_value=[]):
            names = [
                t.get("name") or t.get("type")
                for t in tr.agent_tools(provider="deepseek")
            ]
        self.assertIn("desktop_actions", names)
        self.assertNotIn("computer", names)
        self.assertIn("mark_done", names)

    def test_shared_list_open_apps(self) -> None:
        with patch(
            "displays.format_monitor_occupancy",
            return_value="Running apps:\n  - Notes",
        ):
            out = tr.run_shared_tool("list_open_apps", {"unused": False})
        self.assertIn("Running apps", out)

    def test_run_terminal_forbids_media_sleep(self) -> None:
        desc = tr.RUN_TERMINAL_TOOL["description"].lower()
        self.assertIn("sleep", desc)
        self.assertIn("say", desc)

    def test_send_chat_message_dispatches(self) -> None:
        with patch(
            "chat_bridge.post_assistant_message",
            return_value={"chat_id": "abc", "message_id": "m1", "opened": False},
        ) as post:
            outcome = tr.run_tool(
                "send_chat_message",
                {"message": "Put this in chat", "open_window": False},
                brain="agent",
            )
        self.assertFalse(outcome.is_error)
        self.assertIn("abc", outcome.output)
        post.assert_called_once_with("Put this in chat", open_window=False)

    def test_schedule_error_is_machine_readable(self) -> None:
        outcome = tr.run_tool(
            "schedule_task",
            {"task": "", "run_at_epoch": 1, "source": "user", "parent_task_id": None, "note": None},
            brain="orchestrator",
        )
        self.assertTrue(outcome.is_error)
        self.assertTrue(str(outcome.output).startswith("Error:"))

    def test_schedule_rejects_malformed_epoch(self) -> None:
        cases = ([1, 2], {"at": 1}, float("inf"), float("nan"), "inf", True)
        for value in cases:
            outcome = tr.run_tool(
                "schedule_task",
                {"task": "later", "run_at_epoch": value, "source": "user"},
                brain="orchestrator",
            )
            self.assertTrue(outcome.is_error, value)
            self.assertIn("run_at_epoch", str(outcome.output))

    def test_unknown_shared_raises(self) -> None:
        with self.assertRaises(KeyError):
            tr.run_shared_tool("start_task", {"task": "x"})
        out = tr.prepare_tool_call("start_task", {"task": "x"}, brain="orchestrator")
        self.assertIsInstance(out, tr.ImmediateToolOutcome)

    def test_registry_traces_handler_tools_only(self) -> None:
        from llm_trace import registry_traces_tool

        self.assertTrue(registry_traces_tool("schedule_task"))
        self.assertTrue(registry_traces_tool("search_memories"))
        self.assertFalse(registry_traces_tool("start_task"))
        self.assertFalse(registry_traces_tool("give_response_to_user"))

    def test_handlers_live_on_registry_entries(self) -> None:
        self.assertTrue(tr.has_handler("list_open_apps"))
        self.assertTrue(tr.has_handler("schedule_task"))
        self.assertTrue(tr.has_handler("search_memories"))
        self.assertTrue(tr.has_handler("send_chat_message"))
        self.assertTrue(tr.has_handler("browser_data"))
        self.assertTrue(tr.has_handler("browser_webmcp"))
        self.assertTrue(tr.has_handler("mcp_call"))
        self.assertTrue(tr.has_handler("jev_choose"))
        for name in (
            "start_task",
            "ask_user",
            "give_response_to_user",
            "mark_done",
            "list_skills",
            "read_skill",
            "read_ui_text",
            "run_terminal",
        ):
            self.assertFalse(tr.has_handler(name), name)
        self.assertIn("schedule_task", tr.SHARED_TOOL_NAMES)
        self.assertNotIn("start_task", tr.SHARED_TOOL_NAMES)

    def test_run_tool_records_outcome_once(self) -> None:
        with patch("tools_registry._record_run") as record:
            tr.run_tool(
                "schedule_task",
                {"task": "", "run_at_epoch": 1, "source": "user"},
                brain="orchestrator",
            )
        record.assert_called_once()
        with (
            patch("displays.format_monitor_occupancy", return_value="ok"),
            patch("tools_registry._record_run") as record,
        ):
            tr.run_tool("list_open_apps", {"unused": False}, brain="orchestrator")
        record.assert_called_once()

    def test_mcp_call_schema_not_duplicated(self) -> None:
        with patch("mcp_client.mcp_openai_tools", return_value=[{"type": "function", "name": "mcp_call"}]):
            names = [t.get("name") for t in tr.orchestrator_tools()]
        self.assertEqual(names.count("mcp_call"), 1)


if __name__ == "__main__":
    unittest.main()
