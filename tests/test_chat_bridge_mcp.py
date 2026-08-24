"""Chat bridge MCP config helpers (no network)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import chat_bridge as cb  # noqa: E402


class McpConfigHelpersTests(unittest.TestCase):
    def test_list_add_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mcp.json"
            path.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "github": {
                                "url": "https://example.com/mcp",
                                "headers": {"Authorization": "Bearer SECRET"},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(cb, "_mcp_config_path", return_value=path):
                rows = cb.list_mcp_connections()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["name"], "github")
                self.assertEqual(rows[0]["headers"]["Authorization"], "***")

                added = cb.upsert_mcp_connection(
                    {
                        "name": "Linear App",
                        "kind": "http",
                        "url": "https://mcp.linear.app/mcp",
                        "auth": "oauth",
                    }
                )
                self.assertEqual(added["name"], "linear-app")
                names = {r["name"] for r in cb.list_mcp_connections()}
                self.assertEqual(names, {"github", "linear-app"})

                cb.upsert_mcp_connection(
                    {
                        "name": "hardware",
                        "kind": "stdio",
                        "command": "/usr/bin/python",
                        "args": "server.py\n--port\n9",
                    }
                )
                hw = next(r for r in cb.list_mcp_connections() if r["name"] == "hardware")
                self.assertEqual(hw["command"], "/usr/bin/python")
                self.assertEqual(hw["args"], ["server.py", "--port", "9"])

                cb.delete_mcp_connection("github")
                self.assertEqual(
                    {r["name"] for r in cb.list_mcp_connections()},
                    {"linear-app", "hardware"},
                )


if __name__ == "__main__":
    unittest.main()
