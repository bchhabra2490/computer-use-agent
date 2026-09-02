"""Process lifecycle, control flags, active-agent tracking, and status presentation.

Storage remains in :mod:`app_status`; its read/write functions retain the facade's
runtime-path configuration so existing callers can continue redirecting STATUS_PATH.
"""

from __future__ import annotations

import os
import re
import signal
import time
from types import ModuleType
from typing import Any


def _status_module() -> ModuleType:
    import app_status

    return app_status


class _StatusLock:
    """Resolve the facade lock lazily, avoiding an app_status import cycle."""

    def __enter__(self):
        self._lock = _status_module()._lock
        return self._lock.__enter__()

    def __exit__(self, exc_type, exc, traceback):
        return self._lock.__exit__(exc_type, exc, traceback)


_lock = _StatusLock()


def _read() -> dict[str, Any]:
    return _status_module()._read()


def _write(data: dict[str, Any]) -> None:
    _status_module()._write(data)


def read_status() -> dict[str, Any]:
    return _status_module().read_status()


def log(message: str, *, also_print: bool = False) -> None:
    _status_module().log(message, also_print=also_print)


def register_orchestrator(pid: int | None = None) -> None:
    with _lock:
        data = _read()
        data["orchestrator_pid"] = int(pid if pid is not None else os.getpid())
        data["quit_requested"] = False
        data["done_requested"] = False
        data["done_agent_id"] = None
        data["send_requested"] = False
        data["cancel_requested"] = False
        data["stt_active"] = False
        # Always start awake — Sleep is an opt-in toggle for the session.
        data["sleep_mode"] = False
        _write(data)
    try:
        from wake import on_sleep_mode_changed

        on_sleep_mode_changed(False)
    except Exception:
        pass


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
    r"|stop (?:the )?(?:task|agent|job|run)"
    r"|pause (?:the )?(?:task|agent|job|run)"
    r"|cancel (?:the )?(?:task|agent|job|run)"
    r"|no (?:other|further) actions?(?: (?:is|are))? required"
    r"|no further action"
    r"|nothing else (?:to do|needed|required)"
    r"|that(?:'s| is) all(?: we need)?"
    r")\b",
    re.IGNORECASE,
)

# Bare stop/pause — what users say when the agent says "say stop anytime".
# Keep these exact so "stop listening" / "stop the music" stay out.
_MARK_DONE_EXACT = frozenset(
    {
        "stop",
        "pause",
        "cancel",
        "abort",
        "halt",
        "done",
        "finished",
        "complete",
        "that's it",
        "thats it",
    }
)


def is_mark_done_utterance(text: str) -> bool:
    """True when the user wants the running computer task marked complete."""
    low = (text or "").strip().lower().rstrip(".!?")
    if not low:
        return False
    if low in _MARK_DONE_EXACT:
        return True
    if _MARK_DONE_RE.search(low):
        return True
    return False


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


def set_stt_listening(active: bool) -> None:
    """STT owns the mic — tray Send/Cancel are enabled while this is True."""
    with _lock:
        data = _read()
        data["stt_active"] = bool(active)
        if active:
            data["cancel_requested"] = False
            data["send_requested"] = False
        else:
            data["send_requested"] = False
            data["cancel_requested"] = False
        _write(data)


def request_listen() -> None:
    """Ask the idle orchestrator to bypass wake detection and open the mic."""
    with _lock:
        data = _read()
        data["listen_requested"] = True
        _write(data)
    log("Listen shortcut requested — opening mic")


def listen_pending() -> bool:
    with _lock:
        return bool(_read().get("listen_requested"))


def consume_listen() -> bool:
    """Consume one global listen-shortcut request."""
    with _lock:
        data = _read()
        if not data.get("listen_requested"):
            return False
        data["listen_requested"] = False
        _write(data)
        return True


def request_send() -> None:
    """End the current listen immediately and transcribe what was captured."""
    with _lock:
        data = _read()
        data["send_requested"] = True
        data["cancel_requested"] = False
        _write(data)
    log("Send requested — processing audio")


def send_pending() -> bool:
    with _lock:
        return bool(_read().get("send_requested"))


def consume_send() -> bool:
    """True if Send was clicked; clears the flag so it fires once."""
    with _lock:
        data = _read()
        if not data.get("send_requested"):
            return False
        data["send_requested"] = False
        _write(data)
        return True


def clear_send() -> None:
    with _lock:
        data = _read()
        data["send_requested"] = False
        _write(data)


def request_cancel() -> None:
    """Abort the current listen (no transcript) and stop in-flight agent work.

    While STT is active: discards capture. If computer-use agents are running:
    also requests mark-done so UI actions stop.
    """
    with _lock:
        data = _read()
        data["cancel_requested"] = True
        data["send_requested"] = False
        # Drop queued text/phone commands so they are not processed next.
        data["pending_utterances"] = []
        agents = list(data.get("agents") or [])
        _write(data)
    log("Cancel requested — abort listen / processing")
    if agents:
        request_mark_done()


def cancel_pending() -> bool:
    with _lock:
        return bool(_read().get("cancel_requested"))


def consume_cancel() -> bool:
    """True if Cancel was requested; clears the flag so it fires once."""
    with _lock:
        data = _read()
        if not data.get("cancel_requested"):
            return False
        data["cancel_requested"] = False
        _write(data)
        return True


def clear_cancel() -> None:
    with _lock:
        data = _read()
        data["cancel_requested"] = False
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
    except OSError:
        return False
    # Zombies still accept signal 0; treat them as dead so callers respawn.
    try:
        import subprocess

        out = subprocess.check_output(
            ["ps", "-p", str(p), "-o", "state="],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out.upper().startswith("Z"):
            return False
    except Exception:
        pass
    return True


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
    if data.get("sleep_mode"):
        lines.append("Sleep · wake word ignored (⌘⌃S)")
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
    if data.get("sleep_mode"):
        return f"sleep · {state}"[:80]
    if agents:
        return f"{state} · {len(agents)} agent(s)"[:80]
    detail = (data.get("detail") or "").strip()
    if detail:
        return f"{state}: {detail}"[:80]
    return str(state)
