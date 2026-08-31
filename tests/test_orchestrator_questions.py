"""Orchestrator must open the mic for clarifying questions (no GUI)."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import orchestrator  # noqa: E402
from orchestrator import (  # noqa: E402
    TurnTrace,
    _assistant_message_text,
    _confirm_heard,
    _confirm_heard_enabled,
    _give_response_closes_turn,
    _listen_for_answer,
    _looks_like_question,
    _strip_wait_filler,
    _turn_already_spoke,
    _turn_spoke_since,
    _user_turn_input,
)


PLAN_MD_CLARIFIERS = """\
I can do that. Quick questions before I create them:

1) Do you want one issue per top-level item (the five numbered sections), or do you want separate issues for each subtask/bullet inside those sections?
2) Confirm the repo: bchhabra2490/computer-use-agent — correct?
3) Any default labels, assignees, or milestone you want applied to the created issues? If you don’t say, I’ll create them unlabeled and unassigned.

Which option should I use?
"""


class LooksLikeQuestionTests(unittest.TestCase):
    def test_plan_md_clarifiers_are_a_question(self) -> None:
        self.assertTrue(_looks_like_question(PLAN_MD_CLARIFIERS))

    def test_trailing_question_mark(self) -> None:
        self.assertTrue(_looks_like_question("Would you like me to paste the repo name?"))

    def test_statement_is_not_a_question(self) -> None:
        self.assertFalse(
            _looks_like_question("The computer-use-agent repo has twelve stars.")
        )

    def test_empty(self) -> None:
        self.assertFalse(_looks_like_question(""))
        self.assertFalse(_looks_like_question("   "))


class AssistantMessageTextTests(unittest.TestCase):
    def test_joins_output_text(self) -> None:
        response = SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="message",
                    content=[
                        SimpleNamespace(type="output_text", text="Hello."),
                        SimpleNamespace(type="output_text", text=" Next?"),
                    ],
                ),
                SimpleNamespace(type="function_call", name="ask_user"),
            ]
        )
        self.assertEqual(_assistant_message_text(response), "Hello.\nNext?")

    def test_empty_when_tools_only(self) -> None:
        response = SimpleNamespace(
            output=[SimpleNamespace(type="function_call", name="mcp_call")]
        )
        self.assertEqual(_assistant_message_text(response), "")


class RepeatSpeechTests(unittest.TestCase):
    def test_strip_wait_filler(self) -> None:
        text = (
            "I created seven issues in the computer-use-agent repo "
            "from the top-level bullets in plan.md. "
            "I'll wait for any further instructions."
        )
        cleaned = _strip_wait_filler(text)
        self.assertIn("seven issues", cleaned)
        self.assertNotIn("wait", cleaned.lower())

    def test_strip_ready_filler(self) -> None:
        self.assertEqual(
            _strip_wait_filler("Saved. I'm ready for your next task."),
            "Saved.",
        )

    def test_turn_already_spoke(self) -> None:
        turn = TurnTrace("create the issues")
        self.assertFalse(_turn_already_spoke(turn))
        turn.add("spoken", "I created seven issues.")
        self.assertTrue(_turn_already_spoke(turn))

    def test_turn_spoke_since_ignores_earlier_speech(self) -> None:
        turn = TurnTrace("gpu advice")
        turn.add("spoken", "Want me to search listings?")
        start = len(turn.steps)
        turn.add("llm", "follow-up answer in a plain message")
        self.assertFalse(_turn_spoke_since(turn, start))
        turn.add("spoken", "Orin Nano can run Whisper small.")
        self.assertTrue(_turn_spoke_since(turn, start))

    def test_give_response_closes_turn(self) -> None:
        call = SimpleNamespace(name="give_response_to_user")
        self.assertTrue(
            _give_response_closes_turn(
                call, {"output": "Spoke to user. end_session=False"}
            )
        )
        self.assertFalse(
            _give_response_closes_turn(
                call,
                {"output": "Spoke to user, then captured their answer (no wake word): yes."},
            )
        )
        self.assertFalse(
            _give_response_closes_turn(
                call, {"output": "Speech interrupted. User then said: stop."}
            )
        )


class UserTurnInputTests(unittest.TestCase):
    def test_plain_text_without_photo(self) -> None:
        inp = _user_turn_input("open notes", [])
        self.assertIsInstance(inp, str)
        self.assertIn("open notes", inp)
        self.assertIn("Current local date and time:", inp)

    def test_injects_local_datetime_on_every_turn(self) -> None:
        with patch(
            "orchestrator.local_datetime_line",
            return_value="Current local date and time: TEST.",
        ):
            inp = _user_turn_input("what time is it?", [])
        self.assertIn("Current local date and time: TEST.", inp)

    def test_attaches_desktop_screenshot(self) -> None:
        png = b"\x89PNG" + b"\x00" * 20
        inp = _user_turn_input(
            "what is on screen?",
            [],
            desktop_context="Desktop snapshot",
            desktop_screenshot_png=png,
        )
        self.assertIsInstance(inp, list)
        content = inp[0]["content"]
        types = [part["type"] for part in content]
        self.assertIn("input_text", types)
        self.assertIn("input_image", types)
        url = next(p["image_url"] for p in content if p["type"] == "input_image")
        self.assertTrue(url.startswith("data:image/png;base64,"))
        self.assertIn("Desktop snapshot", content[0]["text"])

    def test_attaches_phone_jpeg(self) -> None:
        jpeg = b"\xff\xd8\xff" + b"\x00" * 20
        inp = _user_turn_input("what is this?", [], photo_jpeg=jpeg)
        self.assertIsInstance(inp, list)
        content = inp[0]["content"]
        types = [part["type"] for part in content]
        self.assertIn("input_text", types)
        self.assertIn("input_image", types)
        url = next(p["image_url"] for p in content if p["type"] == "input_image")
        self.assertTrue(url.startswith("data:image/jpeg;base64,"))
        self.assertIn("image attached", content[0]["text"])


class ConfirmHeardTests(unittest.TestCase):
    def test_enabled_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TTS_CONFIRM_HEARD", None)
            self.assertTrue(_confirm_heard_enabled())

    def test_disabled_with_zero(self) -> None:
        with patch.dict(os.environ, {"TTS_CONFIRM_HEARD": "0"}):
            self.assertFalse(_confirm_heard_enabled())

    def test_skip_speak_when_disabled(self) -> None:
        with patch.dict(os.environ, {"TTS_CONFIRM_HEARD": "off"}):
            with patch("orchestrator._speak") as speak:
                out = _confirm_heard(SimpleNamespace(), "open a map of India")
        speak.assert_not_called()
        self.assertEqual(out, "open a map of India")


class ListenForAnswerTests(unittest.TestCase):
    def test_empty_stt_does_not_raise(self) -> None:
        from stt import NoSpeechError

        with (
            patch("orchestrator.get_audio", return_value=None),
            patch(
                "orchestrator.listen_once",
                side_effect=NoSpeechError("Transcription came back empty — try speaking again."),
            ),
        ):
            out = _listen_for_answer(SimpleNamespace())
        self.assertIn("No speech was captured", out)


class ChatTextOnlySpeakTests(unittest.TestCase):
    def test_speak_skips_chat_for_status_blurbs(self) -> None:
        with (
            patch("orchestrator.chat_text_only", return_value=True),
            patch("orchestrator.reply_tts_enabled", return_value=False),
            patch("orchestrator.set_last_spoken") as last,
            patch("orchestrator.get_audio", return_value=None),
            patch("orchestrator.log_llm"),
        ):
            orchestrator._speak(SimpleNamespace(), "Starting that now.")
        last.assert_not_called()

    def test_speak_publishes_user_replies(self) -> None:
        with (
            patch("orchestrator.chat_text_only", return_value=True),
            patch("orchestrator.reply_tts_enabled", return_value=False),
            patch("orchestrator.set_last_spoken") as last,
            patch("orchestrator.get_audio", return_value=None),
            patch("orchestrator.log_llm"),
        ):
            orchestrator._speak(SimpleNamespace(), "The time is noon.", user_reply=True)
        last.assert_called_once_with("The time is noon.", enqueue_chat=True)

    def test_speak_can_exclude_startup_announcement_from_chat(self) -> None:
        with (
            patch("orchestrator.chat_text_only", return_value=False),
            patch("orchestrator.reply_tts_enabled", return_value=False),
            patch("orchestrator.set_last_spoken") as last,
            patch("orchestrator.get_audio", return_value=None),
            patch("orchestrator.log_llm"),
        ):
            orchestrator._speak(
                SimpleNamespace(),
                "Ready. Say the wake word, then tell me what you need.",
                publish_to_chat=False,
            )
        last.assert_called_once_with(
            "Ready. Say the wake word, then tell me what you need.",
            enqueue_chat=False,
        )


if __name__ == "__main__":
    unittest.main()
