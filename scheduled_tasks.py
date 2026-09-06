"""Durable scheduled task queue.

Stores normalized future task requests under ``.runtime/`` so the orchestrator
can recover them after restart and promote due work into the normal turn flow.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = Path(
    __import__("os").environ.get("AGENT_RUNTIME_DIR", str(ROOT / ".runtime"))
)
QUEUE_PATH = RUNTIME_DIR / "scheduled-tasks.json"

MIN_FUTURE_SECONDS = 1.0
MAX_FUTURE_SECONDS = 30 * 86400.0

TaskStatus = Literal["queued", "running", "done", "cancelled", "failed"]
TaskSource = Literal["user", "agent", "system"]

_LOCK = threading.RLock()


@dataclass(frozen=True)
class ScheduledTask:
    id: str
    task: str
    run_at: float
    created_at: float
    source: TaskSource
    status: TaskStatus = "queued"
    parent_task_id: str | None = None
    note: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    last_error: str | None = None

    @property
    def run_at_iso(self) -> str:
        return _iso(self.run_at)


def _ensure_dir() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()


def _from_dict(row: dict[str, Any]) -> ScheduledTask:
    return ScheduledTask(
        id=str(row.get("id") or uuid.uuid4().hex[:12]),
        task=str(row.get("task") or "").strip(),
        run_at=float(row.get("run_at") or 0.0),
        created_at=float(row.get("created_at") or time.time()),
        source=_normalize_source(row.get("source")),
        status=_normalize_status(row.get("status")),
        parent_task_id=_clean_optional(row.get("parent_task_id")),
        note=_clean_optional(row.get("note")),
        started_at=_optional_float(row.get("started_at")),
        finished_at=_optional_float(row.get("finished_at")),
        last_error=_clean_optional(row.get("last_error")),
    )


def _clean_optional(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_status(value: Any) -> TaskStatus:
    text = str(value or "queued").strip().lower()
    if text in {"queued", "running", "done", "cancelled", "failed"}:
        return text  # type: ignore[return-value]
    return "queued"


def _normalize_source(value: Any) -> TaskSource:
    text = str(value or "system").strip().lower()
    if text in {"user", "agent", "system"}:
        return text  # type: ignore[return-value]
    return "system"


def _read_all_locked() -> list[ScheduledTask]:
    if not QUEUE_PATH.is_file():
        return []
    try:
        raw = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = raw if isinstance(raw, list) else raw.get("tasks", [])
    out: list[ScheduledTask] = []
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        task = _from_dict(row)
        if task.task:
            out.append(task)
    return out


def _write_all_locked(tasks: list[ScheduledTask]) -> None:
    _ensure_dir()
    payload = {"tasks": [asdict(task) for task in tasks]}
    tmp = RUNTIME_DIR / f"scheduled-tasks.{uuid.uuid4().hex}.tmp"
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(QUEUE_PATH)


def _sorted(tasks: list[ScheduledTask]) -> list[ScheduledTask]:
    return sorted(tasks, key=lambda row: (row.run_at, row.created_at, row.id))


def list_scheduled_tasks(*, include_finished: bool = False) -> list[ScheduledTask]:
    with _LOCK:
        rows = _read_all_locked()
    if not include_finished:
        rows = [row for row in rows if row.status not in {"done", "cancelled"}]
    return _sorted(rows)


def schedule_task(
    task: str,
    *,
    run_at: float,
    source: TaskSource = "system",
    parent_task_id: str | None = None,
    note: str | None = None,
) -> ScheduledTask:
    body = (task or "").strip()
    if not body:
        raise ValueError("task is required")
    now = time.time()
    when = float(run_at)
    delay = when - now
    if delay < MIN_FUTURE_SECONDS:
        raise ValueError(f"run_at must be at least {MIN_FUTURE_SECONDS:g}s in the future")
    if delay > MAX_FUTURE_SECONDS:
        raise ValueError(f"run_at must be within {int(MAX_FUTURE_SECONDS)} seconds")
    row = ScheduledTask(
        id=uuid.uuid4().hex[:12],
        task=body,
        run_at=when,
        created_at=now,
        source=source,
        status="queued",
        parent_task_id=_clean_optional(parent_task_id),
        note=_clean_optional(note),
    )
    with _LOCK:
        rows = _read_all_locked()
        rows.append(row)
        _write_all_locked(_sorted(rows))
    return row


def cancel_scheduled_task(
    *,
    task_id: str | None = None,
    task: str | None = None,
) -> dict[str, Any]:
    target_id = (task_id or "").strip() or None
    target_task = (task or "").strip().lower() or None
    if not target_id and not target_task:
        return {"ok": False, "error": "id or task required"}
    cancelled: list[str] = []
    with _LOCK:
        rows = _read_all_locked()
        updated: list[ScheduledTask] = []
        now = time.time()
        for row in rows:
            matches = False
            if target_id and row.id == target_id:
                matches = True
            elif target_task and row.task.lower() == target_task:
                matches = True
            if matches and row.status == "queued":
                cancelled.append(row.id)
                row = ScheduledTask(
                    **{
                        **asdict(row),
                        "status": "cancelled",
                        "finished_at": now,
                    }
                )
            updated.append(row)
        _write_all_locked(_sorted(updated))
    if not cancelled:
        return {"ok": False, "error": "no matching queued task"}
    return {"ok": True, "cancelled": cancelled}


def recover_pending_tasks() -> int:
    """Requeue interrupted work after a restart."""
    repaired = 0
    with _LOCK:
        rows = _read_all_locked()
        if not rows:
            return 0
        fixed: list[ScheduledTask] = []
        for row in rows:
            if row.status == "running":
                repaired += 1
                row = ScheduledTask(
                    **{
                        **asdict(row),
                        "status": "queued",
                        "started_at": None,
                        "last_error": "Recovered after restart before completion.",
                    }
                )
            fixed.append(row)
        if repaired:
            _write_all_locked(_sorted(fixed))
    return repaired


def claim_due_task(*, now: float | None = None) -> ScheduledTask | None:
    ts = time.time() if now is None else float(now)
    with _LOCK:
        rows = _read_all_locked()
        for idx, row in enumerate(_sorted(rows)):
            if row.status != "queued" or row.run_at > ts:
                continue
            claimed = ScheduledTask(
                **{
                    **asdict(row),
                    "status": "running",
                    "started_at": ts,
                    "last_error": None,
                }
            )
            # Replace matching id in original list order before persisting.
            for j, original in enumerate(rows):
                if original.id == row.id:
                    rows[j] = claimed
                    break
            _write_all_locked(_sorted(rows))
            return claimed
    return None


def mark_task_finished(task_id: str, *, status: TaskStatus, error: str | None = None) -> bool:
    if status not in {"done", "failed", "cancelled"}:
        raise ValueError("status must be done, failed, or cancelled")
    done = False
    with _LOCK:
        rows = _read_all_locked()
        for idx, row in enumerate(rows):
            if row.id != task_id:
                continue
            rows[idx] = ScheduledTask(
                **{
                    **asdict(row),
                    "status": status,
                    "finished_at": time.time(),
                    "last_error": _clean_optional(error),
                }
            )
            done = True
            break
        if done:
            _write_all_locked(_sorted(rows))
    return done


def format_scheduled_tasks(*, include_finished: bool = False) -> str:
    rows = list_scheduled_tasks(include_finished=include_finished)
    if not rows:
        return "No scheduled tasks."
    lines = ["Scheduled tasks:"]
    now = time.time()
    for row in rows:
        remaining = max(0.0, row.run_at - now)
        bits = [
            f"- {row.id} {row.status} at {row.run_at_iso}: {row.task}",
        ]
        if row.status == "queued":
            bits.append(f"({remaining:.0f}s left)")
        if row.parent_task_id:
            bits.append(f"[from {row.parent_task_id}]")
        lines.append(" ".join(bits))
    return "\n".join(lines)


def run_scheduled_task_tool(name: str, args: dict[str, Any] | None = None) -> str:
    args = args or {}
    if name == "schedule_task":
        try:
            run_at = float(args.get("run_at_epoch"))
        except (TypeError, ValueError):
            return "Error: run_at_epoch must be a number"
        try:
            row = schedule_task(
                str(args.get("task") or ""),
                run_at=run_at,
                source=_normalize_source(args.get("source")),
                parent_task_id=_clean_optional(args.get("parent_task_id")),
                note=_clean_optional(args.get("note")),
            )
        except ValueError as e:
            return f"Error: {e}"
        return (
            f"Scheduled task {row.id} for {row.run_at_iso}: {row.task}. "
            "It will run automatically when due."
        )
    if name == "list_scheduled_tasks":
        return format_scheduled_tasks(include_finished=bool(args.get("include_finished")))
    if name == "cancel_scheduled_task":
        result = cancel_scheduled_task(
            task_id=_clean_optional(args.get("id")),
            task=_clean_optional(args.get("task")),
        )
        if not result.get("ok"):
            return f"Error: {result.get('error')}"
        return f"Cancelled scheduled tasks: {', '.join(result['cancelled'])}."
    raise KeyError(f"Not a scheduled-task tool: {name}")
