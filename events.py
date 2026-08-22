"""Typed event sink for the orchestrator and computer agent.

Events observe execution and must never change it. Throwing listeners are
caught and reported; they do not abort the loop (harness-v2 §10).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

EventType = Literal[
    "turn_start",
    "turn_end",
    "llm_response",
    "tool_start",
    "tool_result",
    "compact",
    "checkpoint",
    "agent_start",
    "agent_end",
    "queue_enqueue",
    "queue_consume",
    "speak",
    "listen",
    "fault",
    "handler_error",
]

Lane = Literal["main", "agent"]


@dataclass(frozen=True)
class Event:
    type: EventType
    lane: Lane = "main"
    ts: float = field(default_factory=time.time)
    run_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


Listener = Callable[[Event], None]


class EventSink:
    """Flat in-process event bus. Listeners cannot mutate harness state."""

    def __init__(self) -> None:
        self._listeners: list[Listener] = []
        self._lock = threading.Lock()
        self._recent: list[Event] = []
        self._recent_limit = 200

    def on(self, listener: Listener) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                try:
                    self._listeners.remove(listener)
                except ValueError:
                    pass

        return unsubscribe

    def emit(
        self,
        type: EventType,
        *,
        lane: Lane = "main",
        run_id: str | None = None,
        **payload: Any,
    ) -> Event:
        event = Event(type=type, lane=lane, run_id=run_id, payload=dict(payload))
        with self._lock:
            self._recent.append(event)
            if len(self._recent) > self._recent_limit:
                self._recent = self._recent[-self._recent_limit :]
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception as e:
                self._report_handler_error(listeners, e, event)
        return event

    def _report_handler_error(
        self,
        listeners: list[Listener],
        error: BaseException,
        source: Event,
    ) -> None:
        fault = Event(
            type="handler_error",
            lane=source.lane,
            run_id=source.run_id,
            payload={
                "error": str(error),
                "source_type": source.type,
            },
        )
        for listener in listeners:
            try:
                listener(fault)
            except Exception:
                pass

    def recent(self, *, limit: int = 50) -> list[Event]:
        with self._lock:
            return list(self._recent[-limit:])


_default_sink: EventSink | None = None
_sink_lock = threading.Lock()


def get_events() -> EventSink:
    global _default_sink
    with _sink_lock:
        if _default_sink is None:
            _default_sink = EventSink()
            _default_sink.on(_default_logger)
        return _default_sink


def bind_events(sink: EventSink | None) -> EventSink:
    """Replace the process-wide sink (tests). Returns the active sink."""
    global _default_sink
    with _sink_lock:
        _default_sink = sink if sink is not None else EventSink()
        if sink is None:
            _default_sink.on(_default_logger)
        return _default_sink


def emit(
    type: EventType,
    *,
    lane: Lane = "main",
    run_id: str | None = None,
    **payload: Any,
) -> Event:
    return get_events().emit(type, lane=lane, run_id=run_id, **payload)


def _default_logger(event: Event) -> None:
    if event.type == "handler_error":
        print(
            f"[events] handler_error on {event.payload.get('source_type')}: "
            f"{event.payload.get('error')}",
            flush=True,
        )
        return
    if event.type in {"fault"}:
        print(f"[events] fault: {event.payload}", flush=True)
        try:
            from app_status import status_log

            status_log(f"[fault] {event.payload}")
        except Exception:
            pass
