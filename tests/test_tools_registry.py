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
        with patch("mcp_client.mcp_openai_tools", return_value=[]):
            names = [t.get("name") or t.get("type") for t in tr.orchestrator_tools()]
        self.assertIn("start_task", names)
        self.assertIn("give_response_to_user", names)
        self.assertIn("who_am_i", names)
        self.assertIn("ask_user", names)
        self.assertIn("list_open_apps", names)
        self.assertIn("http_get", names)
        self.assertIn("web_search", names)
        self.assertIn("set_timer", names)
        self.assertNotIn("computer", names)
        self.assertNotIn("mark_done", names)

    def test_agent_has_computer_not_start_task(self) -> None:
        with patch("mcp_client.mcp_openai_tools", return_value=[]):
            names = [t.get("name") or t.get("type") for t in tr.agent_tools()]
        self.assertIn("computer", names)
        self.assertIn("mark_done", names)
        self.assertIn("who_am_i", names)
        self.assertIn("list_open_apps", names)
        self.assertIn("set_timer", names)
        self.assertNotIn("start_task", names)
        self.assertNotIn("give_response_to_user", names)

    def test_orchestrator_can_omit_start_task(self) -> None:
        with patch("mcp_client.mcp_openai_tools", return_value=[]):
            names = [
                t.get("name") or t.get("type")
                for t in tr.orchestrator_tools(exclude=frozenset({"start_task"}))
            ]
        self.assertNotIn("start_task", names)
        self.assertIn("give_response_to_user", names)
        self.assertIn("http_get", names)
        self.assertIn("web_search", names)

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

    def test_unknown_shared_raises(self) -> None:
        with self.assertRaises(KeyError):
            tr.run_shared_tool("start_task", {"task": "x"})


if __name__ == "__main__":
    unittest.main()
