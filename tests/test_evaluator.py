"""Tests for difficulty → model / max-steps routing."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import evaluator as ev


def test_max_steps_for_difficulty_defaults():
    assert ev.max_steps_for_difficulty("easy") == 25
    assert ev.max_steps_for_difficulty("medium") == 100
    assert ev.max_steps_for_difficulty("hard") == 200
    assert ev.max_steps_for_difficulty("unknown") == 100


def test_recipe_handoff_is_easy_budget():
    route = ev.model_for_recipe_handoff()
    assert route.difficulty == "easy"
    assert route.max_steps == 25
    assert route.model == ev.MODEL_EASY


def test_resolve_agent_model_uses_classified_steps(monkeypatch):
    monkeypatch.setattr(ev, "AGENT_ROUTE", True)
    monkeypatch.delenv("AGENT_MODEL", raising=False)

    client = MagicMock()
    response = MagicMock()
    response.output = []
    response.output_text = '{"difficulty":"medium","reason":"multi-step form"}'
    client.responses.create.return_value = response

    with patch.object(ev, "_response_text", return_value=response.output_text):
        route = ev.resolve_agent_model(client, "apply to this job")

    assert route.difficulty == "medium"
    assert route.max_steps == 100
    assert route.model == ev.MODEL_MEDIUM


def test_resolve_agent_model_hard(monkeypatch):
    monkeypatch.setattr(ev, "AGENT_ROUTE", True)
    monkeypatch.delenv("AGENT_MODEL", raising=False)
    client = MagicMock()
    with patch.object(
        ev,
        "_response_text",
        return_value='{"difficulty":"hard","reason":"EasyEDA layout"}',
    ):
        client.responses.create.return_value = MagicMock()
        route = ev.resolve_agent_model(client, "route this PCB")
    assert route.difficulty == "hard"
    assert route.max_steps == 200
    assert route.model == ev.MODEL_HARD


def test_fast_path_skips_llm_router(monkeypatch):
    monkeypatch.delenv("AGENT_MODEL", raising=False)
    client = MagicMock()
    route = ev.resolve_agent_model(
        client,
        "open the site",
        execution_path="fast",
        specialist_lane="browser",
    )
    assert route.difficulty == "easy"
    assert route.model == ev.MODEL_EASY
    assert route.max_steps == ev.DIFFICULTY_MAX_STEPS["easy"]
    client.responses.create.assert_not_called()


def test_progress_checkpoint_tracks_work_after_previous_evaluation(tmp_path):
    log = MagicMock()
    log.steps_path = tmp_path / "steps.jsonl"
    entries = [
        {
            "n": 1,
            "kind": "evaluator",
            "summary": "on_track: Click Search",
            "data": {"guidance": ["Click Search"]},
        },
        {
            "n": 2,
            "kind": "computer_actions",
            "summary": "2 action(s)",
            "data": {"actions": [{"type": "click", "x": 20, "y": 30}, {"type": "type", "text": "cats"}]},
        },
        {"n": 3, "kind": "screenshot", "summary": "100 bytes", "data": {"bytes": 100}},
    ]
    log.steps_path.write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n",
        encoding="utf-8",
    )

    checkpoint = ev._progress_since_last_evaluation(log)

    assert "Click Search" in checkpoint
    assert "computer_actions" in checkpoint
    assert '"text": "cats"' in checkpoint
    assert "[screenshot]" not in checkpoint


def test_coach_prompt_forbids_recommending_completed_actions(tmp_path):
    log = MagicMock()
    log.steps_path = tmp_path / "steps.jsonl"
    log.steps_path.write_text(
        json.dumps(
            {
                "n": 1,
                "kind": "desktop_actions",
                "summary": "1 action(s)",
                "data": {"actions": [{"type": "type", "text": "hello"}]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    log.steps_for_prompt.return_value = "1. [desktop_actions] 1 action(s)"
    client = MagicMock()
    client.responses.create.return_value = MagicMock(
        output=[],
        output_text=(
            '{"status":"on_track","completed_since_last_review":["entered hello"],'
            '"guidance":["Submit the form"],"next_focus":"Submit"}'
        ),
    )

    with patch.object(ev, "_response_text", return_value=client.responses.create.return_value.output_text):
        tip = ev.coach_agent(
            client,
            task="Enter hello and submit",
            log=log,
            screenshot_b64=None,
            step_n=5,
        )

    request = client.responses.create.call_args.kwargs
    assert "Never recommend an already successful" in request["instructions"]
    prompt = request["input"][0]["content"][0]["text"]
    assert "Progress checkpoint:" in prompt
    assert '"text": "hello"' in prompt
    assert "Submit the form" in tip
    recorded = log.record.call_args.args[2]
    assert recorded["completed_since_last_review"] == ["entered hello"]
