"""Tests for MCP config, read-only gating, and a live stdio echo server."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mcp_client as mc  # noqa: E402

ECHO_SERVER = ROOT / "tests" / "fixtures" / "echo_mcp_server.py"


class ConfigTests(unittest.TestCase):
    def test_expand_env_and_defaults(self) -> None:
        env = {"GITHUB_TOKEN": "secret-token"}
        self.assertEqual(mc.expand_env_value("${GITHUB_TOKEN}", env), "secret-token")
        self.assertEqual(mc.expand_env_value("${MISSING:-fallback}", env), "fallback")
        self.assertEqual(mc.expand_env_value("${MISSING}", env), "")

    def test_load_mcp_json_and_enable_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mcp.json"
            path.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "github": {
                                "command": "npx",
                                "args": ["-y", "@modelcontextprotocol/server-github"],
                                "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"},
                            },
                            "off": {"command": "echo", "disabled": True},
                            "linear": {
                                "url": "https://mcp.linear.app/mcp",
                                "headers": {"Authorization": "Bearer ${LINEAR_KEY}"},
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            environ = {
                "GITHUB_TOKEN": "gh-secret",
                "LINEAR_KEY": "lin-secret",
                "MCP_ENABLE": "github",
            }
            servers = mc.load_mcp_config(path, environ=environ)
            self.assertEqual(set(servers), {"github"})
            self.assertEqual(servers["github"].command, "npx")
            self.assertEqual(servers["github"].env["GITHUB_PERSONAL_ACCESS_TOKEN"], "gh-secret")

            environ2 = {
                "GITHUB_TOKEN": "gh-secret",
                "LINEAR_KEY": "lin-secret",
            }
            all_servers = mc.load_mcp_config(path, environ=environ2)
            self.assertEqual(set(all_servers), {"github", "linear"})
            self.assertEqual(all_servers["linear"].transport, "http")
            self.assertEqual(all_servers["linear"].headers["Authorization"], "Bearer lin-secret")

    def test_parse_arguments_and_redact(self) -> None:
        self.assertEqual(mc.parse_mcp_arguments("{}"), {})
        self.assertEqual(mc.parse_mcp_arguments('{"q":"hi"}'), {"q": "hi"})
        self.assertEqual(mc.parse_mcp_arguments({"q": "hi"}), {"q": "hi"})
        redacted = mc.redact_for_log({"token": "abc", "q": "hi"})
        self.assertEqual(redacted["token"], "***")
        self.assertEqual(redacted["q"], "hi")


class ReadOnlyTests(unittest.TestCase):
    def test_name_heuristic(self) -> None:
        self.assertTrue(mc.tool_is_read_only("list_issues"))
        self.assertTrue(mc.tool_is_read_only("get_issue"))
        self.assertTrue(mc.tool_is_read_only("search"))
        self.assertFalse(mc.tool_is_read_only("create_issue"))
        self.assertFalse(mc.tool_is_read_only("delete_item"))
        self.assertFalse(mc.tool_is_read_only("send_message"))

    def test_annotation_overrides_name(self) -> None:
        self.assertTrue(mc.tool_is_read_only("create_issue", {"readOnlyHint": True}))
        self.assertFalse(mc.tool_is_read_only("search", {"readOnlyHint": False}))


@unittest.skipUnless(ECHO_SERVER.is_file(), "echo fixture missing")
class LiveStdioTests(unittest.TestCase):
    def setUp(self) -> None:
        mc.stop_mcp()
        self.specs = {
            "echo": mc.ServerSpec(
                name="echo",
                command=sys.executable,
                args=[str(ECHO_SERVER)],
                transport="stdio",
            )
        }

    def tearDown(self) -> None:
        mc.stop_mcp()

    def test_echo_and_add(self) -> None:
        mgr = mc.start_mcp(specs=self.specs)
        self.assertTrue(mgr.connected)
        names = {t.name for t in mgr.tools()}
        self.assertIn("echo", names)
        self.assertIn("add", names)
        out = mgr.call("echo", "echo", {"text": "hello"})
        self.assertIn("hello", out)
        summed = mgr.call("echo", "add", {"a": 2, "b": 3})
        self.assertIn("5", summed)
        catalog = mgr.catalog_text()
        self.assertIn("echo", catalog)
        tools = mc.mcp_openai_tools()
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["name"], "mcp_call")
        via_tool = mc.run_mcp_tool(
            "mcp_call",
            {"server": "echo", "tool": "echo", "arguments": '{"text":"via-tool"}'},
        )
        self.assertIn("via-tool", via_tool)

    def test_read_only_blocks_delete(self) -> None:
        with patch.object(mc, "MCP_READ_ONLY", True):
            mgr = mc.start_mcp(specs=self.specs)
            blocked = mgr.call("echo", "delete_item", {"item_id": "x"})
            self.assertIn("MCP_READ_ONLY", blocked)
            allowed = mgr.call("echo", "echo", {"text": "ok"})
            self.assertIn("ok", allowed)


if __name__ == "__main__":
    unittest.main()
