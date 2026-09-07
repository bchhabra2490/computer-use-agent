"""MCP 1.x / 2.x transport shims."""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mcp_compat as compat  # noqa: E402


class FactoryTests(unittest.TestCase):
    def test_prefers_legacy_name(self) -> None:
        import mcp.client.streamable_http as real

        legacy = object()
        with patch.object(real, "streamablehttp_client", legacy, create=True):
            factory, is_legacy = compat.streamable_http_factory()
        self.assertTrue(is_legacy)
        self.assertIs(factory, legacy)

    def test_uses_mcp2_name(self) -> None:
        import mcp.client.streamable_http as real

        modern = object()
        with (
            patch.object(real, "streamablehttp_client", None, create=True),
            patch.object(real, "streamable_http_client", modern, create=True),
        ):
            factory, is_legacy = compat.streamable_http_factory()
        self.assertFalse(is_legacy)
        self.assertIs(factory, modern)


class ListToolsTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_cursor_kwarg(self) -> None:
        session = MagicMock()
        page = types.SimpleNamespace(tools=[], nextCursor="abc")
        session.list_tools = AsyncMock(return_value=page)
        out = await compat.list_tools_page(session, cursor=None)
        self.assertIs(out, page)
        session.list_tools.assert_awaited_once_with(cursor=None)

    async def test_mcp2_params_after_typeerror(self) -> None:
        session = MagicMock()
        page = types.SimpleNamespace(tools=[], next_cursor=None)

        async def list_tools(**kwargs):
            if "cursor" in kwargs:
                raise TypeError("got an unexpected keyword argument 'cursor'")
            if "params" in kwargs:
                self.assertEqual(kwargs["params"].cursor, "n2")
                return page
            raise AssertionError(kwargs)

        session.list_tools = list_tools
        out = await compat.list_tools_page(session, cursor="n2")
        self.assertIs(out, page)

    def test_next_cursor_aliases(self) -> None:
        self.assertEqual(
            compat.tools_next_cursor(types.SimpleNamespace(nextCursor="a")),
            "a",
        )
        self.assertEqual(
            compat.tools_next_cursor(types.SimpleNamespace(next_cursor="b")),
            "b",
        )


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_unpacks_three_tuple(self) -> None:
        read, write, sid = object(), object(), "s1"

        class _Cm:
            async def __aenter__(self):
                return (read, write, sid)

            async def __aexit__(self, *args):
                return False

        with patch.object(compat, "streamable_http_factory", return_value=(lambda *a, **k: _Cm(), True)):
            async with compat.streamable_http_session("https://example.test/mcp") as streams:
                self.assertEqual(streams, (read, write))

    async def test_mcp2_bearer_goes_in_headers(self) -> None:
        read, write = object(), object()
        captured: dict = {}

        class _Http:
            async def __aenter__(self):
                return "client"

            async def __aexit__(self, *args):
                return False

        class _Transport:
            async def __aenter__(self):
                return (read, write)

            async def __aexit__(self, *args):
                return False

        def factory(url, **kwargs):
            captured["url"] = url
            captured["http_client"] = kwargs.get("http_client")
            return _Transport()

        def create_client(*, headers=None, auth=None):
            captured["headers"] = headers
            captured["auth"] = auth
            return _Http()

        auth = types.SimpleNamespace(token="ghp_test")
        with (
            patch.object(compat, "streamable_http_factory", return_value=(factory, False)),
            patch.dict("sys.modules", {"mcp.shared._httpx_utils": types.SimpleNamespace(create_mcp_http_client=create_client)}),
        ):
            async with compat.streamable_http_session(
                "https://api.githubcopilot.com/mcp/",
                auth=auth,
            ) as streams:
                self.assertEqual(streams, (read, write))
        self.assertEqual(captured["headers"]["Authorization"], "Bearer ghp_test")
        self.assertIsNone(captured["auth"])
        self.assertEqual(captured["http_client"], "client")


if __name__ == "__main__":
    unittest.main()
