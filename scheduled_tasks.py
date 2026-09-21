"""Durable scheduled task queue.

Stores normalized future task requests under ``.runtime/`` in SQLite so the
orchestrator and chat-bridge processes can schedule, cancel, and claim work
without overwriting each other. A JSON file from older builds is imported once.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Literal

ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = Path(os.environ.get("AGENT_RUNTIME_DIR", str(ROOT / ".runtime")))
QUEUE_PATH = RUNTIME_DIR / "scheduled-tasks.json"

MIN_FUTURE_SECONDS = 1.0
MAX_FUTURE_SECONDS = 30 * 86400.0

TaskStatus = Literal["queued", "running", "done", "cancelled", "failed"]
TaskSource = Literal["user", "agent", "system"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    run_at REAL NOT NULL,
    created_at REAL NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    parent_task_id TEXT,
    note TEXT,
    started_at REAL,
    finished_at REAL,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_sched_status_run
    ON scheduled_tasks(status, run_at, created_at, id);
"""

_INIT_THREAD_LOCK = threading.Lock()
_INIT_ATTEMPTS = 8
_INIT_RETRY_SEC = 0.05


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


def _db_file() -> Path:
    return RUNTIME_DIR / "scheduled-tasks.db"


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


def _row_to_task(row: sqlite3.Row) -> ScheduledTask:
    return _from_dict(dict(row))


def _json_migrated_path() -> Path:
    return QUEUE_PATH.with_suffix(".json.migrated")


def _json_queue_sources() -> list[tuple[Path, bool]]:
    """JSON files to import. ``True`` means archive after a successful commit."""
    sources: list[tuple[Path, bool]] = []
    if QUEUE_PATH.is_file():
        sources.append((QUEUE_PATH, True))
    migrated = _json_migrated_path()
    if migrated.is_file():
        sources.append((migrated, False))
    return sources


def _import_json_queue(conn: sqlite3.Connection, path: Path) -> None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    rows = raw if isinstance(raw, list) else raw.get("tasks", [])
    if not isinstance(rows, list):
        return
    for item in rows:
        if not isinstance(item, dict):
            continue
        task = _from_dict(item)
        if not task.task:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO scheduled_tasks (
                id, task, run_at, created_at, source, status,
                parent_task_id, note, started_at, finished_at, last_error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.id,
                task.task,
                task.run_at,
                task.created_at,
                task.source,
                task.status,
                task.parent_task_id,
                task.note,
                task.started_at,
                task.finished_at,
                task.last_error,
            ),
        )


def _archive_json_queue(path: Path) -> None:
    dest = _json_migrated_path()
    try:
        if path.resolve() == dest.resolve():
            return
        if dest.exists():
            path.unlink()
        else:
            path.rename(dest)
    except OSError:
        pass


def _is_lock_error(exc: BaseException) -> bool:
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    text = str(exc).lower()
    return "locked" in text or "busy" in text


@contextmanager
def _schema_lock() -> Iterator[None]:
    """Cross-process lock so WAL/schema setup does not race on a new file."""
    _ensure_dir()
    lock_path = _db_file().with_name(_db_file().name + ".lock")
    with _INIT_THREAD_LOCK:
        fh = open(lock_path, "a+")
        try:
            try:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            except (ImportError, OSError):
                pass
            yield
        finally:
            try:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            fh.close()


def _prepare_connection(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(_SCHEMA)


def _open_connection() -> sqlite3.Connection:
    delay = _INIT_RETRY_SEC
    last_error: sqlite3.OperationalError | None = None
    for attempt in range(1, _INIT_ATTEMPTS + 1):
        conn = sqlite3.connect(str(_db_file()), timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            with _schema_lock():
                _prepare_connection(conn)
            return conn
        except sqlite3.OperationalError as e:
            conn.close()
            last_error = e
            if not _is_lock_error(e) or attempt >= _INIT_ATTEMPTS:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.5)
    assert last_error is not None
    raise last_error


@contextmanager
def _connect(*, write: bool = False) -> Iterator[sqlite3.Connection]:
    _ensure_dir()
    sources = _json_queue_sources()
    need_migrate = bool(sources)
    write = write or need_migrate
    pending_archive: list[Path] = []
    conn: sqlite3.Connection | None = None
    delay = _INIT_RETRY_SEC
    try:
        for attempt in range(1, _INIT_ATTEMPTS + 1):
            conn = _open_connection()
            try:
                if write:
                    conn.execute("BEGIN IMMEDIATE")
                break
            except sqlite3.OperationalError as e:
                conn.close()
                conn = None
                if not _is_lock_error(e) or attempt >= _INIT_ATTEMPTS:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 0.5)
        assert conn is not None
        if need_migrate:
            for path, archive in sources:
                _import_json_queue(conn, path)
                if archive:
                    pending_archive.append(path)
        yield conn
        if write:
            conn.commit()
            for path in pending_archive:
                _archive_json_queue(path)
    except Exception:
        if write and conn is not None:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
        raise
    finally:
        if conn is not None:
            conn.close()


def _sorted(tasks: list[ScheduledTask]) -> list[ScheduledTask]:
    return sorted(tasks, key=lambda row: (row.run_at, row.created_at, row.id))


def list_scheduled_tasks(*, include_finished: bool = False) -> list[ScheduledTask]:
    with _connect() as conn:
        if include_finished:
            rows = conn.execute("SELECT * FROM scheduled_tasks").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM scheduled_tasks WHERE status NOT IN ('done', 'cancelled')"
            ).fetchall()
    return _sorted([_row_to_task(row) for row in rows])


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
    with _connect(write=True) as conn:
        conn.execute(
            """
            INSERT INTO scheduled_tasks (
                id, task, run_at, created_at, source, status,
                parent_task_id, note, started_at, finished_at, last_error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.id,
                row.task,
                row.run_at,
                row.created_at,
                row.source,
                row.status,
                row.parent_task_id,
                row.note,
                row.started_at,
                row.finished_at,
                row.last_error,
            ),
        )
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
    now = time.time()
    with _connect(write=True) as conn:
        if target_id:
            cur = conn.execute(
                """
                UPDATE scheduled_tasks
                SET status = 'cancelled', finished_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (now, target_id),
            )
            if cur.rowcount:
                cancelled.append(target_id)
        if target_task:
            rows = conn.execute(
                """
                SELECT id FROM scheduled_tasks
                WHERE status = 'queued' AND lower(task) = ?
                """,
                (target_task,),
            ).fetchall()
            for item in rows:
                tid = str(item["id"])
                if tid in cancelled:
                    continue
                conn.execute(
                    """
                    UPDATE scheduled_tasks
                    SET status = 'cancelled', finished_at = ?
                    WHERE id = ? AND status = 'queued'
                    """,
                    (now, tid),
                )
                cancelled.append(tid)
    if not cancelled:
        return {"ok": False, "error": "no matching queued task"}
    return {"ok": True, "cancelled": cancelled}


def recover_pending_tasks() -> int:
    """Requeue interrupted work after a restart."""
    with _connect(write=True) as conn:
        cur = conn.execute(
            """
            UPDATE scheduled_tasks
            SET status = 'queued',
                started_at = NULL,
                last_error = 'Recovered after restart before completion.'
            WHERE status = 'running'
            """
        )
        return int(cur.rowcount or 0)


def claim_due_task(*, now: float | None = None) -> ScheduledTask | None:
    ts = time.time() if now is None else float(now)
    with _connect(write=True) as conn:
        row = conn.execute(
            """
            SELECT * FROM scheduled_tasks
            WHERE status = 'queued' AND run_at <= ?
            ORDER BY run_at, created_at, id
            LIMIT 1
            """,
            (ts,),
        ).fetchone()
        if row is None:
            return None
        cur = conn.execute(
            """
            UPDATE scheduled_tasks
            SET status = 'running', started_at = ?, last_error = NULL
            WHERE id = ? AND status = 'queued'
            """,
            (ts, row["id"]),
        )
        if int(cur.rowcount or 0) != 1:
            return None
        claimed = conn.execute(
            "SELECT * FROM scheduled_tasks WHERE id = ?",
            (row["id"],),
        ).fetchone()
    return None if claimed is None else _row_to_task(claimed)


def mark_task_finished(task_id: str, *, status: TaskStatus, error: str | None = None) -> bool:
    if status not in {"done", "failed", "cancelled"}:
        raise ValueError("status must be done, failed, or cancelled")
    with _connect(write=True) as conn:
        cur = conn.execute(
            """
            UPDATE scheduled_tasks
            SET status = ?, finished_at = ?, last_error = ?
            WHERE id = ?
            """,
            (status, time.time(), _clean_optional(error), task_id),
        )
        return int(cur.rowcount or 0) == 1


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
