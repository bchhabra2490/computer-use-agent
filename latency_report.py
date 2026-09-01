"""End-to-end voice-to-computer-action latency tracing and reports.

Traces are append-only JSONL so the voice orchestrator, chat bridge, and tests
can read them without a database migration. A compact Markdown report is kept
beside the raw data for humans and the ChatApp consumes the structured payload.
"""

from __future__ import annotations

import json
import os
import statistics
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
LATENCY_DIR = Path(os.environ.get("LATENCY_LOG_DIR") or ROOT / "logs" / "latency")
TRACES_PATH = LATENCY_DIR / "traces.jsonl"
REPORT_PATH = LATENCY_DIR / "report.md"
_LOCK = threading.RLock()
_ACTIVE: dict[str, dict[str, Any]] = {}
_CURRENT_ID: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _wall_ms() -> int:
    return round(time.time() * 1000)


def start_trace(*, source: str = "voice", wake_label: str = "") -> str:
    """Start a turn trace and make it the current orchestrator trace."""
    global _CURRENT_ID
    previous = current_trace_id()
    if previous:
        finish_trace(previous, status="superseded")
    trace_id = uuid.uuid4().hex
    now = _wall_ms()
    trace = {
        "id": trace_id,
        "source": (source or "voice").strip().lower(),
        "started_at": _utc_now(),
        "status": "running",
        "task": "",
        "milestones": {"wake_detected": now},
        "metadata": {"wake_label": wake_label} if wake_label else {},
    }
    with _LOCK:
        _ACTIVE[trace_id] = trace
        _CURRENT_ID = trace_id
    return trace_id


def current_trace_id() -> str | None:
    with _LOCK:
        return _CURRENT_ID


def mark(
    trace_id: str | None,
    milestone: str,
    *,
    task: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record the first occurrence of a milestone for an active trace."""
    if not trace_id or not milestone:
        return
    with _LOCK:
        trace = _ACTIVE.get(trace_id)
        if trace is None:
            return
        trace["milestones"].setdefault(milestone, _wall_ms())
        if task is not None and task.strip():
            trace["task"] = task.strip()
        if metadata:
            trace.setdefault("metadata", {}).update(metadata)


def finish_trace(
    trace_id: str | None,
    *,
    status: str = "completed",
    task: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Finalize and persist a trace. Safe to call more than once."""
    global _CURRENT_ID
    if not trace_id:
        return None
    with _LOCK:
        trace = _ACTIVE.pop(trace_id, None)
        if trace is None:
            return None
        now = _wall_ms()
        trace["milestones"].setdefault("task_complete", now)
        trace["status"] = (status or "completed").strip().lower()
        trace["ended_at"] = _utc_now()
        if task is not None and task.strip():
            trace["task"] = task.strip()
        if metadata:
            trace.setdefault("metadata", {}).update(metadata)
        trace["durations_ms"] = _durations(trace.get("milestones") or {})
        if _CURRENT_ID == trace_id:
            _CURRENT_ID = None
        _append_trace(trace)
        build_report()
        return dict(trace)


def abandon_trace(trace_id: str | None, *, reason: str = "abandoned") -> None:
    """Persist an incomplete trace so failed voice turns remain observable."""
    finish_trace(trace_id, status=reason)


def _durations(milestones: dict[str, Any]) -> dict[str, int]:
    def delta(start: str, end: str) -> int | None:
        a, b = milestones.get(start), milestones.get(end)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and b >= a:
            return round(b - a)
        return None

    pairs = {
        "wake_to_speech_end": ("wake_detected", "speech_finished"),
        "wake_to_transcript": ("wake_detected", "transcript_ready"),
        "transcript_to_plan": ("transcript_ready", "plan_ready"),
        "plan_to_agent_start": ("plan_ready", "agent_started"),
        "agent_start_to_first_action": ("agent_started", "first_computer_action"),
        "voice_to_first_action": ("wake_detected", "first_computer_action"),
        "voice_to_task_complete": ("wake_detected", "task_complete"),
    }
    return {name: value for name, pair in pairs.items() if (value := delta(*pair)) is not None}


def _append_trace(trace: dict[str, Any]) -> None:
    LATENCY_DIR.mkdir(parents=True, exist_ok=True)
    with TRACES_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(trace, ensure_ascii=False) + "\n")


def read_traces(*, limit: int = 200) -> list[dict[str, Any]]:
    if not TRACES_PATH.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = TRACES_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines[-max(1, limit) :]:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * percentile)))
    return ordered[index]


def report_payload(*, limit: int = 50) -> dict[str, Any]:
    traces = read_traces(limit=max(limit, 200))
    metric_names = (
        "voice_to_first_action",
        "wake_to_transcript",
        "transcript_to_plan",
        "plan_to_agent_start",
        "agent_start_to_first_action",
        "voice_to_task_complete",
    )
    metrics: dict[str, dict[str, int | None]] = {}
    for name in metric_names:
        values = [
            int(t.get("durations_ms", {}).get(name))
            for t in traces
            if isinstance(t.get("durations_ms", {}).get(name), (int, float))
        ]
        metrics[name] = {
            "count": len(values),
            "median_ms": round(statistics.median(values)) if values else None,
            "p90_ms": _percentile(values, 0.9),
            "min_ms": min(values) if values else None,
            "max_ms": max(values) if values else None,
        }
    completed_actions = metrics["voice_to_first_action"]["count"] or 0
    return {
        "ok": True,
        "generated_at": _utc_now(),
        "trace_count": len(traces),
        "completed_action_count": completed_actions,
        "metrics": metrics,
        "recent": list(reversed(traces[-max(1, limit) :])),
        "report_path": str(REPORT_PATH),
        "traces_path": str(TRACES_PATH),
    }


def _fmt_ms(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value / 1000:.2f}s" if value >= 1000 else f"{value}ms"


def build_report() -> Path:
    payload = report_payload(limit=20)
    metrics = payload["metrics"]
    labels = {
        "voice_to_first_action": "Voice → first action",
        "wake_to_transcript": "Wake → transcript",
        "transcript_to_plan": "Transcript → plan",
        "plan_to_agent_start": "Plan → agent start",
        "agent_start_to_first_action": "Agent start → first action",
        "voice_to_task_complete": "Voice → task complete",
    }
    lines = [
        "# Voice-to-action latency report",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "| Metric | Samples | Median | P90 | Min | Max |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, label in labels.items():
        row = metrics[key]
        lines.append(
            f"| {label} | {row['count']} | {_fmt_ms(row['median_ms'])} | "
            f"{_fmt_ms(row['p90_ms'])} | {_fmt_ms(row['min_ms'])} | {_fmt_ms(row['max_ms'])} |"
        )
    lines.extend(["", "## Recent traces", ""])
    recent = payload["recent"]
    if not recent:
        lines.append("No latency traces have been recorded yet.")
    else:
        lines.extend(
            [
                "| Started | Task | Status | First action | Complete |",
                "|---|---|---|---:|---:|",
            ]
        )
        for trace in recent:
            durations = trace.get("durations_ms") or {}
            task = str(trace.get("task") or "—").replace("|", "\\|")[:90]
            lines.append(
                f"| {trace.get('started_at', '—')} | {task} | {trace.get('status', '—')} | "
                f"{_fmt_ms(durations.get('voice_to_first_action'))} | "
                f"{_fmt_ms(durations.get('voice_to_task_complete'))} |"
            )
    LATENCY_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return REPORT_PATH
