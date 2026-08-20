"""http_get: public HTTPS only."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import http_get as hg  # noqa: E402
import tools_registry as tr  # noqa: E402


class HttpGetTests(unittest.TestCase):
    def test_rejects_http(self) -> None:
        self.assertIn("https", hg.fetch_https("http://example.com/"))

    def test_rejects_localhost(self) -> None:
        self.assertIn("not allowed", hg.fetch_https("https://localhost/secret"))

    def test_rejects_loopback_ip(self) -> None:
        self.assertIn("not allowed", hg.fetch_https("https://127.0.0.1/"))

    def test_fetches_text(self) -> None:
        payload = b"Mohali: +32C"
        cm = MagicMock()
        cm.read.return_value = payload
        cm.headers = {"Content-Type": "text/plain"}
        cm.__enter__.return_value = cm
        cm.__exit__.return_value = False
        with (
            patch.object(hg, "_host_allowed", return_value=True),
            patch("http_get.urlopen", return_value=cm),
        ):
            out = hg.fetch_https("https://wttr.in/Mohali?format=3")
        self.assertIn("Mohali", out)

    def test_empty_url(self) -> None:
        self.assertIn("url is required", hg.run_http_get({}))

    def test_shared_dispatch(self) -> None:
        with patch("http_get.fetch_https", return_value="ok"):
            self.assertEqual(tr.run_shared_tool("http_get", {"url": "https://example.com/"}), "ok")
