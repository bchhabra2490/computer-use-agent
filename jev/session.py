"""Per-agent-session Jev coordination (no process-global mutable state).

Uses :mod:`contextvars` so concurrent sessions on different threads/tasks do
not share attempt state. Context values themselves are immutable.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True)
class JevSessionContext:
    """Immutable session state coordinating the fast loop and ``jev_choose``."""

    fast_loop_ran: bool = False
    snapshot_revision: int | None = None
    outcome: str = ""
    fallback_reason: str = ""
    # After a fast-loop attempt, AX re-decide is blocked until revision changes.
    ax_choose_allowed: bool = True

    def after_fast_loop(
        self,
        *,
        snapshot_revision: int | None,
        outcome: str,
        fallback_reason: str = "",
    ) -> JevSessionContext:
        """Record a pre-agent fast-loop attempt; block same-state AX choose."""
        return replace(
            self,
            fast_loop_ran=True,
            snapshot_revision=snapshot_revision,
            outcome=(outcome or "").strip(),
            fallback_reason=(fallback_reason or "").strip(),
            ax_choose_allowed=False,
        )

    def may_call_ax(self, revision: int | None) -> bool:
        """True when ``source=ax`` may call hosted Jev for this UI revision."""
        if not self.fast_loop_ran:
            return True
        if revision is None:
            return False
        if self.snapshot_revision is None:
            return False
        return int(revision) != int(self.snapshot_revision)

    def after_ax_choose(
        self, *, snapshot_revision: int | None, ok: bool
    ) -> JevSessionContext:
        """Record an AX choose attempt (still advisory-only)."""
        if snapshot_revision is None:
            return self
        return replace(
            self,
            snapshot_revision=int(snapshot_revision),
            ax_choose_allowed=False if ok else self.ax_choose_allowed,
            outcome=self.outcome or ("ax_choose_ok" if ok else "ax_choose_blocked"),
        )

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "fast_loop_ran": self.fast_loop_ran,
            "snapshot_revision": self.snapshot_revision,
            "outcome": self.outcome,
            "fallback_reason": self.fallback_reason,
            "ax_choose_allowed": self.ax_choose_allowed,
        }


_jev_session_var: contextvars.ContextVar[JevSessionContext | None] = contextvars.ContextVar(
    "jev_session_context", default=None
)


def get_jev_session() -> JevSessionContext | None:
    return _jev_session_var.get()


def set_jev_session(ctx: JevSessionContext | None) -> contextvars.Token:
    """Bind session context for the current task/thread. Returns reset token."""
    return _jev_session_var.set(ctx)


def reset_jev_session(token: contextvars.Token) -> None:
    _jev_session_var.reset(token)


def update_jev_session(ctx: JevSessionContext) -> None:
    """Replace the bound session context (same ContextVar slot)."""
    _jev_session_var.set(ctx)
