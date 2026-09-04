"""Tests for safe structured webpage retrieval."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import browser_data as bd  # noqa: E402
import tools_registry as tr  # noqa: E402


class _Headers(dict):
    def get(self, key: str, default=None):
        return super().get(key, default)


class _Response:
    status = 200

    def __init__(self, body: bytes, content_type: str = "text/html; charset=utf-8") -> None:
        self.body = body
        self.headers = _Headers({"Content-Type": content_type})

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self) -> str:
        return "https://example.com/final"

    def read(self, size: int) -> bytes:
        return self.body[:size]


class _Opener:
    def __init__(self, response: _Response) -> None:
        self.response = response

    def open(self, _request, timeout: float):
        self.timeout = timeout
        return self.response


class BrowserDataTests(unittest.TestCase):
    def test_parser_extracts_markdown_and_absolute_links(self) -> None:
        html = b"""<html><head><title> Demo Page </title><script>ignore me</script></head>
        <body><h1>Hello world</h1><p>A useful paragraph.</p>
        <a href='/docs'>Read docs</a></body></html>"""
        with patch.object(bd, "build_opener", return_value=_Opener(_Response(html))), patch.object(
            bd, "_validate_public_url"
        ):
            result = bd.fetch_page("https://example.com")
        self.assertEqual(result.title, "Demo Page")
        self.assertIn("# Hello world", result.markdown)
        self.assertNotIn("ignore me", result.markdown)
        self.assertEqual(result.links[0].url, "https://example.com/docs")

    def test_javascript_shell_requests_lightpanda_fallback(self) -> None:
        html = b"<html><body><div id='root'></div><script src='app.js'></script></body></html>"
        with patch.object(bd, "build_opener", return_value=_Opener(_Response(html))), patch.object(
            bd, "_validate_public_url"
        ):
            result = bd.fetch_page("https://example.com")
        self.assertEqual(result.fallback_required, "lightpanda")

    def test_rejects_unsafe_urls_before_fetch(self) -> None:
        for url in ("file:///etc/passwd", "http://localhost/x", "http://127.0.0.1/x"):
            with self.subTest(url=url):
                payload = json.loads(bd.run_browser_data_tool({"url": url}))
                self.assertIn("error", payload)

    def test_extract_filters_blocks(self) -> None:
        page = bd.PageResult("https://example.com", "https://example.com", markdown="Alpha one\nBeta two\nAlpha three")
        with patch.object(bd, "fetch_page", return_value=page):
            payload = json.loads(
                bd.run_browser_data_tool({"url": "https://example.com", "operation": "extract", "query": "alpha"})
            )
        self.assertEqual(payload["matched_blocks"], 2)
        self.assertNotIn("Beta", payload["markdown"])

    def test_tool_is_shared_by_both_brains(self) -> None:
        with patch("mcp_client.mcp_openai_tools", return_value=[]):
            orchestrator = {tool.get("name") for tool in tr.orchestrator_tools()}
            agent = {tool.get("name") for tool in tr.agent_tools()}
        self.assertIn("browser_data", orchestrator)
        self.assertIn("browser_data", agent)

    def test_lightpanda_uses_guarded_one_shot_fetch(self) -> None:
        output = json.dumps(
            {
                "url": "https://example.com/app",
                "http_status": 200,
                "dump": "markdown",
                "content": "# Rendered app\n\nLoaded with JavaScript.\n\n[Details](/details)",
            }
        )
        completed = SimpleNamespace(returncode=0, stdout=output, stderr="")
        with patch.object(bd, "_validate_public_url"), patch.object(
            bd, "_lightpanda_binary", return_value="/opt/lightpanda"
        ), patch.object(bd.subprocess, "run", return_value=completed) as run:
            result = bd.fetch_lightpanda("https://example.com/app")
        command = run.call_args.args[0]
        self.assertIn("--obey-robots", command)
        self.assertIn("--terminate-ms", command)
        self.assertEqual(result.backend, "lightpanda")
        self.assertEqual(result.title, "Rendered app")
        self.assertEqual(result.links[0].url, "https://example.com/details")
        self.assertEqual(run.call_args.kwargs["env"]["LIGHTPANDA_DISABLE_TELEMETRY"], "true")

    def test_auto_escalates_javascript_shell_to_lightpanda(self) -> None:
        static = bd.PageResult(
            "https://example.com/app",
            "https://example.com/app",
            markdown="",
            fallback_required="lightpanda",
            attempts=[{"backend": "http", "ok": True}],
        )
        rendered = bd.PageResult(
            "https://example.com/app",
            "https://example.com/app",
            markdown="# App\nRendered data",
            backend="lightpanda",
            attempts=[{"backend": "lightpanda", "ok": True}],
        )
        with patch.object(bd, "fetch_page", return_value=static), patch.object(
            bd, "fetch_lightpanda", return_value=rendered
        ):
            payload = json.loads(bd.run_browser_data_tool({"url": "https://example.com/app", "backend": "auto"}))
        self.assertEqual(payload["backend"], "lightpanda")
        self.assertEqual([item["backend"] for item in payload["attempts"]], ["http", "lightpanda"])

    def test_failed_lightpanda_automatically_runs_chromium(self) -> None:
        static = bd.PageResult(
            "https://example.com/app",
            "https://example.com/app",
            fallback_required="lightpanda",
        )
        chromium = bd.PageResult(
            "https://example.com/app",
            "https://example.com/app",
            markdown="# Chromium result",
            backend="chromium",
            attempts=[{"backend": "chromium", "ok": True}],
        )
        with patch.object(bd, "fetch_page", return_value=static), patch.object(
            bd, "fetch_lightpanda", side_effect=bd.BrowserDataError("binary unavailable")
        ), patch.object(
            bd, "fetch_chromium", return_value=chromium
        ):
            payload = json.loads(bd.run_browser_data_tool({"url": "https://example.com/app", "backend": "auto"}))
        self.assertEqual(payload["backend"], "chromium")
        self.assertEqual(
            [item["backend"] for item in payload["attempts"]],
            ["lightpanda", "chromium"],
        )

    def test_chromium_uses_fresh_profile_and_rendered_dom(self) -> None:
        html = """<html><head><title>Rendered</title></head><body>
        <h1>Chromium page</h1><a href='/next'>Next</a></body></html>"""
        completed = SimpleNamespace(returncode=0, stdout=html, stderr="")
        with patch.object(bd, "_validate_public_url"), patch.object(
            bd, "_chromium_binary", return_value="/opt/chromium"
        ), patch.object(bd.subprocess, "run", return_value=completed) as run:
            result = bd.fetch_chromium("https://example.com/app")
        command = run.call_args.args[0]
        profile_arg = next(item for item in command if item.startswith("--user-data-dir="))
        self.assertIn("--headless", command)
        self.assertIn("--dump-dom", command)
        self.assertFalse(Path(profile_arg.split("=", 1)[1]).exists())
        self.assertEqual(result.backend, "chromium")
        self.assertEqual(result.title, "Rendered")
        self.assertEqual(result.links[0].url, "https://example.com/next")

    def test_failed_chromium_requests_visible_desktop_fallback(self) -> None:
        with patch.object(bd, "fetch_chromium", side_effect=bd.BrowserDataError("renderer crashed")):
            payload = json.loads(
                bd.run_browser_data_tool({"url": "https://example.com/app", "backend": "chromium"})
            )
        self.assertEqual(payload["fallback_required"], "desktop")

    def test_endpoint_discovery_ranks_and_replays_relevant_json(self) -> None:
        observed = {
            "supported": True,
            "endpoints": [
                {
                    "url": "https://example.com/api/navigation",
                    "status": 200,
                    "content_type": "application/json",
                    "resource_type": "Fetch",
                    "body": '{"items":["home","about"]}',
                },
                {
                    "url": "https://example.com/api/forecast?city=mohali",
                    "status": 200,
                    "content_type": "application/json",
                    "resource_type": "XHR",
                    "body": '{"location":"Mohali","hourly":[{"rain_probability":25}]}',
                },
            ],
        }
        completed = SimpleNamespace(returncode=0, stdout=json.dumps(observed), stderr="")
        replay = bd.PageResult(
            "https://example.com/api/forecast?city=mohali",
            "https://example.com/api/forecast?city=mohali",
            content_type="application/json",
            markdown='{"location":"Mohali","hourly":[{"rain_probability":25}]}',
        )
        with (
            patch.object(bd, "_validate_public_url"),
            patch.object(bd, "_chromium_binary", return_value="/opt/chromium"),
            patch.object(bd.shutil, "which", return_value="/opt/node"),
            patch.object(bd.subprocess, "run", return_value=completed),
            patch.object(bd, "fetch_page", return_value=replay),
        ):
            payload = bd.discover_endpoints(
                "https://example.com/weather", query="Mohali hourly rain forecast"
            )
        self.assertEqual(
            payload["selected_endpoint"],
            "https://example.com/api/forecast?city=mohali",
        )
        self.assertEqual(payload["selected_source"], "safe_http_replay")
        self.assertIn("rain_probability", json.dumps(payload["data"]))
        self.assertIsNone(payload["fallback_required"])

    def test_endpoint_discovery_falls_back_when_no_json_is_observed(self) -> None:
        completed = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"supported": True, "endpoints": []}),
            stderr="",
        )
        with (
            patch.object(bd, "_validate_public_url"),
            patch.object(bd, "_chromium_binary", return_value="/opt/chromium"),
            patch.object(bd.shutil, "which", return_value="/opt/node"),
            patch.object(bd.subprocess, "run", return_value=completed),
        ):
            payload = bd.discover_endpoints("https://example.com", query="weather")
        self.assertEqual(payload["fallback_required"], "desktop")
        self.assertIsNone(payload["selected_endpoint"])

    def test_endpoint_discovery_rejects_irrelevant_json(self) -> None:
        observed = {
            "supported": True,
            "endpoints": [{
                "url": "https://example.com/api/navigation",
                "status": 200,
                "content_type": "application/json",
                "resource_type": "Fetch",
                "body": '{"items":["home","about"]}',
            }],
        }
        completed = SimpleNamespace(returncode=0, stdout=json.dumps(observed), stderr="")
        with (
            patch.object(bd, "_validate_public_url"),
            patch.object(bd, "_chromium_binary", return_value="/opt/chromium"),
            patch.object(bd.shutil, "which", return_value="/opt/node"),
            patch.object(bd.subprocess, "run", return_value=completed),
        ):
            payload = bd.discover_endpoints(
                "https://example.com/weather", query="Mohali rain forecast"
            )
        self.assertIsNone(payload["selected_endpoint"])
        self.assertEqual(payload["fallback_required"], "desktop")

    def test_tool_schema_exposes_endpoint_discovery(self) -> None:
        operations = tr.BROWSER_DATA_TOOL["parameters"]["properties"]["operation"]["enum"]
        self.assertIn("discover_endpoints", operations)


if __name__ == "__main__":
    unittest.main()
