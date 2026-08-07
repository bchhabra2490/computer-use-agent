"""
Cost-aware routing and periodic coaching for the computer-use agent.

- Router: cheap text model picks easy/medium/hard → Luna / Terra / Sol.
- Evaluator: every N computer turns, cheap vision model coaches the agent
  (and may nudge wrap-up when likely done / stuck).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI

from task_log import TaskLog

ROUTER_MODEL = os.environ.get("ROUTER_MODEL", "gpt-5-mini")
EVAL_MODEL = os.environ.get("EVAL_MODEL", "gpt-5-mini")
# 0 disables the N-step coach.
EVAL_EVERY = int(os.environ.get("EVAL_EVERY", "5"))
# Set AGENT_ROUTE=0 to skip difficulty routing.
AGENT_ROUTE = os.environ.get("AGENT_ROUTE", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}

MODEL_EASY = os.environ.get("AGENT_MODEL_EASY", "gpt-5.6-luna")
MODEL_MEDIUM = os.environ.get("AGENT_MODEL_MEDIUM", "gpt-5.6-terra")
MODEL_HARD = os.environ.get("AGENT_MODEL_HARD", "gpt-5.6")

DIFFICULTY_MODELS = {
    "easy": MODEL_EASY,
    "medium": MODEL_MEDIUM,
    "hard": MODEL_HARD,
}


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


def resolve_agent_model(client: OpenAI, task: str, log: TaskLog | None = None) -> str:
    """
    Choose the computer-agent model.

    If AGENT_MODEL is set, use it (manual override).
    Else if AGENT_ROUTE is on, classify difficulty with ROUTER_MODEL.
    Else fall back to AGENT_MODEL_HARD.
    """
    override = (os.environ.get("AGENT_MODEL") or "").strip()
    if override:
        print(f"[router] AGENT_MODEL override → {override}")
        if log is not None:
            log.record("router", f"override {override}", {"model": override})
        return override

    if not AGENT_ROUTE:
        print(f"[router] routing disabled → {MODEL_HARD}")
        if log is not None:
            log.record("router", f"disabled {MODEL_HARD}", {"model": MODEL_HARD})
        return MODEL_HARD

    prompt = f"""Classify this desktop computer-use task difficulty.

easy — few clicks, open one app, type short text, simple one-screen UI
medium — multi-step UI in one or two apps, forms, browsing, light CAD/schematic edits
hard — dense professional UIs (EasyEDA/KiCad/etc.), long multi-phase design, careful placement/routing

Task:
{task}

Reply JSON only:
{{"difficulty":"easy"|"medium"|"hard","reason":"one short sentence"}}
"""
    try:
        response = client.responses.create(
            model=ROUTER_MODEL,
            input=prompt,
        )
        raw = _response_text(response)
        data = _extract_json(raw) or {}
        difficulty = str(data.get("difficulty") or "medium").strip().lower()
        if difficulty not in DIFFICULTY_MODELS:
            difficulty = "medium"
        model = DIFFICULTY_MODELS[difficulty]
        reason = str(data.get("reason") or "").strip()
        print(f"[router] {difficulty} → {model}" + (f" ({reason})" if reason else ""))
        if log is not None:
            log.record(
                "router",
                f"{difficulty} → {model}",
                {"difficulty": difficulty, "model": model, "reason": reason},
            )
        return model
    except Exception as e:
        print(f"[router] failed ({e}) — using {MODEL_HARD}", flush=True)
        if log is not None:
            log.record("router", f"error → {MODEL_HARD}", {"error": str(e)})
        return MODEL_HARD


def coach_agent(
    client: OpenAI,
    *,
    task: str,
    log: TaskLog,
    screenshot_b64: str | None,
    step_n: int,
) -> str | None:
    """
    Periodic coach. Returns a user-message string to inject, or None.
    Uses EVAL_MODEL (cheap). Screenshot optional but strongly preferred.
    """
    if EVAL_EVERY <= 0:
        return None

    recent = log.steps_for_prompt(max_chars=6_000)
    instructions = (
        "You are a concise coach for a desktop computer-use agent. "
        "Given the goal, recent steps, and current screenshot, guide the next actions. "
        "Do not invent UI that is not visible. Prefer concrete, short guidance. "
        "If the goal appears satisfied, say so. If the agent is looping or lost, say so."
    )
    content: list[dict[str, Any]] = [
        {
            "type": "input_text",
            "text": (
                f"Goal:\n{task}\n\n"
                f"Computer turns so far: {step_n}\n\n"
                f"Recent steps:\n{recent}\n\n"
                "Reply JSON only:\n"
                "{\n"
                '  "status": "on_track" | "drifting" | "stuck" | "likely_done",\n'
                '  "guidance": ["short bullet", "..."],\n'
                '  "next_focus": "one sentence priority"\n'
                "}"
            ),
        }
    ]
    if screenshot_b64:
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{screenshot_b64}",
                "detail": "high",
            }
        )

    try:
        response = client.responses.create(
            model=EVAL_MODEL,
            instructions=instructions,
            input=[{"role": "user", "content": content}],
        )
        raw = _response_text(response)
        data = _extract_json(raw) or {}
    except Exception as e:
        print(f"[eval] coach failed: {e}", flush=True)
        if log is not None:
            log.record("evaluator", f"error: {e}", {"error": str(e)})
        return None

    status = str(data.get("status") or "on_track").strip().lower()
    if status not in {"on_track", "drifting", "stuck", "likely_done"}:
        status = "on_track"
    guidance = data.get("guidance") or []
    if isinstance(guidance, str):
        guidance = [guidance]
    guidance = [str(g).strip() for g in guidance if str(g).strip()][:6]
    next_focus = str(data.get("next_focus") or "").strip()

    print(f"[eval] step {step_n}: {status}" + (f" — {next_focus}" if next_focus else ""))
    log.record(
        "evaluator",
        f"{status}: {next_focus or (guidance[0] if guidance else '')}",
        {"status": status, "guidance": guidance, "next_focus": next_focus, "step": step_n},
    )

    lines = [
        "Evaluator coaching (advisory — adapt to what you see; do not ignore the screen):",
        f"status: {status}",
    ]
    if next_focus:
        lines.append(f"next focus: {next_focus}")
    for g in guidance:
        lines.append(f"- {g}")
    if status == "likely_done":
        lines.append(
            "If the goal is satisfied on screen, finish now (no more exploratory clicks). "
            "If not, state what remains and do only that."
        )
    elif status == "stuck":
        lines.append(
            "You appear stuck. Change approach, use a skill if relevant, or call ask_user "
            "if a human decision is required. Do not repeat the same failing action."
        )

    return "\n".join(lines)


def screenshot_b64_from_computer_output(output: dict) -> str | None:
    """Extract raw base64 PNG from a computer_call_output dict."""
    try:
        payload = output.get("output") or {}
        url = payload.get("image_url") or ""
        if isinstance(url, str) and "base64," in url:
            return url.split("base64,", 1)[1]
    except Exception:
        return None
    return None
