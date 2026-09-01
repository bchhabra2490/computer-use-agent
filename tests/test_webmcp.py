"""WebMCP discovery, validation, and mutation-boundary tests."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import tools_registry as tr  # noqa: E402
import webmcp  # noqa: E402


READ_TOOL = {
    "name": "search_docs",
    "title": "Search docs",
    "description": "Search documentation.",
    "origin": "https://example.com",
    "inputSchema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "untrustedContentHint": True},
}


def discovery(tool=READ_TOOL):
    return {
        "supported": True,
        "url": "https://example.com/docs",
        "title": "Docs",
        "origin": "https://example.com",
        "tools": [tool],
    }


class WebMCPTests(unittest.TestCase):
    def test_list_returns_origin_scoped_tools(self) -> None:
        with patch.object(webmcp, "_validate_public_url"), patch.object(
            webmcp, "_persistent_bridge", return_value=discovery()
        ):
            result = webmcp.list_webmcp_tools("https://example.com/docs")
        self.assertEqual(result["backend"], "chromium-webmcp")
        self.assertEqual(result["tools"][0]["origin"], "https://example.com")

    def test_read_only_call_validates_schema_and_executes(self) -> None:
        executed = {
            "supported": True,
            "url": "https://example.com/docs",
            "origin": "https://example.com",
            "tool": READ_TOOL,
            "result": "Match",
            "navigated": False,
        }
        with patch.object(webmcp, "_validate_public_url"), patch.object(
            webmcp, "_persistent_bridge", side_effect=[discovery(), executed]
        ) as bridge:
            result = webmcp.call_webmcp_tool(
                "https://example.com/docs", "search_docs", {"query": "WebMCP"}
            )
        self.assertEqual(result["result"], "Match")
        self.assertEqual(bridge.call_args_list[1].args[0]["expected_origin"], "https://example.com")

    def test_schema_rejects_bad_arguments_before_execution(self) -> None:
        with patch.object(webmcp, "_validate_public_url"), patch.object(
            webmcp, "_persistent_bridge", return_value=discovery()
        ) as bridge:
            with self.assertRaisesRegex(webmcp.WebMCPError, "schema type"):
                webmcp.call_webmcp_tool("https://example.com/docs", "search_docs", {"query": 42})
        self.assertEqual(bridge.call_count, 1)

    def test_mutating_tool_requires_explicit_permission(self) -> None:
        mutating = dict(READ_TOOL)
        mutating["name"] = "add_to_cart"
        mutating["annotations"] = {"readOnlyHint": False, "untrustedContentHint": False}
        with patch.object(webmcp, "_validate_public_url"), patch.object(
            webmcp, "_persistent_bridge", return_value=discovery(mutating)
        ) as bridge:
            result = webmcp.call_webmcp_tool(
                "https://example.com/shop", "add_to_cart", {"query": "item"}
            )
        self.assertTrue(result["confirmation_required"])
        self.assertEqual(bridge.call_count, 1)

    def test_run_tool_parses_arguments_json(self) -> None:
        with patch.object(webmcp, "call_webmcp_tool", return_value={"result": "ok"}) as call:
            payload = json.loads(
                webmcp.run_webmcp_tool(
                    {
                        "url": "https://example.com",
                        "operation": "call",
                        "tool_name": "search_docs",
                        "arguments_json": '{"query":"x"}',
                        "allow_mutation": False,
                    }
                )
            )
        self.assertEqual(payload["result"], "ok")
        self.assertEqual(call.call_args.args[2], {"query": "x"})

    def test_calls_reuse_the_same_page_session(self) -> None:
        class FakeProcess:
            def poll(self):
                return None

        class FakeSession:
            def __init__(self, url, *, timeout):
                self.id = "session-1"
                self.process = FakeProcess()
                self.requests = []

            def request(self, payload, *, timeout):
                self.requests.append(payload)
                return discovery()

            def close(self):
                pass

        webmcp.close_webmcp_sessions()
        with patch.object(webmcp, "_BridgeSession", FakeSession):
            first = webmcp._persistent_bridge(
                {"url": "https://example.com/docs", "operation": "list"}, timeout=5
            )
            second = webmcp._persistent_bridge(
                {"url": "https://example.com/docs", "operation": "list"}, timeout=5
            )
        self.assertEqual(first["origin"], second["origin"])
        self.assertEqual(len(webmcp._SESSIONS), 1)
        self.assertEqual(len(next(iter(webmcp._SESSIONS.values())).requests), 2)
        webmcp.close_webmcp_sessions()

    def test_tool_is_available_to_both_brains(self) -> None:
        with patch("mcp_client.mcp_openai_tools", return_value=[]):
            orchestrator = {tool.get("name") for tool in tr.orchestrator_tools()}
            agent = {tool.get("name") for tool in tr.agent_tools()}
        self.assertIn("browser_webmcp", orchestrator)
        self.assertIn("browser_webmcp", agent)


if __name__ == "__main__":
    unittest.main()
