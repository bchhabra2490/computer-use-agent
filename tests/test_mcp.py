"""Tests for MCP config, read-only gating, and a live stdio echo server."""

from __future__ import annotations

import asyncio
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


class ConnectErrorIsolationTests(unittest.TestCase):
    def test_mcp_error_text_unwraps_taskgroup(self) -> None:
        inner = RuntimeError("MCP linear session expired. Run: cua mcp login linear")
        group = ExceptionGroup("unhandled errors in a TaskGroup", [inner])
        text = mc._mcp_error_text(group)
        self.assertIn("session expired", text)
        self.assertNotIn("\n", text)

    def test_start_survives_connect_exception_group(self) -> None:
        group = ExceptionGroup(
            "unhandled errors in a TaskGroup",
            [RuntimeError("MCP linear session expired. Run: cua mcp login linear")],
        )
        mgr = mc.McpManager(
            specs={
                "linear": mc.ServerSpec(
                    name="linear",
                    url="https://example.test/mcp",
                    transport="http",
                )
            }
        )
        with (
            patch.object(mgr, "_submit", side_effect=group),
            patch("threading.Thread.start", lambda self: None),
        ):
            mgr.start()
        self.assertTrue(mgr._started)
        if mgr._loop is not None:
            mgr._loop.close()
            mgr._loop = None

    def test_start_survives_timeout(self) -> None:
        mgr = mc.McpManager(
            specs={
                "linear": mc.ServerSpec(
                    name="linear",
                    url="https://example.test/mcp",
                    transport="http",
                )
            }
        )
        with (
            patch.object(mgr, "_submit", side_effect=mc.concurrent.futures.TimeoutError()),
            patch("threading.Thread.start", lambda self: None),
        ):
            mgr.start()
        self.assertTrue(mgr._started)
        if mgr._loop is not None:
            mgr._loop.close()
            mgr._loop = None


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


    def test_ensure_connected_retries_http_server(self) -> None:
        spec = mc.ServerSpec(
            name="morning",
            url="http://127.0.0.1:9/api/mcp",
            transport="http",
        )
        mgr = mc.McpManager(specs={"morning": spec})
        mgr._started = True
        mgr._loop = asyncio.new_event_loop()

        async def fake_connect(s: mc.ServerSpec) -> None:
            mgr._servers[s.name] = mc._LiveServer(
                spec=s,
                session=object(),
                tools=[
                    mc.McpTool(
                        server=s.name,
                        name="get_briefing",
                        description="Get briefing",
                        read_only=True,
                    )
                ],
            )

        with patch.object(mgr, "_submit", side_effect=lambda coro, timeout: mgr._loop.run_until_complete(coro)):
            with patch.object(mgr, "_connect_one", side_effect=fake_connect):
                err = mgr.ensure_connected("morning")
        self.assertIsNone(err)
        self.assertIsNotNone(mgr._servers["morning"].session)
        mgr._loop.close()
        mgr._loop = None

    def test_call_reconnects_before_tool(self) -> None:
        spec = mc.ServerSpec(name="echo", command="unused", transport="stdio")
        mgr = mc.McpManager(specs={"echo": spec})
        mgr._started = True
        mgr._loop = asyncio.new_event_loop()
        session = object()

        async def fake_connect(s: mc.ServerSpec) -> None:
            mgr._servers[s.name] = mc._LiveServer(
                spec=s,
                session=session,
                tools=[
                    mc.McpTool(
                        server=s.name,
                        name="ping",
                        description="Ping",
                        read_only=True,
                    )
                ],
            )

        with (
            patch.object(mgr, "_submit", side_effect=lambda coro, timeout: mgr._loop.run_until_complete(coro)),
            patch.object(mgr, "_connect_one", side_effect=fake_connect),
            patch.object(mgr, "_call_async", return_value=asyncio.sleep(0, result="pong")),
        ):
            # _call_async is awaited via _submit — patch _submit for call path too after connect.
            calls = {"n": 0}

            def submit(coro, timeout):
                calls["n"] += 1
                if calls["n"] == 1:
                    return mgr._loop.run_until_complete(coro)
                # second submit is the tool call
                return "pong"

            with patch.object(mgr, "_submit", side_effect=submit):
                with patch.object(mgr, "_connect_one", side_effect=fake_connect):
                    out = mgr.call("echo", "ping", {})
        self.assertEqual(out, "pong")
        mgr._loop.close()
        mgr._loop = None


if __name__ == "__main__":
    unittest.main()
