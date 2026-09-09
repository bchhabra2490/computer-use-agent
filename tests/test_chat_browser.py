"""Serve the existing chat renderer from chat_bridge (browser mode)."""

from __future__ import annotations

import http.client
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import chat_bridge as cb  # noqa: E402
from chat_overlay import ensure_chat_bridge_and_app  # noqa: E402


class RendererPathTests(unittest.TestCase):
    def test_index_and_js(self) -> None:
        index = cb.renderer_file("/")
        self.assertIsNotNone(index)
        self.assertEqual(index.name, "index.html")
        js = cb.renderer_file("/app.js")
        self.assertIsNotNone(js)
        self.assertEqual(js.name, "app.js")
        shim = cb.renderer_file("/browser.js")
        self.assertIsNotNone(shim)
        self.assertIn(b"window.cuaChat", shim.read_bytes())

    def test_rejects_traversal(self) -> None:
        self.assertIsNone(cb.renderer_file("/../orchestrator.py"))
        self.assertIsNone(cb.renderer_file("/v1/chats"))


class RendererHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self._token = "test-chat-token-abcdefgh"
        self._patches = [
            patch.object(cb, "TOKEN_PATH", root / "chat.token"),
            patch.object(cb, "RUNTIME_DIR", root),
            patch.object(cb, "_CHAT_URLS_PRINTED", True),
        ]
        for p in self._patches:
            p.start()
        cb.ChatBridgeHandler.token = self._token
        self.server = cb.ThreadingHTTPServer(("127.0.0.1", 0), cb.ChatBridgeHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        for p in reversed(self._patches):
            p.stop()
        self.tmp.cleanup()

    def _get(self, path: str, *, auth: bool = False) -> tuple[int, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        headers = {}
        if auth:
            headers["Authorization"] = f"Bearer {self._token}"
        conn.request("GET", path, headers=headers)
        response = conn.getresponse()
        body = response.read()
        status = response.status
        conn.close()
        return status, body

    def test_index_without_auth(self) -> None:
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"browser.js", body)
        self.assertIn(b"CUA Chat", body)

    def test_api_still_requires_auth(self) -> None:
        with patch.dict(os.environ, {"CHAT_BROWSER": "0"}, clear=False):
            status, _ = self._get("/v1/chats")
        self.assertEqual(status, 401)
        status, body = self._get("/v1/health")
        self.assertEqual(status, 200)
        self.assertIn(b"cua-chat-bridge", body)

    def test_browser_mode_api_needs_no_token(self) -> None:
        from chat_store import ChatStore

        store = ChatStore(db_path=Path(self.tmp.name) / "chats.sqlite3")
        with (
            patch.dict(os.environ, {"CHAT_BROWSER": "1"}, clear=False),
            patch.object(cb, "get_store", return_value=store),
        ):
            status, body = self._get("/v1/chats")
        self.assertEqual(status, 200)
        self.assertIn(b"chats", body)


class BrowserModeLaunchTests(unittest.TestCase):
    def test_skips_electron(self) -> None:
        with (
            patch.dict(os.environ, {"CHAT_BROWSER": "1"}, clear=False),
            patch("chat_bridge.ensure_chat_bridge") as bridge,
            patch("chat_bridge.print_chat_urls") as urls,
            patch("chat_overlay._electron_bin") as electron,
        ):
            ensure_chat_bridge_and_app()
        bridge.assert_called_once()
        urls.assert_called_once()
        electron.assert_not_called()


class BrowserUrlTests(unittest.TestCase):
    def test_print_chat_urls_omits_token(self) -> None:
        with (
            patch.dict(os.environ, {"CHAT_BROWSER": "1"}, clear=False),
            patch.object(cb, "_CHAT_URLS_PRINTED", False),
            patch("phone_gateway.advertise_urls", return_value=["http://192.168.1.9:8743"]),
            patch("builtins.print") as printed,
        ):
            cb.print_chat_urls()
        text = " ".join(str(c.args[0]) for c in printed.call_args_list)
        self.assertIn("http://192.168.1.9:8743/", text)
        self.assertNotIn("token=", text)


if __name__ == "__main__":
    unittest.main()
