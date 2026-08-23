"""Orchestrator session compaction: task history folding and thread summaries."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

TASK_HISTORY_KEEP = int(os.environ.get("ORCHESTRATOR_TASK_HISTORY_KEEP", "3"))
TURN_COMPACT_EVERY = int(os.environ.get("ORCHESTRATOR_TURN_COMPACT", "25"))
COMPACT_MODEL = (
    os.environ.get("ORCHESTRATOR_COMPACT_MODEL", "").strip()
    or os.environ.get("ORCHESTRATOR_MODEL", "gpt-5-mini")
)

_CONTEXT_OVERFLOW_RE = re.compile(
    r"context.?length|maximum.*context|token.*limit|too many tokens|"
    r"request too large|context window|max_tokens|reduce the length",
    re.IGNORECASE,
)

_TASK_SUMMARY_SYSTEM = """You maintain a rolling summary of completed desktop-agent tasks.
Merge new task outcomes into any existing summary. Keep facts the orchestrator needs later:
what was requested, what succeeded or failed, app names, URLs/titles (not raw https), leftovers.
Write compact prose or short bullets — no markdown headings. Do not invent details."""

_SESSION_SUMMARY_SYSTEM = """You summarize a voice-assistant session for context continuity.
Merge recent turns into any existing summary. Preserve: user goals, decisions, preferences
stated, open threads, speaker-related context, and what was already done on the Mac.
Omit tool JSON, repetition, and filler. Compact prose or bullets — no markdown headings."""


@dataclass
class SessionCompactState:
    turn_count: int = 0
    session_summary: str = ""
    task_summary: str = ""
    turn_log: list[str] = field(default_factory=list)
    overflow_recovery_used: bool = False

    def begin_turn(self) -> None:
        self.overflow_recovery_used = False

    def record_turn(self, utterance: str, turn_text: str) -> None:
        body = (turn_text or "").strip()
        if not body:
            body = "(no tool activity)"
        self.turn_log.append(f"User: {(utterance or '').strip()}\n{body}")
        if len(self.turn_log) > 30:
            self.turn_log = self.turn_log[-20:]
        self.turn_count += 1


def is_context_overflow_error(exc: BaseException) -> bool:
    parts: list[str] = [str(exc)]
    for attr in ("message", "body", "response"):
        val = getattr(exc, attr, None)
        if val is not None:
            parts.append(str(val))
    return bool(_CONTEXT_OVERFLOW_RE.search("\n".join(parts)))


def format_task_history_block(
    history: list[dict[str, str]],
    *,
    task_summary: str = "",
) -> str:
    """Format task history for prompts: summarized older tasks + last N verbatim."""
    parts: list[str] = []
    summary = (task_summary or "").strip()
    if summary:
        parts.append(f"### Earlier tasks (summarized)\n{summary}")
    if not history and not summary:
        return "(no computer tasks run yet in this session)"
    for i, entry in enumerate(history, start=1):
        parts.append(
            f"### Task {i}\n"
            f"Request:\n{entry.get('task', '')}\n\n"
            f"Result:\n{entry.get('result', '')}"
        )
    return "\n\n".join(parts)


def _clip(text: str, limit: int) -> str:
    body = (text or "").strip()
    if len(body) <= limit:
        return body
    cut = body[: limit - 1].rsplit("\n", 1)[0].rstrip()
    return (cut or body[: limit - 1]) + "…"


def _extract_response_text(response: Any) -> str:
    parts: list[str] = []
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) != "message":
            continue
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", None) == "output_text":
                text = (getattr(part, "text", None) or "").strip()
                if text:
                    parts.append(text)
    return "\n".join(parts).strip()


def _summarize(client: Any, *, system: str, user: str) -> str:
    response = client.responses.create(
        model=COMPACT_MODEL,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return _clip(_extract_response_text(response), 6000)


def _format_tasks_for_summary(tasks: list[dict[str, str]]) -> str:
    blocks: list[str] = []
    for entry in tasks:
        blocks.append(
            f"Request:\n{_clip(entry.get('task', ''), 2000)}\n\n"
            f"Result:\n{_clip(entry.get('result', ''), 4000)}"
        )
    return "\n\n---\n\n".join(blocks)


def summarize_tasks(
    client: Any,
    tasks: list[dict[str, str]],
    existing_summary: str,
) -> str:
    if not tasks:
        return existing_summary
    user = (
        f"Existing summary:\n{(existing_summary or '(none)').strip()}\n\n"
        f"New task(s) to merge:\n{_format_tasks_for_summary(tasks)}"
    )
    try:
        merged = _summarize(client, system=_TASK_SUMMARY_SYSTEM, user=user)
        return merged or existing_summary
    except Exception as e:
        print(f"[orchestrator] task summarize failed ({e}); keeping prior summary", flush=True)
        fallback = existing_summary.strip()
        for entry in tasks:
            line = _clip(entry.get("task", ""), 200)
            fallback = f"{fallback}\n- {line}".strip() if fallback else f"- {line}"
        return fallback


def fold_task_history(
    client: Any,
    state: SessionCompactState,
    task_history: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Keep the last ``TASK_HISTORY_KEEP`` tasks; summarize older ones into ``task_summary``."""
    while len(task_history) > TASK_HISTORY_KEEP:
        dropped = task_history.pop(0)
        state.task_summary = summarize_tasks(client, [dropped], state.task_summary)
        print(
            f"[orchestrator] folded task history ({len(task_history)} kept, summary updated)",
            flush=True,
        )
    return task_history


def compact_session_thread(client: Any, state: SessionCompactState, *, reason: str) -> None:
    """Summarize recent turns into ``session_summary`` (resets turn counter)."""
    recent = "\n\n---\n\n".join(state.turn_log[-12:])
    if not recent.strip() and not state.session_summary.strip():
        state.turn_count = 0
        return
    user = (
        f"Reason: {reason}\n\n"
        f"Existing session summary:\n{(state.session_summary or '(none)').strip()}\n\n"
        f"Recent turns:\n{recent or '(none)'}"
    )
    try:
        merged = _summarize(client, system=_SESSION_SUMMARY_SYSTEM, user=user)
        if merged:
            state.session_summary = merged
    except Exception as e:
        print(f"[orchestrator] session summarize failed ({e})", flush=True)
    state.turn_log.clear()
    state.turn_count = 0
    print("[orchestrator] session context compacted", flush=True)


def maybe_compact_checkpoint(
    client: Any,
    state: SessionCompactState,
    task_history: list[dict[str, str]],
    *,
    after_task: bool = False,
) -> tuple[list[dict[str, str]], bool]:
    """
    Run compaction checkpoints.

    Returns ``(task_history, reset_previous_response_id)``.
    """
    reset_thread = False
    if after_task:
        task_history = fold_task_history(client, state, task_history)
    elif state.turn_count >= TURN_COMPACT_EVERY:
        compact_session_thread(client, state, reason=f"after {TURN_COMPACT_EVERY} turns")
        reset_thread = True
    return task_history, reset_thread


def recover_from_overflow(
    client: Any,
    state: SessionCompactState,
    task_history: list[dict[str, str]],
) -> tuple[list[dict[str, str]], bool]:
    """Aggressive compaction after a context overflow error. Returns (history, reset_thread)."""
    if state.overflow_recovery_used:
        return task_history, False
    state.overflow_recovery_used = True
    task_history = fold_task_history(client, state, task_history)
    compact_session_thread(client, state, reason="context overflow")
    print("[orchestrator] overflow recovery: compacted session and folded tasks", flush=True)
    return task_history, True
