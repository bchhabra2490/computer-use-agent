"""Shadow-mode Jev evaluation — analysis only, never executes desktop actions.

Captures/accepts a UISnapshot, enumerates grounded candidates, calls Jev,
applies the confidence gate for logging, and returns control to the existing
agent path. Active execution lives in :mod:`jev.loop`.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Callable

from jev.actions import (
    enumerate_grounded_actions,
    evaluate_decision_gate,
)
from jev.client import JevClient
from jev.config import JevConfig, load_jev_config
from jev.models import (
    DecisionGateResult,
    GroundedAction,
    JevDecision,
    UISnapshot,
)


@dataclass(frozen=True)
class ShadowEvaluationResult:
    """Outcome of one shadow Jev evaluation (never executed)."""

    status: str
    decision: JevDecision
    candidates: tuple[GroundedAction, ...]
    gate: DecisionGateResult | None = None
    snapshot_revision: int | None = None
    candidate_count: int = 0
    snapshot_ms: float | None = None
    candidate_gen_ms: float | None = None
    would_action_id: str | None = None
    would_description: str = ""
    reason: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "decision": self.decision.to_public_dict(),
            "gate": None if self.gate is None else self.gate.to_public_dict(),
            "snapshot_revision": self.snapshot_revision,
            "candidate_count": self.candidate_count,
            "snapshot_ms": self.snapshot_ms,
            "candidate_gen_ms": self.candidate_gen_ms,
            "would_action_id": self.would_action_id,
            "would_description": self.would_description,
            "reason": self.reason,
            # Never include full candidate list / sensitive UI in the public summary.
        }


def record_jev_decision(
    log: Any | None,
    *,
    step: int,
    result: ShadowEvaluationResult,
    latency_trace_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append a safe per-decision record to TaskLog + optional latency trace."""
    from jev.diagnostics import scrub_for_logs

    decision = result.decision
    usage = (
        None if decision.token_usage is None else decision.token_usage.to_public_dict()
    )
    payload = scrub_for_logs(
        {
            "step": step,
            "snapshot_revision": result.snapshot_revision,
            "candidate_count": result.candidate_count,
            "selected_candidate_id": decision.selected_candidate_id,
            "selected_description": result.would_description,
            "confidence": decision.confidence,
            "selected_probability": decision.selected_probability,
            "second_probability": decision.second_probability,
            "margin": decision.margin,
            "complete_probability": decision.complete_probability,
            "stuck_probability": decision.stuck_probability,
            "jev_latency_ms": decision.latency_ms,
            "snapshot_ms": result.snapshot_ms,
            "candidate_gen_ms": result.candidate_gen_ms,
            "token_usage": usage,
            "gate": None if result.gate is None else result.gate.to_public_dict(),
            "status": result.status,
            "fallback_reason": decision.fallback_reason or result.reason,
            "model": decision.model,
            **(extra or {}),
        }
    )
    summary = (
        f"jev {result.status} step={step} "
        f"cand={decision.selected_candidate_id or '-'} "
        f"conf={decision.confidence:.2f} margin={decision.margin:.2f}"
    )
    if log is not None:
        try:
            log.record("jev_decision", summary[:200], payload)
        except Exception:
            pass
    if latency_trace_id:
        try:
            from latency_report import mark

            mark(
                latency_trace_id,
                "jev_decision",
                metadata={
                    "status": result.status,
                    "confidence": decision.confidence,
                    "latency_ms": decision.latency_ms,
                    "snapshot_ms": result.snapshot_ms,
                    "candidate_gen_ms": result.candidate_gen_ms,
                },
            )
        except Exception:
            pass


def run_shadow_evaluation(
    *,
    goal: str,
    snapshot: UISnapshot | None = None,
    capture_snapshot: Callable[[], UISnapshot] | None = None,
    config: JevConfig | None = None,
    client: JevClient | None = None,
    recent_actions: Sequence[GroundedAction] | None = None,
    step: int = 0,
    subgoal: str = "",
    url: str = "",
    log: Any | None = None,
    latency_trace_id: str | None = None,
    executor: Callable[..., Any] | None = None,
) -> ShadowEvaluationResult:
    """Run one shadow Jev decision. Never invokes the desktop executor.

    ``executor`` is accepted only so tests can assert it is unused.
    """
    cfg = config or load_jev_config()
    snapshot_ms = None
    if snapshot is None:
        if capture_snapshot is None:
            decision = JevDecision(
                error="snapshot unavailable",
                fallback_reason="snapshot unavailable",
            )
            result = ShadowEvaluationResult(
                status="unavailable",
                decision=decision,
                candidates=(),
                reason="snapshot unavailable",
            )
            record_jev_decision(
                log, step=step, result=result, latency_trace_id=latency_trace_id
            )
            return result
        started = time.perf_counter()
        snapshot = capture_snapshot()
        snapshot_ms = (time.perf_counter() - started) * 1000.0

    if not cfg.fast_loop:
        decision = JevDecision(error="jev disabled", fallback_reason="jev disabled")
        result = ShadowEvaluationResult(
            status="unavailable",
            decision=decision,
            candidates=(),
            snapshot_revision=snapshot.revision,
            snapshot_ms=snapshot_ms,
            reason="jev disabled",
        )
        record_jev_decision(
            log, step=step, result=result, latency_trace_id=latency_trace_id
        )
        return result

    if not cfg.shadow_mode:
        decision = JevDecision(
            error="shadow mode required",
            fallback_reason="use jev.loop.run_jev_fast_loop for active execution",
        )
        result = ShadowEvaluationResult(
            status="unavailable",
            decision=decision,
            candidates=(),
            snapshot_revision=snapshot.revision,
            snapshot_ms=snapshot_ms,
            reason="active execution uses jev.loop",
        )
        record_jev_decision(
            log, step=step, result=result, latency_trace_id=latency_trace_id
        )
        return result

    started = time.perf_counter()
    candidates = enumerate_grounded_actions(
        snapshot, goal, recent_actions=recent_actions, config=cfg
    )
    candidate_gen_ms = (time.perf_counter() - started) * 1000.0

    owns_client = client is None
    jev = client or JevClient(cfg)
    try:
        decision = jev.decide(
            goal=goal,
            snapshot=snapshot,
            candidates=candidates,
            recent_actions=recent_actions,
            step=step,
            subgoal=subgoal,
            url=url,
        )
    finally:
        if owns_client:
            jev.close()

    gate = None
    status = "fallback"
    would_id = decision.selected_candidate_id
    would_desc = ""
    if decision.error:
        status = (
            "unavailable"
            if "unavailable" in (decision.error or "")
            or decision.error
            in {
                "jev disabled",
                "api key unavailable",
                "typesafe-sdk unavailable",
                "request timeout",
            }
            or decision.error.startswith("provider error")
            else "rejected"
        )
        reason = decision.fallback_reason or decision.error or ""
    else:
        gate = evaluate_decision_gate(
            decision, candidates, cfg, confirmed=False, goal=goal
        )
        by_id = {c.action_id: c for c in candidates}
        chosen = by_id.get(decision.selected_candidate_id or "")
        if chosen is not None:
            would_desc = chosen.description
        if gate.requires_verification:
            status = "shadowed"
            reason = gate.reason
        elif gate.allowed:
            status = "shadowed"
            reason = "would execute (shadow only)"
        else:
            status = (
                "rejected"
                if "unknown" in gate.reason or "unsafe" in gate.reason
                else "fallback"
            )
            reason = gate.reason

    # Hard guarantee: never execute in shadow mode.
    if executor is not None:
        # Intentionally unused — shadow analysis must not touch the desktop.
        pass

    result = ShadowEvaluationResult(
        status=status,
        decision=decision,
        candidates=tuple(candidates),
        gate=gate,
        snapshot_revision=snapshot.revision,
        candidate_count=len(candidates),
        snapshot_ms=snapshot_ms,
        candidate_gen_ms=candidate_gen_ms,
        would_action_id=would_id,
        would_description=would_desc,
        reason=reason,
    )
    record_jev_decision(
        log, step=step, result=result, latency_trace_id=latency_trace_id
    )
    return result


def shadow_evaluation_enabled(config: JevConfig | None = None) -> bool:
    """True when callers may invoke :func:`run_shadow_evaluation`."""
    cfg = config or load_jev_config()
    return bool(cfg.fast_loop and cfg.shadow_mode)
