"""Classify Hey Jarvis lines while a computer-use job owns the desktop."""

from __future__ import annotations

import os
import re
from typing import Literal

from openai import OpenAI

from evaluator import ROUTER_MODEL, _extract_json, _response_text

Route = Literal["cu_update", "sidekick", "cu_new"]

ROUTES: frozenset[str] = frozenset({"cu_update", "sidekick", "cu_new"})

MIDTASK_ROUTE = os.environ.get("MIDTASK_ROUTE", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}

_STOP = frozenset(
    """
    a an the to of and or for on in it is be my me please just that this
    with from at do can you we i i'll im i'm the current now then also
    """.split()
)

_SIDEKICK_RE = re.compile(
    r"\b("
    r"timer|remind(?:er| me)?|who are you|who am i|what time|"
    r"weather|remember (?:that|this)|what(?:'s| is)|how much is|"
    r"times \d|\d+ times|plus \d|minus \d"
    r")\b",
    re.I,
)
_STATUS_RE = re.compile(
    r"\b(is it done|are you done|how's it going|how is it going|"
    r"status|progress|eta|still (?:working|running|writing)|click|"
    r"press|type|cancel|continue|write|confirm)\b",
    re.I,
)
_NEW_UI_RE = re.compile(
    r"\b(open|play|send|call|search|email|message|text|whatsapp|"
    r"youtube|chrome|slack|maps?|instagram)\b",
    re.I,
)


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOP}


def heuristic_route(cu_goal: str, utterance: str) -> Route:
    """Cheap fallback when the router LLM is off or fails.

    Default is ``cu_update`` so on-screen instructions are not dropped.
    """
    said = (utterance or "").strip()
    goal = (cu_goal or "").strip()
    if not said:
        return "cu_update"
    overlap = _tokens(goal) & _tokens(said)
    if _STATUS_RE.search(said) or len(overlap) >= 1:
        return "cu_update"
    if _SIDEKICK_RE.search(said):
        return "sidekick"
    if _NEW_UI_RE.search(said) and not overlap:
        return "cu_new"
    return "cu_update"


def classify_midtask(
    cu_goal: str,
    utterance: str,
    *,
    client: OpenAI | None = None,
) -> Route:
    """Return how a mid-task utterance should be handled."""
    fallback = heuristic_route(cu_goal, utterance)
    if client is None:
        return fallback
    prompt = f"""A computer-use agent is already controlling this Mac.

Current goal:
{cu_goal}

User just said (wake word already stripped):
{utterance}

Pick one route:
- cu_update — about THIS job: clicks, typing, cancel/confirm that UI, status of this work, details on that screen.
- sidekick — answer without the mouse: facts, math, timers, memory, who you are, MCP/search, photos. The CU agent must not see this.
- cu_new — a NEW desktop UI task unrelated to the current goal (open another app, send a WhatsApp, play a video).

If unsure and it might be about the current on-screen work, choose cu_update.
Reply JSON only:
{{"route":"cu_update"|"sidekick"|"cu_new","reason":"one short sentence"}}
"""
    try:
        response = client.responses.create(model=ROUTER_MODEL, input=prompt)
        raw = _response_text(response)
        data = _extract_json(raw) or {}
        route = str(data.get("route") or "").strip().lower()
        if route not in ROUTES:
            route = fallback
        reason = str(data.get("reason") or "").strip()
        print(
            f"[midtask] {route}" + (f" ({reason})" if reason else ""),
            flush=True,
        )
        return route  # type: ignore[return-value]
    except Exception as e:
        print(f"[midtask] classify failed ({e}) — {fallback}", flush=True)
        return fallback
