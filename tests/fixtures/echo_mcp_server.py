"""Minimal stdio MCP server used by tests/test_mcp.py."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("echo")


@mcp.tool()
def echo(text: str) -> str:
    """Return the same text."""
    return text


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@mcp.tool()
def delete_item(item_id: str) -> str:
    """Delete an item by id (write)."""
    return f"deleted {item_id}"


if __name__ == "__main__":
    mcp.run()
