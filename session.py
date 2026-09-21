"""Explicit voice-session phases. Tray status is a projection of this machine.

Phases match the strings already shown in the menu bar. Illegal transitions are
logged (and, in strict tests, raised) so barge-in / ask-user / agent overlap
cannot silently invent a new mode.
"""

from __future__ import annotations

import threading
import uuid
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


HISTORY_LIMIT = 200


class Session:
    """In-process session. ``enter`` writes the tray JSON via app_status."""

    def __init__(self, *, strict: bool = False, project_status: bool = True) -> None:
        self.phase = "idle"
        self.detail = ""
        self.strict = strict
        self.project_status = project_status
        self.history: list[tuple[str, str]] = [("idle", "")]
        self.session_id = uuid.uuid4().hex
        self.revision = 0
        self._lock = threading.RLock()
        if self.project_status:
            _claim_session(self.session_id)

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
        with self._lock:
            previous = self.phase
            legal = phase == previous or self.can_enter(phase)
            if phase != previous and not legal:
                msg = f"illegal session transition {self.phase} → {phase}"
                _emit_session_event(previous, phase, False, detail)
                if self.strict:
                    raise SessionError(msg)
                print(f"[session] {msg} (allowed)", flush=True)
            self.phase = phase
            self.detail = detail
            self.history.append((phase, detail))
            if len(self.history) > HISTORY_LIMIT:
                self.history = self.history[-HISTORY_LIMIT:]
            self.revision += 1
            revision = self.revision
            session_id = self.session_id
        if legal:
            _emit_session_event(previous, phase, True, detail)
        if self.project_status:
            _project(
                phase,
                detail,
                task=task,
                log_dir=log_dir,
                log=log,
                revision=revision,
                session_id=session_id,
            )
        return phase

    def enter_and_log(self, phase: str, message: str, **kwargs: Any) -> str:
        return self.enter(phase, message, log=True, **kwargs)


_active: Session | None = None
_active_lock = threading.RLock()


def get_session() -> Session:
    """Process-wide session owner. Mutate only through ``Session.enter``."""
    global _active
    with _active_lock:
        if _active is None:
            _active = Session()
        return _active


def bind_session(session: Session | None) -> Session | None:
    """Install the process-wide session owner. Pass None to clear."""
    global _active
    with _active_lock:
        previous = _active
        _active = session
    if session is not None and session.project_status:
        _claim_session(session.session_id)
    return previous


def _canon(phase: str) -> str:
    key = (phase or "idle").strip().lower() or "idle"
    aliases = {"run": "agent", "running": "agent", "ask_user": "ask"}
    key = aliases.get(key, key)
    if key not in PHASES:
        return "idle"
    return key


def _emit_session_event(previous: str, phase: str, legal: bool, detail: str) -> None:
    try:
        from events import emit

        emit(
            "session",
            from_phase=previous,
            to_phase=phase,
            legal=legal,
            detail=detail[:160],
        )
    except Exception:
        pass


def _claim_session(session_id: str) -> None:
    try:
        from app_status import claim_session

        claim_session(session_id)
    except Exception as e:
        print(f"[session] claim failed: {e}", flush=True)


def _project(
    phase: str,
    detail: str,
    *,
    task: str | None,
    log_dir: str | None,
    log: bool,
    revision: int,
    session_id: str,
) -> None:
    from app_status import set_and_log, set_state

    if log and detail:
        set_and_log(
            phase,
            detail,
            task=task,
            log_dir=log_dir,
            revision=revision,
            session_id=session_id,
        )
    else:
        set_state(
            phase,
            detail,
            task=task,
            log_dir=log_dir,
            revision=revision,
            session_id=session_id,
        )
