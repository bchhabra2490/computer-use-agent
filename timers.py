"""In-process timers: schedule, list, cancel. No Clock.app, no model-exec.

A daemon thread per job fires a macOS notification and optionally queues TTS
for the orchestrator (never speaks from this thread).
"""

from __future__ import annotations

import subprocess
import threading
import time
from typing import Any

from app_status import enqueue_speak, reply_sink
from app_status import log as status_log

MIN_SECONDS = 1.0
MAX_SECONDS = 24 * 3600.0

_lock = threading.Lock()
_seq = 0
_jobs: dict[str, dict[str, Any]] = {}


def reset() -> None:
    """Cancel all timers (tests / shutdown)."""
    global _seq
    with _lock:
        jobs = list(_jobs.values())
        _jobs.clear()
        _seq = 0
    for job in jobs:
        timer = job.get("timer")
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass


def _next_id() -> str:
    global _seq
    with _lock:
        _seq += 1
        return f"t{_seq}"


def _osa_str(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace('"', '\\"')


def notify_macos(*, title: str, subtitle: str, body: str) -> None:
    """Show a macOS notification. Safe to call from a timer thread."""
    title = _osa_str((title or "Jarvis")[:80])
    subtitle = _osa_str((subtitle or "")[:80])
    body = _osa_str((body or "")[:200])
    script = (
        f'display notification "{body}" with title "{title}"'
        + (f' subtitle "{subtitle}"' if subtitle else "")
    )
    try:
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _fire(job_id: str) -> None:
    with _lock:
        job = _jobs.pop(job_id, None)
    if not job:
        return
    label = str(job.get("label") or "timer")
    message = str(job.get("message") or "").strip()
    speak = bool(job.get("speak"))
    body = message or f"{label} is done."
    notify_macos(title="Jarvis", subtitle=label, body=body)
    try:
        status_log(f"[timer] done: {label} — {body[:160]}")
    except Exception:
        pass
    if speak:
        try:
            enqueue_speak(body, source="timer", sink=str(job.get("sink") or "mac"))
        except Exception:
            pass


def set_timer(
    seconds: float,
    *,
    label: str = "timer",
    speak: bool = False,
    message: str | None = None,
) -> dict[str, Any]:
    try:
        secs = float(seconds)
    except (TypeError, ValueError):
        return {"ok": False, "error": "seconds must be a number"}
    if secs < MIN_SECONDS:
        return {"ok": False, "error": f"seconds must be at least {MIN_SECONDS:g}"}
    if secs > MAX_SECONDS:
        return {"ok": False, "error": f"seconds must be at most {int(MAX_SECONDS)}"}
    label = (label or "timer").strip() or "timer"
    label = label[:80]
    msg = (message or "").strip() or None
    job_id = _next_id()
    fire_at = time.time() + secs
    timer = threading.Timer(secs, _fire, args=(job_id,))
    timer.daemon = True
    try:
        sink = reply_sink()
    except Exception:
        sink = "mac"
    job = {
        "id": job_id,
        "label": label,
        "seconds": secs,
        "fire_at": fire_at,
        "speak": bool(speak),
        "message": msg,
        "sink": sink,
        "timer": timer,
    }
    with _lock:
        _jobs[job_id] = job
    timer.start()
    try:
        status_log(f"[timer] set {job_id} {label!r} in {secs:g}s speak={bool(speak)}")
    except Exception:
        pass
    return {
        "ok": True,
        "id": job_id,
        "label": label,
        "seconds": secs,
        "fire_at": fire_at,
        "speak": bool(speak),
    }


def list_timers() -> list[dict[str, Any]]:
    now = time.time()
    with _lock:
        rows = list(_jobs.values())
    out: list[dict[str, Any]] = []
    for job in rows:
        remaining = max(0.0, float(job["fire_at"]) - now)
        out.append(
            {
                "id": job["id"],
                "label": job["label"],
                "remaining_seconds": round(remaining, 1),
                "speak": bool(job.get("speak")),
            }
        )
    out.sort(key=lambda row: row["remaining_seconds"])
    return out


def cancel_timer(*, timer_id: str | None = None, label: str | None = None) -> dict[str, Any]:
    timer_id = (timer_id or "").strip() or None
    label = (label or "").strip() or None
    if not timer_id and not label:
        return {"ok": False, "error": "id or label required"}
    cancelled: list[str] = []
    with _lock:
        targets = []
        for job in list(_jobs.values()):
            if timer_id and job["id"] == timer_id:
                targets.append(job)
            elif label and not timer_id and str(job["label"]).lower() == label.lower():
                targets.append(job)
        for job in targets:
            _jobs.pop(job["id"], None)
            cancelled.append(job["id"])
            timer = job.get("timer")
            if timer is not None:
                try:
                    timer.cancel()
                except Exception:
                    pass
    if not cancelled:
        return {"ok": False, "error": "no matching timer"}
    try:
        status_log(f"[timer] cancelled {', '.join(cancelled)}")
    except Exception:
        pass
    return {"ok": True, "cancelled": cancelled}


def run_timer_tool(name: str, args: dict[str, Any] | None = None) -> str:
    args = args or {}
    if name == "set_timer":
        result = set_timer(
            args.get("seconds"),
            label=str(args.get("label") or "timer"),
            speak=bool(args.get("speak")),
            message=args.get("message"),
        )
        if not result.get("ok"):
            return f"Error: {result.get('error')}"
        speak = " and will speak a reminder" if result.get("speak") else ""
        return (
            f"Timer {result['id']} {result['label']!r} set for "
            f"{result['seconds']:g} seconds{speak}. Do not wait for it."
        )
    if name == "list_timers":
        rows = list_timers()
        if not rows:
            return "No timers running."
        lines = ["Active timers:"]
        for row in rows:
            lines.append(
                f"- {row['id']} {row['label']!r}: {row['remaining_seconds']:g}s left"
                + (" (will speak)" if row.get("speak") else "")
            )
        return "\n".join(lines)
    if name == "cancel_timer":
        result = cancel_timer(
            timer_id=str(args.get("id") or "") or None,
            label=str(args.get("label") or "") or None,
        )
        if not result.get("ok"):
            return f"Error: {result.get('error')}"
        return f"Cancelled: {', '.join(result['cancelled'])}."
    raise KeyError(f"Not a timer tool: {name}")
