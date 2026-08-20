"""Ollama orchestrator adapter unit tests (no live Ollama required)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ollama_orchestrator as ob  # noqa: E402


class OllamaAdapterTests(unittest.TestCase):
    def test_tool_schema_conversion(self) -> None:
        tools = [
            {
                "type": "function",
                "name": "give_response_to_user",
                "description": "Speak",
                "parameters": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False,
                },
                "strict": True,
            }
        ]
        converted = ob.responses_tools_to_ollama(tools)
        self.assertEqual(len(converted), 1)
        fn = converted[0]["function"]
        self.assertEqual(fn["name"], "give_response_to_user")
        self.assertNotIn("additionalProperties", fn["parameters"])

    def test_text_tool_recovery(self) -> None:
        text = 'give_response_to_user\n{"message": "Hi", "final": true}'
        calls = ob.parse_text_tool_calls(text, {"give_response_to_user"})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].name, "give_response_to_user")
        self.assertIn("Hi", calls[0].arguments)

    def test_create_recovers_text_tools(self) -> None:
        session = ob.OllamaSession(model="qwen3:8b")
        fake = {
            "message": {
                "role": "assistant",
                "content": 'mcp_call\n{"server": "hardware", "tool": "list_devices", "arguments": {}}',
            }
        }
        with patch.object(session, "_chat", return_value=fake):
            resp = session.create(
                instructions="system",
                input="list devices",
                tools=[
                    {
                        "type": "function",
                        "name": "mcp_call",
                        "description": "MCP",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ],
            )
        self.assertEqual(resp.output[0].type, "function_call")
        self.assertEqual(resp.output[0].name, "mcp_call")

    def test_create_maps_tool_calls(self) -> None:
        session = ob.OllamaSession(model="qwen3:8b")
        fake = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "give_response_to_user",
                            "arguments": {"message": "Hello", "final": True},
                        },
                    }
                ],
            }
        }
        with patch.object(session, "_chat", return_value=fake):
            resp = session.create(
                instructions="system",
                input="hi",
                tools=[
                    {
                        "type": "function",
                        "name": "give_response_to_user",
                        "description": "Speak",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ],
            )
        self.assertTrue(resp.id.startswith("ollama_"))
        self.assertEqual(len(resp.output), 1)
        call = resp.output[0]
        self.assertEqual(call.type, "function_call")
        self.assertEqual(call.name, "give_response_to_user")
        self.assertIn("Hello", call.arguments)
        self.assertEqual(call.call_id, "call_1")

    def test_image_input_becomes_text_note(self) -> None:
        items = ob._normalize_input_items(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "What is this?"},
                        {
                            "type": "input_image",
                            "image_url": "data:image/jpeg;base64,xxx",
                        },
                    ],
                }
            ]
        )
        self.assertEqual(len(items), 1)
        self.assertIn("cannot see images", items[0]["content"])


if __name__ == "__main__":
    unittest.main()
