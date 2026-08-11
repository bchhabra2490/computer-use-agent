"""
Shared live status + recent log lines for the macOS menu-bar tray.

Orchestrator / agent write here; `status_tray.py` polls and shows hover tooltip
+ click menu. State lives in a JSON file so separate processes can share it.
"""

from __future__ import annotations

import json
import os
import re
import signal
import threading
import time
from pathlib import Path
from typing import Any

RUNTIME_DIR = Path(
    os.environ.get(
        "AGENT_RUNTIME_DIR",
        str(Path(__file__).resolve().parent / ".runtime"),
    )
)
STATUS_PATH = RUNTIME_DIR / "status.json"
MAX_LOG_LINES = int(os.environ.get("STATUS_LOG_LINES", "40"))

_lock = threading.Lock()


def _default_state() -> dict[str, Any]:
    return {
        "state": "idle",
        "detail": "",
        "updated_at": 0.0,
        "logs": [],
        "log_dir": None,
        "task": None,
        "orchestrator_pid": None,
        "agent_pid": None,
        "tray_pid": None,
        "quit_requested": False,
        "done_requested": False,
        "done_agent_id": None,
        "agents": [],  # active subagents / computer-agent jobs
    }


def _ensure_dir() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def _read() -> dict[str, Any]:
    if not STATUS_PATH.exists():
        return _default_state()
    try:
        data = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _default_state()
        base = _default_state()
        base.update(data)
        if not isinstance(base.get("logs"), list):
            base["logs"] = []
        if not isinstance(base.get("agents"), list):
            base["agents"] = []
        return base
    except Exception:
        return _default_state()


def _write(data: dict[str, Any]) -> None:
    _ensure_dir()
    data["updated_at"] = time.time()
    tmp = STATUS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATUS_PATH)


def read_status() -> dict[str, Any]:
    """Snapshot for the tray (or callers)."""
    with _lock:
        return _read()


def set_state(state: str, detail: str = "", *, task: str | None = None, log_dir: str | None = None) -> None:
    """Update high-level status shown in the menu bar."""
    state = (state or "idle").strip() or "idle"
    detail = (detail or "").strip()
    with _lock:
        data = _read()
        data["state"] = state
        data["detail"] = detail
        if task is not None:
            data["task"] = task
        if log_dir is not None:
            data["log_dir"] = log_dir
        _write(data)


def log(message: str, *, also_print: bool = False) -> None:
    """Append a line to the ring buffer shown on hover / in the menu."""
    message = (message or "").strip()
    if not message:
        return
    if also_print:
        print(message, flush=True)
    stamp = time.strftime("%H:%M:%S")
    line = f"{stamp} {message}"
    with _lock:
        data = _read()
        logs = list(data.get("logs") or [])
        logs.append(line)
        if len(logs) > MAX_LOG_LINES:
            logs = logs[-MAX_LOG_LINES:]
        data["logs"] = logs
        _write(data)


def set_and_log(state: str, message: str, *, detail: str | None = None, **kwargs: Any) -> None:
    """Set state and append the same message to the log ring."""
    detail = message if detail is None else detail
    set_state(state, detail, **kwargs)
    log(message)


def clear_logs() -> None:
    with _lock:
        data = _read()
        data["logs"] = []
        _write(data)


def set_tray_pid(pid: int | None) -> None:
    with _lock:
        data = _read()
        data["tray_pid"] = pid
        _write(data)


def register_orchestrator(pid: int | None = None) -> None:
    with _lock:
        data = _read()
        data["orchestrator_pid"] = int(pid if pid is not None else os.getpid())
        data["quit_requested"] = False
        data["done_requested"] = False
        data["done_agent_id"] = None
        _write(data)


def unregister_orchestrator() -> None:
    with _lock:
        data = _read()
        data["orchestrator_pid"] = None
        data["quit_requested"] = False
        data["agents"] = []
        _write(data)


def register_agent_process(pid: int | None = None) -> None:
    """Standalone `python agent.py` process (not under orchestrator)."""
    with _lock:
        data = _read()
        data["agent_pid"] = int(pid if pid is not None else os.getpid())
        data["quit_requested"] = False
        _write(data)


def unregister_agent_process() -> None:
    with _lock:
        data = _read()
        data["agent_pid"] = None
        _write(data)


def request_quit() -> None:
    """Ask the orchestrator (or standalone agent) to exit."""
    with _lock:
        data = _read()
        data["quit_requested"] = True
        _write(data)
    log("Quit requested from menu bar")


def clear_quit_request() -> None:
    with _lock:
        data = _read()
        data["quit_requested"] = False
        _write(data)


def quit_requested() -> bool:
    with _lock:
        return bool(_read().get("quit_requested"))


_MARK_DONE_RE = re.compile(
    r"\b("
    r"mark (?:it |the task |this |the job )?(?:as )?done"
    r"|mark done"
    r"|that(?:'s| is) done"
    r"|task is done"
    r"|stop (?:the )?(?:task|agent)"
    r"|no (?:other|further) actions?(?: (?:is|are))? required"
    r"|no further action"
    r"|nothing else (?:to do|needed|required)"
    r"|that(?:'s| is) all(?: we need)?"
    r")\b",
    re.IGNORECASE,
)


def is_mark_done_utterance(text: str) -> bool:
    """True when the user wants the running computer task marked complete."""
    low = (text or "").strip().lower()
    if not low:
        return False
    if _MARK_DONE_RE.search(low):
        return True
    return low in {"done", "finished", "complete", "that's it", "thats it"}


def request_mark_done(agent_id: str | None = None) -> None:
    """Ask the running computer-agent job to finish (menu bar or voice)."""
    agent_id = (agent_id or "").strip() or None
    with _lock:
        data = _read()
        data["done_requested"] = True
        data["done_agent_id"] = agent_id
        _write(data)
    if agent_id:
        log(f"Mark done requested (agent {agent_id})")
    else:
        log("Mark done requested")


def mark_done_pending(agent_id: str | None = None) -> bool:
    """True if mark-done was requested for this agent (or for all agents)."""
    agent_id = (agent_id or "").strip() or None
    with _lock:
        data = _read()
        if not data.get("done_requested"):
            return False
        target = (data.get("done_agent_id") or "").strip() or None
        if target and agent_id and target != agent_id:
            return False
        return True


def consume_mark_done(agent_id: str | None = None) -> bool:
    """Like mark_done_pending, but clears the flag when it matches."""
    agent_id = (agent_id or "").strip() or None
    with _lock:
        data = _read()
        if not data.get("done_requested"):
            return False
        target = (data.get("done_agent_id") or "").strip() or None
        if target and agent_id and target != agent_id:
            return False
        data["done_requested"] = False
        data["done_agent_id"] = None
        _write(data)
        return True


def clear_mark_done() -> None:
    with _lock:
        data = _read()
        data["done_requested"] = False
        data["done_agent_id"] = None
        _write(data)


def pid_alive(pid: Any) -> bool:
    try:
        p = int(pid)
    except (TypeError, ValueError):
        return False
    if p <= 0:
        return False
    try:
        os.kill(p, 0)
        return True
    except OSError:
        return False


def signal_quit_orchestrator() -> bool:
    """
    Soft-quit via flag, then SIGTERM the orchestrator process if known.

    Returns True if a signal was sent (or only the flag was set because no pid).
    """
    request_quit()
    data = read_status()
    pid = data.get("orchestrator_pid")
    if pid_alive(pid):
        try:
            os.kill(int(pid), signal.SIGTERM)
            log(f"Sent SIGTERM to orchestrator (pid={pid})")
            return True
        except OSError as e:
            log(f"Failed to signal orchestrator: {e}")
            return False
    # Standalone agent?
    apid = data.get("agent_pid")
    if pid_alive(apid):
        try:
            os.kill(int(apid), signal.SIGTERM)
            log(f"Sent SIGTERM to agent (pid={apid})")
            return True
        except OSError as e:
            log(f"Failed to signal agent: {e}")
            return False
    return True


def upsert_agent(
    agent_id: str,
    *,
    task: str,
    kind: str = "computer-agent",
    status: str = "running",
    log_dir: str | None = None,
) -> None:
    """Register or refresh an in-progress subagent / computer-agent job."""
    agent_id = (agent_id or "").strip()
    if not agent_id:
        return
    task = (task or "").strip()
    now = time.time()
    with _lock:
        data = _read()
        agents = [a for a in (data.get("agents") or []) if isinstance(a, dict)]
        found = None
        for a in agents:
            if a.get("id") == agent_id:
                found = a
                break
        if found is None:
            found = {
                "id": agent_id,
                "kind": kind,
                "task": task,
                "status": status,
                "started_at": now,
                "log_dir": log_dir,
            }
            agents.append(found)
        else:
            found["kind"] = kind
            found["task"] = task or found.get("task")
            found["status"] = status
            if log_dir is not None:
                found["log_dir"] = log_dir
            found["updated_at"] = now
        data["agents"] = agents
        if task:
            data["task"] = task
        if log_dir is not None:
            data["log_dir"] = log_dir
        _write(data)


def remove_agent(agent_id: str) -> None:
    agent_id = (agent_id or "").strip()
    if not agent_id:
        return
    with _lock:
        data = _read()
        agents = [a for a in (data.get("agents") or []) if isinstance(a, dict) and a.get("id") != agent_id]
        data["agents"] = agents
        if not agents:
            # Clear primary task if nothing left running.
            if data.get("state") == "agent":
                data["detail"] = "No active agents"
        _write(data)


def active_agents(data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = data or read_status()
    agents = [a for a in (data.get("agents") or []) if isinstance(a, dict)]
    return [a for a in agents if (a.get("status") or "running") != "done"]


def format_tooltip(data: dict[str, Any] | None = None, *, max_log_lines: int = 10) -> str:
    """Plain-text tooltip for NSStatusItem hover."""
    data = data or read_status()
    state = data.get("state") or "idle"
    detail = (data.get("detail") or "").strip()
    task = (data.get("task") or "").strip()
    lines = [f"Jarvis · {state}"]
    if detail:
        lines.append(detail[:120])
    agents = active_agents(data)
    if agents:
        lines.append(f"In progress ({len(agents)}):")
        for a in agents[:5]:
            label = (a.get("task") or a.get("id") or "?").strip()
            kind = (a.get("kind") or "agent").strip()
            lines.append(f"  • [{kind}] {label[:90]}")
    elif task:
        lines.append(f"Task: {task[:100]}")
    logs = list(data.get("logs") or [])
    if logs:
        lines.append("─" * 24)
        for entry in logs[-max_log_lines:]:
            lines.append(entry[:140])
    else:
        lines.append("(no recent logs)")
    text = "\n".join(lines)
    if len(text) > 1800:
        text = text[:1800] + "\n…"
    return text


def status_label(data: dict[str, Any] | None = None) -> str:
    data = data or read_status()
    agents = active_agents(data)
    state = data.get("state") or "idle"
    if agents:
        return f"{state} · {len(agents)} agent(s)"[:80]
    detail = (data.get("detail") or "").strip()
    if detail:
        return f"{state}: {detail}"[:80]
    return str(state)
