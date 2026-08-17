"""Explicit voice-session phases. Tray status is a projection of this machine.

Phases match the strings already shown in the menu bar. Illegal transitions are
logged (and, in strict tests, raised) so barge-in / ask-user / agent overlap
cannot silently invent a new mode.
"""

from __future__ import annotations

from typing import Any

PHASES = frozenset(
    {
        "idle",
        "ready",
        "waiting",
        "listening",
        "thinking",
        "speaking",
        "agent",
        "ask",
        "done",
    }
)

# From → allowed next. Same-phase refresh is always allowed.
TRANSITIONS: dict[str, frozenset[str]] = {
    "idle": frozenset({"ready", "waiting", "listening", "thinking", "agent", "done"}),
    "ready": frozenset({"waiting", "listening", "thinking", "speaking", "agent", "ask", "done", "idle"}),
    "waiting": frozenset({"listening", "thinking", "speaking", "ready", "done", "idle"}),
    "listening": frozenset({"thinking", "speaking", "waiting", "ready", "idle", "done", "ask", "agent"}),
    "thinking": frozenset({"speaking", "agent", "ask", "listening", "waiting", "ready", "done", "idle"}),
    "speaking": frozenset({"listening", "waiting", "ready", "thinking", "agent", "ask", "done", "idle"}),
    "agent": frozenset({"ask", "speaking", "listening", "thinking", "ready", "waiting", "done", "idle"}),
    "ask": frozenset({"agent", "thinking", "listening", "speaking", "ready", "waiting", "done", "idle"}),
    "done": frozenset({"idle", "waiting", "ready"}),
}


class SessionError(ValueError):
    """Illegal phase transition (strict mode only)."""


class Session:
    """In-process session. ``enter`` writes the tray JSON via app_status."""

    def __init__(self, *, strict: bool = False, project_status: bool = True) -> None:
        self.phase = "idle"
        self.detail = ""
        self.strict = strict
        self.project_status = project_status
        self.history: list[tuple[str, str]] = [("idle", "")]

    def can_enter(self, phase: str) -> bool:
        phase = _canon(phase)
        if phase == self.phase:
            return True
        return phase in TRANSITIONS.get(self.phase, frozenset())

    def enter(
        self,
        phase: str,
        detail: str = "",
        *,
        task: str | None = None,
        log_dir: str | None = None,
        log: bool = False,
    ) -> str:
        """Move to ``phase``. Returns the phase actually entered."""
        phase = _canon(phase)
        detail = (detail or "").strip()
        if phase != self.phase and not self.can_enter(phase):
            msg = f"illegal session transition {self.phase} → {phase}"
            if self.strict:
                raise SessionError(msg)
            print(f"[session] {msg} (allowed)", flush=True)
        self.phase = phase
        self.detail = detail
        self.history.append((phase, detail))
        if self.project_status:
            _project(phase, detail, task=task, log_dir=log_dir, log=log)
        return phase

    def enter_and_log(self, phase: str, message: str, **kwargs: Any) -> str:
        return self.enter(phase, message, log=True, **kwargs)


_active: Session | None = None


def get_session() -> Session:
    global _active
    if _active is None:
        _active = Session()
    return _active


def bind_session(session: Session | None) -> Session | None:
    """Install the process-wide session. Pass None to clear."""
    global _active
    previous = _active
    _active = session
    return previous


def _canon(phase: str) -> str:
    key = (phase or "idle").strip().lower() or "idle"
    aliases = {"run": "agent", "running": "agent", "ask_user": "ask"}
    key = aliases.get(key, key)
    if key not in PHASES:
        return "idle"
    return key


def _project(
    phase: str,
    detail: str,
    *,
    task: str | None,
    log_dir: str | None,
    log: bool,
) -> None:
    from app_status import set_and_log, set_state

    if log and detail:
        set_and_log(phase, detail, task=task, log_dir=log_dir)
    else:
        set_state(phase, detail, task=task, log_dir=log_dir)
