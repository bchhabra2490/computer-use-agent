"""Smallest Electron orchestrator adapter unit tests (no live API required)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import smallest_orchestrator as sob  # noqa: E402


class ElectronAdapterTests(unittest.TestCase):
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
        converted = sob.responses_tools_to_chat(tools)
        self.assertEqual(len(converted), 1)
        fn = converted[0]["function"]
        self.assertEqual(fn["name"], "give_response_to_user")
        self.assertNotIn("additionalProperties", fn["parameters"])

    def test_text_tool_recovery(self) -> None:
        text = 'give_response_to_user\n{"message": "Hi", "final": true}'
        calls = sob.parse_text_tool_calls(text, {"give_response_to_user"})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].name, "give_response_to_user")
        self.assertIn("Hi", calls[0].arguments)

    def test_function_call_output_keeps_call_id(self) -> None:
        items = sob._normalize_input_items(
            [
                {
                    "type": "function_call_output",
                    "call_id": "call_abc",
                    "output": "done",
                }
            ]
        )
        self.assertEqual(items[0]["role"], "tool")
        self.assertEqual(items[0]["tool_call_id"], "call_abc")
        self.assertEqual(items[0]["content"], "done")

    def test_image_input_becomes_text_note(self) -> None:
        items = sob._normalize_input_items(
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
        self.assertIn("cannot see images", items[0]["content"].lower())

    def test_create_maps_tool_calls(self) -> None:
        session = sob.ElectronSession.__new__(sob.ElectronSession)
        session.model = "electron"
        session._system = ""
        session._messages = []
        session._openai = MagicMock()

        fake_msg = MagicMock()
        fake_msg.content = ""
        fake_tc = MagicMock()
        fake_tc.id = "call_1"
        fake_tc.function.name = "give_response_to_user"
        fake_tc.function.arguments = '{"message": "Hello"}'
        fake_msg.tool_calls = [fake_tc]
        fake_choice = MagicMock()
        fake_choice.message = fake_msg
        fake_resp = MagicMock()
        fake_resp.choices = [fake_choice]
        session._openai.chat.completions.create.return_value = fake_resp

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
        self.assertTrue(resp.id.startswith("electron_"))
        self.assertEqual(len(resp.output), 1)
        call = resp.output[0]
        self.assertEqual(call.type, "function_call")
        self.assertEqual(call.name, "give_response_to_user")
        self.assertIn("Hello", call.arguments)
        self.assertEqual(call.call_id, "call_1")


class SmallestTtsRoutingTests(unittest.TestCase):
    def test_use_smallest_helper(self) -> None:
        import tts as tts_mod

        prev = tts_mod.TTS_PROVIDER
        try:
            tts_mod.TTS_PROVIDER = "smallest"
            self.assertTrue(tts_mod._use_smallest())
            tts_mod.TTS_PROVIDER = "openai"
            self.assertFalse(tts_mod._use_smallest())
        finally:
            tts_mod.TTS_PROVIDER = prev


if __name__ == "__main__":
    unittest.main()
