"""Classify TTS barge-in: new computer task vs answer/clarification."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

CLASSIFY_MODEL = os.environ.get("BARGE_CLASSIFY_MODEL", os.environ.get("ORCHESTRATOR_MODEL", "gpt-5-mini"))
BARGE_CLASSIFY = os.environ.get("BARGE_CLASSIFY", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}


@dataclass(frozen=True)
class BargeDecision:
    """Result of LLM barge-in routing."""

    kind: str  # new_task | answer | steer | other
    task_goal: str
    reason: str

    @property
    def is_new_task(self) -> bool:
        return self.kind == "new_task" and bool(self.task_goal.strip())


def _extract_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _response_text(response) -> str:
    chunks: list[str] = []
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) != "message":
            continue
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", None) == "output_text":
                chunks.append(part.text)
    if chunks:
        return "\n".join(chunks).strip()
    return (getattr(response, "output_text", None) or "").strip()


def classify_barge_utterance(
    client: OpenAI,
    utterance: str,
    *,
    spoken_context: str = "",
    user_turn: str = "",
    task_context: str = "",
) -> BargeDecision:
    """
    Ask a cheap model whether a barge-in replaces the current work with a new task.

    ``new_task`` — user wants fresh computer work (open/find/click/research on Mac).
    ``answer`` — user is answering a question Jarvis just asked.
    ``steer`` — minor correction to work already in progress.
    ``other`` — meta, chitchat, or not actionable on the Mac.
    """
    text = (utterance or "").strip()
    if not text:
        return BargeDecision("other", "", "empty utterance")

    if not BARGE_CLASSIFY:
        return BargeDecision("other", "", "BARGE_CLASSIFY disabled")

    prompt = (
        "The user interrupted Jarvis while it was speaking (barge-in).\n\n"
        f"What Jarvis was saying (may be partial):\n{(spoken_context or '(unknown)')[:800]}\n\n"
        f"Original user request this turn:\n{(user_turn or '(unknown)')[:400]}\n\n"
        f"Recent computer tasks this session:\n{(task_context or '(none)')[:600]}\n\n"
        f"User barge-in:\n{text}\n\n"
        "Decide ONE kind:\n"
        "- new_task: user is redirecting to DIFFERENT computer work — opening apps, "
        "finding/opening files or pages, clicking, typing, research on the Mac. "
        "NOT a short yes/no answer to a question.\n"
        "- answer: user is answering a question Jarvis asked (yes/no/choice/clarification).\n"
        "- steer: small fix to the SAME work already running (e.g. 'use the other tab').\n"
        "- other: thanks, stop, repeat, or not actionable on the Mac.\n\n"
        "If new_task, set task_goal to ONE short goal sentence (what to do on the Mac). "
        "Do NOT repeat an already-finished research task unless the user explicitly asks to redo it.\n"
        'Reply JSON only: {"kind":"...", "task_goal":"..." or "", "reason":"..."}'
    )
    try:
        response = client.responses.create(
            model=CLASSIFY_MODEL,
            input=prompt,
            max_output_tokens=220,
        )
        raw = _response_text(response)
        data = _extract_json(raw) or {}
    except Exception as e:
        print(f"[barge] classify failed ({e})", flush=True)
        return BargeDecision("other", "", f"classify error: {e}")

    kind = str(data.get("kind") or "other").strip().lower()
    if kind not in {"new_task", "answer", "steer", "other"}:
        kind = "other"
    goal = str(data.get("task_goal") or "").strip()
    reason = str(data.get("reason") or "").strip()
    print(f"[barge] classify → {kind}" + (f" goal={goal!r}" if goal else "") + f" ({reason})", flush=True)
    return BargeDecision(kind, goal, reason)
