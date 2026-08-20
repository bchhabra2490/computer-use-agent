"""In-memory work list for mid-task routing (slice 1).

``inbox`` holds desktop goals that must wait until the current computer-use
job finishes. Related mid-task lines still go over the ZeroMQ bus, not here.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

_lock = threading.Lock()
_seq = 0
_inbox: list["InboxItem"] = []
_running_goal: str | None = None
_running_id: str | None = None
_sidequests: list["Sidequest"] = []


@dataclass(frozen=True)
class InboxItem:
    id: str
    goal: str
    user_said: str


@dataclass(frozen=True)
class Sidequest:
    user: str
    summary: str


def reset() -> None:
    global _seq, _running_goal, _running_id
    with _lock:
        _inbox.clear()
        _sidequests.clear()
        _seq = 0
        _running_goal = None
        _running_id = None


def set_running(job_id: str, goal: str) -> None:
    global _running_id, _running_goal
    with _lock:
        _running_id = (job_id or "").strip() or None
        _running_goal = (goal or "").strip() or None


def clear_running() -> None:
    global _running_id, _running_goal
    with _lock:
        _running_id = None
        _running_goal = None


def running_goal() -> str | None:
    with _lock:
        return _running_goal


def running_id() -> str | None:
    with _lock:
        return _running_id


def enqueue_inbox(goal: str, *, user_said: str = "") -> InboxItem | None:
    """Queue a CU goal to run after the current job. Empty goals are ignored."""
    global _seq
    text = (goal or "").strip()
    if not text:
        return None
    said = (user_said or text).strip() or text
    with _lock:
        _seq += 1
        item = InboxItem(id=f"i{_seq}", goal=text, user_said=said)
        _inbox.append(item)
    print(f"[jobs] queued {item.id}: {item.goal[:120]}", flush=True)
    return item


def pop_inbox() -> InboxItem | None:
    with _lock:
        if not _inbox:
            return None
        return _inbox.pop(0)


def peek_inbox() -> list[InboxItem]:
    with _lock:
        return list(_inbox)


def record_sidequest(user: str, summary: str) -> None:
    """Keep a CU-blind Q&A so the main orchestrator can answer follow-ups."""
    said = (user or "").strip()
    body = (summary or "").strip()
    if not said and not body:
        return
    with _lock:
        _sidequests.append(Sidequest(user=said, summary=body))
    print(f"[jobs] sidequest: {said[:80]!r}", flush=True)


def format_sidequests(*, max_chars: int = 6_000) -> str:
    with _lock:
        rows = list(_sidequests)
    if not rows:
        return ""
    blocks = [
        "Side quests this session (answered while a computer-use job was running; "
        "that agent did not see them — you did, and should answer follow-ups):"
    ]
    for i, row in enumerate(rows, start=1):
        blocks.append(f"### Side quest {i}\nUser: {row.user}\n{row.summary}".strip())
    text = "\n\n".join(blocks)
    if len(text) > max_chars:
        return text[:max_chars] + "\n… (truncated)"
    return text
