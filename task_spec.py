"""Planner vs actor: start_task is a goal, not a UI screenplay.

The orchestrator chooses *whether* to drive the desktop. Recipes and
the computer-use agent decide *how*. If the planner writes Chrome/Spotlight
steps, drop them and keep the user's words.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PROCEDURE = re.compile(
    r"create a new tab|navigate to https?://|wait for the page to finish loading|"
    r"open google chrome,|ensure the map is centered|"
    r"youtube is not playable|if that fails|apple music|"
    r"\b(cmd\s*\+|command\s*\+|spotlight|press enter)\b|"
    r"bring google chrome|type in the address bar",
    re.I,
)
_NUMBERED_STEP = re.compile(r"(?m)^\s*\d+[\.)]\s")
_MAX_GOAL_CHARS = 280


def is_procedure_brief(text: str) -> bool:
    """True when the text is a how-to screenplay instead of a user goal."""
    body = (text or "").strip()
    if not body:
        return False
    if _PROCEDURE.search(body):
        return True
    if _NUMBERED_STEP.search(body):
        return True
    if len(body) > _MAX_GOAL_CHARS:
        return True
    return False


@dataclass(frozen=True)
class AgentTaskSpec:
    """What the actor should match on vs what it should optimize for."""

    match_text: str
    goal: str


def resolve_agent_task(*, user_said: str, planner_task: str) -> AgentTaskSpec:
    """
    Recipes match ``match_text`` (the spoken request).

    The computer-use prompt uses ``goal``: the planner's task only when it is a
    short restatement (anaphora, leftover step). Procedure briefs are discarded.
    """
    said = (user_said or "").strip()
    planned = (planner_task or "").strip()
    match_text = said or planned
    if planned and not is_procedure_brief(planned):
        goal = planned
    else:
        goal = said or planned
    return AgentTaskSpec(match_text=match_text, goal=goal)
