"""DeepSeek computer-use adapter unit tests (no live APIs)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import agent_deepseek as ad  # noqa: E402


class DeepseekAgentTests(unittest.TestCase):
    def test_computer_tool_in_chat_schema(self) -> None:
        tools = ad.responses_tools_to_chat(
            [
                {"type": "computer"},
                {
                    "type": "function",
                    "name": "mark_done",
                    "description": "Done",
                    "parameters": {"type": "object", "properties": {}},
                },
            ]
        )
        names = [(t.get("function") or {}).get("name") for t in tools]
        self.assertIn("computer", names)
        self.assertIn("mark_done", names)

    def test_normalize_actions(self) -> None:
        actions = ad._normalize_actions(
            [
                {"type": "click", "x": 10, "y": 20},
                {"type": "type", "text": "hi"},
                {"nope": True},
            ]
        )
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0]["type"], "click")
        self.assertEqual(actions[1]["text"], "hi")

    def test_describe_screenshot_uses_vision_model(self) -> None:
        client = MagicMock()
        response = MagicMock()
        response.output = [
            MagicMock(
                type="message",
                content=[MagicMock(type="output_text", text="Chrome is open at (100,200)")],
            )
        ]
        client.responses.create.return_value = response
        text = ad.describe_screenshot(
            client,
            "aaa",
            width=800,
            height=600,
            task="open chrome",
        )
        self.assertIn("Chrome", text)
        kwargs = client.responses.create.call_args.kwargs
        self.assertEqual(kwargs["model"], ad.CU_VISION_MODEL)
        content = kwargs["input"][0]["content"]
        self.assertEqual(content[1]["type"], "input_image")


if __name__ == "__main__":
    unittest.main()
