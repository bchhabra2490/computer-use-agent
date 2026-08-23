"""Tests for difficulty → model / max-steps routing."""

from __future__ import annotations

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
