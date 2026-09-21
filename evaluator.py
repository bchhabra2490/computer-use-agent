"""
Cost-aware routing and periodic coaching for the computer-use agent.

- Router: the deterministic execution route picks easy/medium/hard → Luna / Terra / Sol
  and a matching max-steps budget (25 / 100 / 200). No extra LLM round trip.
- Evaluator: every N computer turns, cheap vision model coaches the agent
  (and may nudge wrap-up when likely done / stuck).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from llm_client import make_llm_client, model_for_request, parse_json_dict, response_output_text
from task_log import TaskLog


def _client_for_model(client: OpenAI, model: str) -> OpenAI:
    """Use a provider matching ``model``; keep mocks/fakes for tests."""
    if type(client).__name__ != "OpenAI":
        return client
    return make_llm_client(model=model)

EVAL_MODEL = os.environ.get("EVAL_MODEL", "gpt-5-mini")
# 0 disables the N-step coach.
EVAL_EVERY = int(os.environ.get("EVAL_EVERY", "5"))
# Set AGENT_ROUTE=0 to skip difficulty routing and always use AGENT_MODEL_HARD.
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

DIFFICULTY_MAX_STEPS = {
    "easy": int(os.environ.get("AGENT_STEPS_EASY", "25")),
    "medium": int(os.environ.get("AGENT_STEPS_MEDIUM", "100")),
    "hard": int(os.environ.get("AGENT_STEPS_HARD", "200")),
}


@dataclass(frozen=True)
class AgentRoute:
    model: str
    difficulty: str
    max_steps: int


def max_steps_for_difficulty(difficulty: str) -> int:
    key = (difficulty or "medium").strip().lower()
    if key not in DIFFICULTY_MAX_STEPS:
        key = "medium"
    return DIFFICULTY_MAX_STEPS[key]


def _response_text(response) -> str:
    return response_output_text(response)


def _extract_json(text: str) -> dict[str, Any] | None:
    return parse_json_dict(text)


def _route(model: str, difficulty: str) -> AgentRoute:
    return AgentRoute(
        model=model,
        difficulty=difficulty,
        max_steps=max_steps_for_difficulty(difficulty),
    )


def _progress_since_last_evaluation(log: TaskLog, *, max_chars: int = 4_000) -> str:
    """Return authoritative work performed since the previous coach response."""
    try:
        entries = [
            json.loads(line)
            for line in log.steps_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError, AttributeError):
        return "(progress log unavailable)"

    last_eval = -1
    previous_guidance = "(none)"
    for index, entry in enumerate(entries):
        if entry.get("kind") == "evaluator":
            last_eval = index
            previous_guidance = json.dumps(entry.get("data") or {}, ensure_ascii=False)

    lines = [f"Previous evaluator guidance: {previous_guidance}"]
    recent = entries[last_eval + 1 :]
    if not recent:
        lines.append("Actions and results since that guidance: (none)")
    else:
        lines.append("Actions and results since that guidance (authoritative, chronological):")
        for entry in recent:
            kind = str(entry.get("kind") or "unknown")
            if kind in {"screenshot", "router"}:
                continue
            summary = str(entry.get("summary") or "")
            data = entry.get("data")
            detail = json.dumps(data, ensure_ascii=False) if data else ""
            if len(detail) > 1_200:
                detail = detail[:1_200] + "…"
            lines.append(
                f"- step {entry.get('n', '?')} [{kind}] {summary}"
                + (f" | {detail}" if detail else "")
            )

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[-max_chars:]
        text = "(older progress omitted)\n" + text
    return text


def model_for_recipe_handoff(log: TaskLog | None = None) -> AgentRoute:
    """Leftover zoom/click after a recipe — always the cheap CU model (easy budget)."""
    override = (os.environ.get("AGENT_MODEL") or "").strip()
    if override:
        route = _route(override, "easy")
        if log is not None:
            log.record(
                "router",
                f"override {override}",
                {"model": override, "difficulty": "easy", "max_steps": route.max_steps},
            )
        return route
    route = _route(MODEL_EASY, "easy")
    print(f"[router] recipe leftover → {MODEL_EASY} (max_steps={route.max_steps})")
    if log is not None:
        log.record(
            "router",
            f"recipe-handoff → {MODEL_EASY}",
            {"model": MODEL_EASY, "difficulty": "easy", "max_steps": route.max_steps},
        )
    return route


def _difficulty_for_task(
    task: str,
    *,
    execution_path: str | None = None,
    specialist_lane: str | None = None,
    difficulty: str | None = None,
) -> str:
    """Use an explicit hint, else the deterministic execution route (medium if unsure)."""
    chosen = (difficulty or "").strip().lower()
    if chosen in DIFFICULTY_MODELS:
        return chosen
    from execution_router import infer_difficulty

    inferred = infer_difficulty(task, path=execution_path, lane=specialist_lane)
    if inferred in DIFFICULTY_MODELS:
        return inferred
    return "medium"


def resolve_agent_model(
    client: OpenAI,
    task: str,
    log: TaskLog | None = None,
    *,
    fallback_max_steps: int | None = None,
    execution_path: str | None = None,
    specialist_lane: str | None = None,
    difficulty: str | None = None,
) -> AgentRoute:
    """
    Choose the computer-agent model and step budget.

    If AGENT_MODEL is set, use it (manual override) and keep fallback_max_steps
    when provided, else the hard budget.
    Else if AGENT_ROUTE is on, map the deterministic execution route to
    easy/medium/hard (no extra LLM call). Ambiguous tasks fall back to medium.
    Else fall back to AGENT_MODEL_HARD with the hard step budget.
    """
    _ = client  # kept for call-site compatibility; routing is deterministic
    override = (os.environ.get("AGENT_MODEL") or "").strip()
    if override:
        chosen = "hard"
        steps = fallback_max_steps if fallback_max_steps is not None else max_steps_for_difficulty(chosen)
        print(f"[router] AGENT_MODEL override → {override} (max_steps={steps})")
        if log is not None:
            log.record(
                "router",
                f"override {override}",
                {"model": override, "difficulty": chosen, "max_steps": steps},
            )
        return AgentRoute(model=override, difficulty=chosen, max_steps=steps)

    if not AGENT_ROUTE:
        route = _route(MODEL_HARD, "hard")
        print(f"[router] routing disabled → {MODEL_HARD} (max_steps={route.max_steps})")
        if log is not None:
            log.record(
                "router",
                f"disabled {MODEL_HARD}",
                {"model": MODEL_HARD, "difficulty": "hard", "max_steps": route.max_steps},
            )
        return route

    chosen = _difficulty_for_task(
        task,
        execution_path=execution_path,
        specialist_lane=specialist_lane,
        difficulty=difficulty,
    )
    route = _route(DIFFICULTY_MODELS[chosen], chosen)
    lane = (specialist_lane or "").strip().lower() or "unspecified"
    path = (execution_path or "").strip().lower() or "inferred"
    print(
        f"[router] {path}/{lane} {chosen} → {route.model} (max_steps={route.max_steps})",
        flush=True,
    )
    if log is not None:
        log.record(
            "router",
            f"{chosen} → {route.model}",
            {
                "execution_path": path,
                "specialist_lane": lane,
                "difficulty": chosen,
                "model": route.model,
                "max_steps": route.max_steps,
            },
        )
    return route


def resolve_agent_model_name(
    client: OpenAI,
    task: str,
    log: TaskLog | None = None,
) -> str:
    """Back-compat: model id only."""
    return resolve_agent_model(client, task, log).model


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
    progress_delta = _progress_since_last_evaluation(log)
    instructions = (
        "You are a concise coach for a desktop computer-use agent. "
        "Given the goal, recent steps, and current screenshot, guide the next actions. "
        "The action/result log is authoritative: an action recorded there was already "
        "attempted. Never recommend an already successful or visibly completed action. "
        "Before giving guidance, compare the previous evaluator guidance with the actions "
        "and results performed since then. Treat fulfilled guidance as completed. Only "
        "recommend retrying an action when the log or screenshot provides concrete evidence "
        "that it failed; state that evidence and propose a materially different retry. "
        "Do not invent UI that is not visible. Prefer concrete, short guidance. "
        "Name the remaining GOAL and what is wrong on screen (wrong chat, missing window). "
        "Do not write click-by-click, keypress, type-character, or Enter recipes — "
        "the agent chooses actions from the screenshot. "
        "If the goal appears satisfied, say so. If the agent is looping or lost, say so. "
        "Starting media playback is done — do not tell the agent to sleep for duration, "
        "use macOS say, or wait in Terminal until a song or video finishes. "
        "For public information retrieval, do not recommend visible browser UI after "
        "a failed browser_data fetch unless the log also shows a browser_data "
        "discover_endpoints attempt (or the task requires authentication/interaction)."
    )
    content: list[dict[str, Any]] = [
        {
            "type": "input_text",
            "text": (
                f"Goal:\n{task}\n\n"
                f"Computer turns so far: {step_n}\n\n"
                f"Recent steps:\n{recent}\n\n"
                f"Progress checkpoint:\n{progress_delta}\n\n"
                "Reply JSON only:\n"
                "{\n"
                '  "status": "on_track" | "drifting" | "stuck" | "likely_done",\n'
                '  "completed_since_last_review": ["completed outcome", "..."],\n'
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
        response = _client_for_model(client, EVAL_MODEL).responses.create(
            model=model_for_request(EVAL_MODEL, has_image=bool(screenshot_b64)),
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
    completed = data.get("completed_since_last_review") or []
    if isinstance(completed, str):
        completed = [completed]
    completed = [str(item).strip() for item in completed if str(item).strip()][:10]
    guidance = data.get("guidance") or []
    if isinstance(guidance, str):
        guidance = [guidance]
    guidance = [str(g).strip() for g in guidance if str(g).strip()][:6]
    next_focus = str(data.get("next_focus") or "").strip()

    print(f"[eval] step {step_n}: {status}" + (f" — {next_focus}" if next_focus else ""))
    log.record(
        "evaluator",
        f"{status}: {next_focus or (guidance[0] if guidance else '')}",
        {
            "status": status,
            "completed_since_last_review": completed,
            "guidance": guidance,
            "next_focus": next_focus,
            "step": step_n,
        },
    )

    lines = [
        "Evaluator coaching (advisory — remaining GOAL only, not a click script; "
        "adapt to what you see; do not ignore the screen):",
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
