"""Tests for MCP browser-login helpers (no live OAuth)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cua  # noqa: E402
import mcp_auth as ma  # noqa: E402
import mcp_client as mc  # noqa: E402


class ResolveAppTests(unittest.TestCase):
    def test_known_linear(self) -> None:
        app = ma.resolve_app("Linear")
        self.assertEqual(app.name, "linear")
        self.assertEqual(app.url, "https://mcp.linear.app/mcp")

    def test_custom_url(self) -> None:
        app = ma.resolve_app("acme", url="https://mcp.acme.test/mcp")
        self.assertEqual(app.name, "acme")
        self.assertEqual(app.url, "https://mcp.acme.test/mcp")

    def test_unknown_without_url(self) -> None:
        with self.assertRaises(ValueError):
            ma.resolve_app("not-a-real-app")


class TokenStorageTests(unittest.TestCase):
    def test_roundtrip_and_clear(self) -> None:
        from mcp.shared.auth import OAuthToken

        with tempfile.TemporaryDirectory() as tmp:
            storage = ma.FileTokenStorage("linear", directory=Path(tmp))
            self.assertFalse(storage.has_tokens())

            async def _run() -> None:
                await storage.set_tokens(
                    OAuthToken(access_token="tok_abc", token_type="Bearer")
                )

            import asyncio

            asyncio.run(_run())
            self.assertTrue(storage.has_tokens())
            raw = json.loads(storage.path.read_text(encoding="utf-8"))
            self.assertEqual(raw["tokens"]["access_token"], "tok_abc")
            storage.clear()
            self.assertFalse(storage.has_tokens())
            self.assertFalse(storage.path.exists())


class ConfigUpsertTests(unittest.TestCase):
    def test_upsert_enables_oauth_and_strips_bearer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mcp.json"
            path.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "linear": {
                                "url": "https://old.example/mcp",
                                "headers": {"Authorization": "Bearer secret"},
                                "disabled": True,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            ma.upsert_oauth_server(
                "linear",
                "https://mcp.linear.app/mcp",
                path=path,
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            spec = data["mcpServers"]["linear"]
            self.assertEqual(spec["url"], "https://mcp.linear.app/mcp")
            self.assertEqual(spec["auth"], "oauth")
            self.assertNotIn("disabled", spec)
            self.assertNotIn("headers", spec)

            servers = mc.load_mcp_config(path, environ={})
            self.assertEqual(servers["linear"].auth, "oauth")
            self.assertEqual(servers["linear"].url, "https://mcp.linear.app/mcp")


    def test_github_login_uses_gh_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "mcp.json"
            auth_dir = Path(tmp) / "auth"
            dummy = type("S", (), {"name": "github", "url": "https://api.githubcopilot.com/mcp/", "headers": {}})()
            with (
                patch.object(ma, "AUTH_DIR", auth_dir),
                patch.object(ma, "MCP_CONFIG_PATH", cfg),
                patch.object(ma, "_gh_token", return_value="ghp_test_token"),
            ):
                msg = ma.login_with_bearer(ma.resolve_app("github"))
                auth = ma.oauth_httpx_auth(dummy)
            self.assertIn("GitHub", msg)
            storage = ma.FileTokenStorage("github", directory=auth_dir)
            self.assertTrue(storage.has_tokens())
            self.assertEqual(storage.kind(), "token")
            spec = json.loads(cfg.read_text())["mcpServers"]["github"]
            self.assertEqual(spec["auth"], "token")
            self.assertIsInstance(auth, ma.BearerTokenAuth)

    def test_github_without_gh_explains_install(self) -> None:
        with (
            patch.object(ma, "_gh_bin", return_value=None),
            patch.object(ma, "_gh_token", return_value=None),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                ma.login_with_bearer(ma.resolve_app("github"))
        self.assertIn("brew install gh", str(ctx.exception))

    def test_load_token_auth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mcp.json"
            path.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "github": {
                                "url": "https://api.githubcopilot.com/mcp/",
                                "auth": "token",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            servers = mc.load_mcp_config(path, environ={})
            self.assertEqual(servers["github"].auth, "token")
    def test_mcp_apps_lists_linear(self) -> None:
        self.assertEqual(cua.main(["mcp", "apps"]), 0)

    def test_mcp_status_when_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(ma, "AUTH_DIR", Path(tmp)):
                self.assertEqual(cua.main(["mcp", "status"]), 0)


if __name__ == "__main__":
    unittest.main()
