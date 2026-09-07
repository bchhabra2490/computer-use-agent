"""MCP SDK 1.x / 2.x shims.

mcp 1.x: ``streamablehttp_client(url, headers=, auth=)`` yields
``(read, write, session_id)`` and ``ClientSession.list_tools(cursor=)``.

mcp 2.x: ``streamable_http_client(url, http_client=)`` yields
``(read, write)``; pagination is ``list_tools(params=PaginatedRequestParams)``.
Phoenix/pydantic-ai may pull 2.x even when this repo pins 1.x.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any


def streamable_http_factory() -> tuple[Any, bool]:
    """Return ``(factory, is_legacy)`` for the installed MCP HTTP transport."""
    import mcp.client.streamable_http as mod

    legacy = getattr(mod, "streamablehttp_client", None)
    if legacy is not None:
        return legacy, True
    modern = getattr(mod, "streamable_http_client", None)
    if modern is None:
        raise ImportError(
            "mcp.client.streamable_http has neither streamablehttp_client "
            "nor streamable_http_client"
        )
    return modern, False


def _bearer_token(auth: Any) -> str | None:
    token = getattr(auth, "token", None) or getattr(auth, "_token", None)
    if isinstance(token, str) and token.strip():
        return token.strip()
    return None


@asynccontextmanager
async def streamable_http_session(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    auth: Any = None,
):
    """Yield ``(read, write)`` against a Streamable HTTP MCP server."""
    factory, is_legacy = streamable_http_factory()
    hdrs = dict(headers or {})
    if is_legacy:
        async with factory(url, headers=hdrs or None, auth=auth) as streams:
            yield streams[0], streams[1]
        return

    from mcp.shared._httpx_utils import create_mcp_http_client

    http_auth = auth
    token = _bearer_token(auth)
    if token and not any(k.lower() == "authorization" for k in hdrs):
        hdrs["Authorization"] = f"Bearer {token}"
        http_auth = None
    async with create_mcp_http_client(headers=hdrs or None, auth=http_auth) as client:
        async with factory(url, http_client=client) as streams:
            yield streams[0], streams[1]


async def list_tools_page(session: Any, cursor: str | None = None) -> Any:
    """One ``tools/list`` page on MCP 1.x or 2.x."""
    try:
        return await session.list_tools(cursor=cursor)
    except TypeError:
        if not cursor:
            return await session.list_tools()
        params = _paginated_params(cursor)
        return await session.list_tools(params=params)


def _paginated_params(cursor: str) -> Any:
    try:
        from mcp_types import PaginatedRequestParams
    except ImportError:
        from mcp.types import PaginatedRequestParams  # type: ignore[attr-defined]
    return PaginatedRequestParams(cursor=cursor)


def tools_next_cursor(page: Any) -> str | None:
    return getattr(page, "nextCursor", None) or getattr(page, "next_cursor", None)
