"""Steer / follow-up / next-run input queues (harness-v2 §4).

- steer — mid-task correction; inject into the running agent immediately.
  Cleared / unused if the agent aborts before consumption.
- follow_up — applied when the model would stop (after a tool batch /
  when no further automatic continuation).
- next_run — seeds the *next* orchestrator turn; not injected into the
  current computer-use agent.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

from events import emit

QueueKind = Literal["steer", "follow_up", "next_run"]

# Wire kinds accepted on the ZeroMQ bus (plus legacy aliases).
BUS_KINDS = frozenset(
    {
        "steer",
        "follow_up",
        "next_run",
        "user_message",  # legacy → steer
        "directive",  # legacy → steer
    }
)


def normalize_bus_kind(kind: str | None) -> QueueKind:
    raw = (kind or "steer").strip().lower()
    if raw in {"follow_up", "follow-up", "followup"}:
        return "follow_up"
    if raw in {"next_run", "next-run", "nextrun"}:
        return "next_run"
    return "steer"


@dataclass(frozen=True)
class QueuedMessage:
    id: str
    kind: QueueKind
    text: str
    ts: float = field(default_factory=time.time)

    @classmethod
    def make(cls, text: str, *, kind: QueueKind = "steer") -> QueuedMessage:
        return cls(id=uuid.uuid4().hex[:12], kind=kind, text=(text or "").strip())


@dataclass
class DrainBatch:
    steer: list[QueuedMessage] = field(default_factory=list)
    follow_up: list[QueuedMessage] = field(default_factory=list)
    next_run: list[QueuedMessage] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.steer or self.follow_up or self.next_run)

    def all_texts(self, *kinds: QueueKind) -> list[str]:
        wanted = set(kinds) if kinds else {"steer", "follow_up", "next_run"}
        out: list[str] = []
        if "steer" in wanted:
            out.extend(m.text for m in self.steer if m.text)
        if "follow_up" in wanted:
            out.extend(m.text for m in self.follow_up if m.text)
        if "next_run" in wanted:
            out.extend(m.text for m in self.next_run if m.text)
        return out


class NextRunQueue:
    """In-process queue for messages that should start the next orch turn."""

    def __init__(self) -> None:
        self._items: list[QueuedMessage] = []
        self._lock = threading.Lock()

    def enqueue(self, text: str) -> QueuedMessage | None:
        msg = QueuedMessage.make(text, kind="next_run")
        if not msg.text:
            return None
        with self._lock:
            self._items.append(msg)
        emit("queue_enqueue", lane="main", kind="next_run", text=msg.text[:160], id=msg.id)
        return msg

    def drain(self) -> list[QueuedMessage]:
        with self._lock:
            items = list(self._items)
            self._items.clear()
        for msg in items:
            emit("queue_consume", lane="main", kind="next_run", text=msg.text[:160], id=msg.id)
        return items

    def peek(self) -> list[QueuedMessage]:
        with self._lock:
            return list(self._items)

    def clear(self) -> list[QueuedMessage]:
        """Drop without consuming (abort path). Returns cleared items."""
        with self._lock:
            items = list(self._items)
            self._items.clear()
        return items


_next_run: NextRunQueue | None = None
_next_lock = threading.Lock()


def get_next_run_queue() -> NextRunQueue:
    global _next_run
    with _next_lock:
        if _next_run is None:
            _next_run = NextRunQueue()
        return _next_run


def bind_next_run_queue(queue: NextRunQueue | None) -> NextRunQueue:
    global _next_run
    with _next_lock:
        _next_run = queue if queue is not None else NextRunQueue()
        return _next_run


def classify_utterance_for_agent(text: str) -> QueueKind:
    """
    Heuristic when the orchestrator forwards speech to a running agent.

    Default is steer (correct current work). Phrases that clearly wait until
    the current step finishes become follow_up. Explicit "later" / "next"
    become next_run.
    """
    low = (text or "").strip().lower()
    if not low:
        return "steer"
    if any(
        p in low
        for p in (
            "after that",
            "when you're done",
            "when you are done",
            "once you're done",
            "once you are done",
            "then also",
            "afterwards",
            "afterward",
        )
    ):
        return "follow_up"
    if any(
        p in low
        for p in (
            "next time",
            "for later",
            "remind me later",
            "after this task",
            "when this is finished",
        )
    ):
        return "next_run"
    return "steer"
