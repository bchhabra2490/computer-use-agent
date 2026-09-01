from orchestrator import (
    _completed_tasks_in_turn,
    _completed_task_match,
    _normalized_task_goal,
    _start_task_block_reason,
)
from memory import TurnTrace


def test_normalized_goal_drops_polite_wrapper() -> None:
    assert _normalized_task_goal("Can you convert the figures to USD?") == "convert figures to usd"


def test_completed_duplicate_is_detected() -> None:
    history = [
        {
            "task": "Convert the figures to USD",
            "result": "completed\nResult:\nConverted the chart figures.",
        }
    ]
    match = _completed_task_match("Can you convert the figures to USD?", history)
    assert match is history[0]


def test_failed_task_can_be_retried() -> None:
    history = [{"task": "Convert the figures to USD", "result": "failed\nError"}]
    assert _completed_task_match("convert figures to USD", history) is None


def test_distinct_leftover_is_not_blocked() -> None:
    history = [{"task": "Create a USD chart", "result": "completed\nResult:\nSaved."}]
    assert _completed_task_match("Email the chart to Bharat", history) is None


def test_sleep_blocks_new_task() -> None:
    reason = _start_task_block_reason("Open Notes", [], sleeping=True)
    assert reason is not None
    assert "Sleep mode" in reason


def test_awake_duplicate_is_still_blocked() -> None:
    history = [{"task": "Open Notes", "result": "completed\nResult:\nOpened Notes."}]
    reason = _start_task_block_reason("Please open Notes", history, sleeping=False)
    assert reason is not None
    assert "already completed" in reason


def test_only_current_turn_completed_tasks_feed_duplicate_guard() -> None:
    turn = TurnTrace("make the chart")
    turn.add("start_task", "Convert the figures to USD")
    turn.add("start_task_result", "completed\nResult:\nConverted figures.")
    assert _completed_tasks_in_turn(turn) == [
        {
            "task": "Convert the figures to USD",
            "result": "completed\nResult:\nConverted figures.",
        }
    ]


def test_new_turn_has_no_duplicate_history() -> None:
    assert _completed_tasks_in_turn(TurnTrace("open Notes again")) == []
