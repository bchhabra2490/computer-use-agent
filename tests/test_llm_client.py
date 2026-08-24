"""Tests for llm_client provider selection and vision model routing."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import llm_client as lc  # noqa: E402


class LlmClientTests(unittest.TestCase):
    def test_provider_from_model_name(self) -> None:
        self.assertEqual(lc.provider_for_model("deepseek-v4-pro"), "deepseek")
        self.assertEqual(lc.provider_for_model("gpt-5-mini"), "openai")
        self.assertEqual(
            lc.provider_for_model("gpt-5-mini", explicit="deepseek"),
            "deepseek",
        )

    def test_vision_model_for_deepseek(self) -> None:
        with patch.dict(
            os.environ,
            {"DEEPSEEK_VISION_MODEL": "deepseek-v4-flash-vision-exp"},
            clear=False,
        ):
            self.assertEqual(
                lc.model_for_request("deepseek-v4-pro", has_image=True),
                "deepseek-v4-flash-vision-exp",
            )
            self.assertEqual(
                lc.model_for_request("deepseek-v4-pro", has_image=False),
                "deepseek-v4-pro",
            )

    def test_input_has_image(self) -> None:
        self.assertTrue(
            lc.input_has_image(
                [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "hi"},
                            {
                                "type": "input_image",
                                "image_url": "data:image/png;base64,xx",
                            },
                        ],
                    }
                ]
            )
        )
        self.assertFalse(lc.input_has_image("just text"))

    def test_make_llm_client_deepseek_requires_key(self) -> None:
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}, clear=False):
            with self.assertRaises(RuntimeError):
                lc.make_llm_client(model="deepseek-v4-pro")

    def test_deepseek_is_stateless(self) -> None:
        self.assertFalse(lc.supports_previous_response_id("deepseek-v4-pro"))
        self.assertTrue(lc.supports_previous_response_id("gpt-5-mini"))

    def test_merge_tool_followup_puts_calls_before_outputs(self) -> None:
        from types import SimpleNamespace

        response = SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="function_call",
                    call_id="call_1",
                    name="who_am_i",
                    arguments="{}",
                )
            ]
        )
        outputs = [
            {"type": "function_call_output", "call_id": "call_1", "output": "README"}
        ]
        merged = lc.merge_tool_followup_input(response, outputs)
        self.assertEqual(merged[0]["type"], "function_call")
        self.assertEqual(merged[0]["call_id"], "call_1")
        self.assertEqual(merged[1]["type"], "function_call_output")

    def test_merge_aligns_empty_call_id_from_output(self) -> None:
        from types import SimpleNamespace

        response = SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="function_call",
                    call_id="",
                    name="who_am_i",
                    arguments="{}",
                )
            ]
        )
        outputs = [
            {
                "type": "function_call_output",
                "call_id": "call_00_abc",
                "output": "README",
            }
        ]
        merged = lc.merge_tool_followup_input(response, outputs)
        self.assertEqual(merged[0]["call_id"], "call_00_abc")
        self.assertEqual(merged[1]["call_id"], "call_00_abc")

    def test_fold_orphan_tool_outputs_into_user_text(self) -> None:
        payload = [
            {
                "type": "function_call_output",
                "call_id": "call_orphan",
                "output": "who_am_i result text",
            },
            {"role": "user", "content": "Who am I?"},
        ]
        folded = lc.fold_orphan_tool_outputs(payload)
        self.assertEqual(len(folded), 1)
        self.assertEqual(folded[0]["role"], "user")
        self.assertIn("who_am_i result text", folded[0]["content"])
        self.assertIn("Who am I?", folded[0]["content"])
        self.assertNotIn("function_call_output", str(folded))


if __name__ == "__main__":
    unittest.main()
