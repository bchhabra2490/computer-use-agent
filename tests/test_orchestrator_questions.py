"""Orchestrator must open the mic for clarifying questions (no GUI)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orchestrator import (  # noqa: E402
    TurnTrace,
    _assistant_message_text,
    _give_response_closes_turn,
    _looks_like_question,
    _strip_wait_filler,
    _turn_already_spoke,
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


if __name__ == "__main__":
    unittest.main()
