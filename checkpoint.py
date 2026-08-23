"""Orchestrator turn checkpoint (harness-v2 §4).

Between turns the lane passes a checkpoint:
  1. Apply deferred writes (pending function outputs).
  2. Consume next_run queue items into this turn's utterance path.
  3. Compact if the next request would not fit / periodic fold.
  4. Capture live desktop context for the model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from context import TurnDesktopContext, capture_turn_desktop_context
from events import emit
from input_queues import NextRunQueue, QueuedMessage, get_next_run_queue
from session_compact import SessionCompactState, maybe_compact_checkpoint, recover_from_overflow


@dataclass
class CheckpointResult:
    task_history: list[dict[str, str]]
    reset_thread: bool = False
    desktop: TurnDesktopContext = field(default_factory=lambda: TurnDesktopContext(""))
    next_run_messages: list[QueuedMessage] = field(default_factory=list)
    pending_fn_outputs: list[dict] = field(default_factory=list)


def run_orchestrator_checkpoint(
    client: Any,
    compact_state: SessionCompactState,
    task_history: list[dict[str, str]],
    *,
    pending_fn_outputs: list[dict] | None = None,
    next_run_queue: NextRunQueue | None = None,
    capture_desktop: bool = True,
    after_task: bool = False,
    overflow: bool = False,
) -> CheckpointResult:
    """
    Run one orchestrator checkpoint before (or after recovering) a model call.

    Order matches harness-v2: deferred → queues → compact → fresh context.
    """
    deferred = list(pending_fn_outputs or [])
    queue = next_run_queue if next_run_queue is not None else get_next_run_queue()
    next_msgs = queue.drain() if not overflow else []

    if overflow:
        task_history, reset_thread = recover_from_overflow(client, compact_state, task_history)
        emit("compact", lane="main", reason="overflow", reset_thread=reset_thread)
    else:
        task_history, reset_thread = maybe_compact_checkpoint(
            client,
            compact_state,
            task_history,
            after_task=after_task,
        )
        if reset_thread or after_task:
            emit(
                "compact",
                lane="main",
                reason="after_task" if after_task else "periodic",
                reset_thread=reset_thread,
            )

    desktop = TurnDesktopContext("")
    if capture_desktop:
        desktop = capture_turn_desktop_context()

    emit(
        "checkpoint",
        lane="main",
        reset_thread=reset_thread,
        deferred=len(deferred),
        next_run=len(next_msgs),
        desktop_chars=len(desktop.text or ""),
        has_screenshot=bool(desktop.screenshot_png),
    )
    return CheckpointResult(
        task_history=task_history,
        reset_thread=reset_thread,
        desktop=desktop,
        next_run_messages=next_msgs,
        pending_fn_outputs=deferred,
    )
