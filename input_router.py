"""Choose the next orchestrator input without owning speech or tools.

The voice loop still lives in ``orchestrator.py``. This module only decides
whether the next turn comes from a scheduled task, a queued follow-up,
timer speech, or the microphone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class NextInput:
    action: str  # quit | continue | ready
    utterance: str | None = None
    scheduled_id: str | None = None
    pending: Any = None


def collect_next_input(
    pending: Any,
    *,
    claim_scheduled: Callable[[], tuple[str | None, str | None]],
    drain_next_run: Callable[[], list[Any]],
    speak_pending: Callable[[], bool],
    service_timer_speech: Callable[[], Any],
    listen: Callable[[], str | None],
    quit_requested: Callable[[], bool],
    on_quit: Callable[[], None],
    log_scheduled: Callable[[str], None] | None = None,
    log_next_run: Callable[[str], None] | None = None,
) -> NextInput:
    if pending is not None:
        return NextInput(action="ready", utterance=pending, pending=None)
    scheduled_utterance, scheduled_task_id = claim_scheduled()
    if scheduled_utterance:
        if log_scheduled is not None:
            log_scheduled(scheduled_utterance)
        return NextInput(
            action="ready",
            utterance=scheduled_utterance,
            scheduled_id=scheduled_task_id,
        )
    next_batch = drain_next_run()
    if next_batch:
        utterance = " ".join(m.text for m in next_batch if getattr(m, "text", None)).strip()
        if log_next_run is not None:
            log_next_run(utterance)
        return NextInput(action="ready", utterance=utterance)
    if speak_pending():
        return NextInput(action="continue", pending=service_timer_speech())
    utterance = listen()
    if quit_requested():
        on_quit()
        return NextInput(action="quit")
    if utterance is None:
        return NextInput(action="continue")
    return NextInput(action="ready", utterance=utterance)
