"""Active one-action-at-a-time Jev fast loop with fallback to the vision agent.

Shadow mode records a single decision and returns without executing.
Active mode validates freshness, executes exactly one grounded action per
cycle, waits for a bounded UI revision change, and falls back on gates,
stuck/no-progress, or interrupt signals. Never treats fallback as success.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from jev.actions import (
    OP_DONE,
    OP_ESCALATE,
    OP_TYPE,
    OP_WAIT,
    action_requires_confirmation,
    classify_jev_input_privacy,
    enumerate_grounded_actions,
    evaluate_decision_gate,
    execute_grounded_action,
    plan_execution,
    validate_grounded_action,
)
from jev.client import JevClient
from jev.config import JevConfig, load_jev_config
from jev.diagnostics import JevSessionStats, StepTimer, record_jev_session_summary
from jev.models import (
    DecisionGateResult,
    GroundedAction,
    JevDecision,
    JevGateResult,
    JevGateVerdict,
    JevLoopResult,
    JevLoopStatus,
    UISnapshot,
)
from jev.shadow import (
    ShadowEvaluationResult,
    record_jev_decision,
    run_shadow_evaluation,
)

# Bounded polling — not continuous / not 60 Hz.
_STATE_POLL_SECONDS = 0.05
_STATE_DEADLINE_SECONDS = 1.5
_MAX_FRESHNESS_RETRIES = 2
_SUPPORTED_ACTIVE_OPS = frozenset(
    {
        "click_element",
        "focus_element",
        "type_task_text",
        "press_enter",
        "press_escape",
        "press_tab",
        "scroll_down",
        "scroll_up",
        "wait",
    }
)


@dataclass(frozen=True)
class WaitOutcome:
    """Result of waiting for a meaningful UI revision change."""

    changed: bool
    wait_ms: float
    before_revision: int
    after_revision: int
    snapshot: UISnapshot | None = None
    interrupted: bool = False


def action_signature(action: GroundedAction) -> tuple[Any, ...]:
    """Stable key for repeated-action / no-progress detection."""
    args = dict(action.arguments or {})
    op = args.get("op")
    return (
        op,
        action.element_id,
        action.kind.value if hasattr(action.kind, "value") else str(action.kind),
        args.get("text"),
        tuple(args.get("keys") or ()),
        args.get("scroll_x"),
        args.get("scroll_y"),
        args.get("ms"),
    )


def format_jev_handoff_prompt(
    *,
    original_task: str,
    result: JevLoopResult,
    mode: str = "fallback",
) -> str:
    """Build a concise handoff for the existing generative agent."""
    lines = [
        original_task.strip(),
        "",
        f"[Jev handoff — {mode}]",
        f"Reason: {result.reason or result.status.value}",
        f"Jev steps: {result.steps}",
    ]
    if result.executed_actions:
        lines.append("Already executed by Jev (do not repeat):")
        for i, action in enumerate(result.executed_actions, 1):
            effect = ""
            if i - 1 < len(result.observed_effects):
                effect = f" → {result.observed_effects[i - 1]}"
            lines.append(f"  {i}. {action.description or action.action_id}{effect}")
    else:
        lines.append("No Jev actions were executed.")
    if result.observed_effects and not result.executed_actions:
        lines.append("Observed effects: " + "; ".join(result.observed_effects))
    snap = result.latest_snapshot_public
    if snap:
        lines.append(
            "Latest structured UI state: "
            f"app={snap.get('app_name')!r} window={snap.get('window_title')!r} "
            f"revision={snap.get('revision')} elements={len(snap.get('elements') or [])} "
            f"error={snap.get('error') or 'none'}"
        )
        # Compact element hints (labels only) — keep prompt bounded.
        labels = []
        for el in (snap.get("elements") or [])[:12]:
            lab = (el.get("label") or "").strip()
            role = (el.get("role") or "").strip()
            if lab:
                labels.append(f"{role}:{lab}" if role else lab)
        if labels:
            lines.append("Visible controls (sample): " + "; ".join(labels))
    if mode == "verification":
        lines.append(
            "Jev believes the task may be complete. Verify against the goal "
            "using the screenshot and tools; only mark_done if truly done. "
            "Do not redo completed Jev actions."
        )
    else:
        lines.append(
            "Continue from this state with the vision computer-use path. "
            "Do not restart the task from scratch or repeat completed Jev actions."
        )
    return "\n".join(lines)


def wait_for_revision_change(
    *,
    before: UISnapshot,
    capture_snapshot: Callable[[], UISnapshot],
    deadline_seconds: float = _STATE_DEADLINE_SECONDS,
    poll_seconds: float = _STATE_POLL_SECONDS,
    sleep_fn: Callable[[float], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    clock: Callable[[], float] | None = None,
) -> WaitOutcome:
    """Poll structured snapshots until revision changes or deadline hits."""
    sleep = time.sleep if sleep_fn is None else sleep_fn
    now = time.monotonic if clock is None else clock
    started = now()
    deadline = started + max(0.0, float(deadline_seconds))
    last = before
    while True:
        if should_stop is not None and should_stop():
            return WaitOutcome(
                changed=False,
                wait_ms=(now() - started) * 1000.0,
                before_revision=before.revision,
                after_revision=last.revision,
                snapshot=last,
                interrupted=True,
            )
        if now() >= deadline:
            return WaitOutcome(
                changed=False,
                wait_ms=(now() - started) * 1000.0,
                before_revision=before.revision,
                after_revision=last.revision,
                snapshot=last,
                interrupted=False,
            )
        sleep(max(0.0, float(poll_seconds)))
        last = capture_snapshot()
        if last.revision != before.revision:
            return WaitOutcome(
                changed=True,
                wait_ms=(now() - started) * 1000.0,
                before_revision=before.revision,
                after_revision=last.revision,
                snapshot=last,
                interrupted=False,
            )


def _enable_gate(cfg: JevConfig) -> JevGateResult:
    if not cfg.fast_loop:
        return JevGateResult(
            verdict=JevGateVerdict.DISABLED,
            reason="JEV_FAST_LOOP disabled",
            config_enabled=False,
        )
    if cfg.shadow_mode:
        return JevGateResult(
            verdict=JevGateVerdict.SHADOW,
            reason=(
                "shadow mode"
                if cfg.has_api_key
                else "shadow mode (api key unavailable)"
            ),
            shadow=True,
            config_enabled=True,
        )
    if not cfg.has_api_key:
        return JevGateResult(
            verdict=JevGateVerdict.FALLBACK,
            reason="api key unavailable",
            config_enabled=True,
        )
    return JevGateResult(
        verdict=JevGateVerdict.ALLOW,
        reason="active fast loop",
        shadow=False,
        config_enabled=True,
    )


def _snapshot_usable(snapshot: UISnapshot) -> bool:
    if snapshot.error:
        return False
    return bool(snapshot.elements) or snapshot.handle_count > 0


def _op(action: GroundedAction) -> str:
    return str(action.arguments.get("op") or "")


def _unsupported_active(action: GroundedAction) -> str | None:
    op = _op(action)
    if op not in _SUPPORTED_ACTIVE_OPS:
        return f"unsupported active op {op or action.kind}"
    if action.sensitive:
        return "secure / sensitive typing blocked"
    if op == OP_TYPE:
        text = str(action.arguments.get("text") or "")
        if not text.strip():
            return "free-form text cannot be deterministically grounded"
    return None


def _record_active(
    log: Any | None,
    *,
    step: int,
    status: str,
    decision: JevDecision,
    gate: DecisionGateResult | None,
    snapshot: UISnapshot | None,
    candidates: Sequence[GroundedAction],
    reason: str,
    would_desc: str = "",
    latency_trace_id: str | None = None,
    wait_ms: float | None = None,
    effect: str | None = None,
    snapshot_ms: float | None = None,
    candidate_gen_ms: float | None = None,
    gate_ms: float | None = None,
    freshness_ms: float | None = None,
    execute_ms: float | None = None,
    step_total_ms: float | None = None,
) -> None:
    result = ShadowEvaluationResult(
        status=status,
        decision=decision,
        candidates=tuple(candidates),
        gate=gate,
        snapshot_revision=None if snapshot is None else snapshot.revision,
        candidate_count=len(candidates),
        snapshot_ms=snapshot_ms,
        candidate_gen_ms=candidate_gen_ms,
        would_action_id=decision.selected_candidate_id,
        would_description=would_desc,
        reason=reason,
    )
    record_jev_decision(
        log,
        step=step,
        result=result,
        latency_trace_id=latency_trace_id,
        extra={
            "gate_ms": gate_ms,
            "freshness_ms": freshness_ms,
            "execute_ms": execute_ms,
            "wait_ms": wait_ms,
            "step_total_ms": step_total_ms,
            "effect": effect,
        },
    )
    if log is not None and (
        wait_ms is not None or effect is not None or step_total_ms is not None
    ):
        try:
            from jev.diagnostics import scrub_for_logs

            log.record(
                "jev_step",
                f"jev {status} effect={effect or '-'} wait_ms={wait_ms}",
                scrub_for_logs(
                    {
                        "status": status,
                        "wait_ms": wait_ms,
                        "effect": effect,
                        "reason": reason,
                        "step": step,
                        "snapshot_ms": snapshot_ms,
                        "candidate_gen_ms": candidate_gen_ms,
                        "jev_latency_ms": decision.latency_ms,
                        "gate_ms": gate_ms,
                        "freshness_ms": freshness_ms,
                        "execute_ms": execute_ms,
                        "step_total_ms": step_total_ms,
                    }
                ),
            )
        except Exception:
            pass


def run_jev_fast_loop(
    *,
    task: str,
    original_task: str | None = None,
    subgoal: str = "",
    constraints: str = "",
    config: JevConfig | None = None,
    client: JevClient | None = None,
    desktop: Any | None = None,
    log: Any | None = None,
    agent_id: str | None = None,
    auto: bool = False,
    voice: bool = False,
    llm_client: Any | None = None,
    confirm_fn: Callable[..., bool] | None = None,
    capture_snapshot: Callable[[], UISnapshot] | None = None,
    ax_perform: Callable[[Any, str], bool] | None = None,
    execute_fn: Callable[..., dict[str, Any]] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
    should_stop: Callable[[], bool] | None = None,
    latency_trace_id: str | None = None,
    url: str = "",
    state_deadline_seconds: float = _STATE_DEADLINE_SECONDS,
    state_poll_seconds: float = _STATE_POLL_SECONDS,
) -> JevLoopResult:
    """Run the Jev fast loop (shadow or active). Never claims task completion."""
    cfg = config or load_jev_config()
    goal = (task or "").strip()
    original = (original_task or task or "").strip()
    if constraints:
        goal = f"{goal}\nConstraints: {constraints.strip()}"

    gate = _enable_gate(cfg)
    if gate.verdict is JevGateVerdict.DISABLED:
        return JevLoopResult(
            status=JevLoopStatus.DISABLED,
            gate=gate,
            reason=gate.reason,
        )

    privacy = classify_jev_input_privacy(goal, subgoal)
    if not privacy.allowed:
        # Never send secret-bearing goals to TypeSafe. Leave fallback_prompt
        # empty so the vision agent keeps the original task unchanged.
        return JevLoopResult(
            status=JevLoopStatus.FALLBACK,
            gate=gate,
            reason=privacy.reason,
            fallback_prompt="",
        )

    def _default_capture() -> UISnapshot:
        from accessibility import capture_ui_snapshot

        return capture_ui_snapshot()

    capture = capture_snapshot or _default_capture

    def _default_ax(handle: Any, name: str) -> bool:
        from accessibility import ax_perform_action

        return ax_perform_action(handle, name)

    ax_fn = ax_perform if ax_perform is not None else _default_ax
    executor = execute_fn or execute_grounded_action

    def _interrupted() -> bool:
        if should_stop is not None and should_stop():
            return True
        if agent_id is not None:
            try:
                from status_control import consume_mark_done, mark_done_pending

                if mark_done_pending(agent_id):
                    consume_mark_done(agent_id)
                    return True
            except Exception:
                pass
        return False

    # --- Shadow: one evaluation, zero execution ---
    if cfg.shadow_mode or gate.verdict is JevGateVerdict.SHADOW:
        shadow = run_shadow_evaluation(
            goal=goal,
            capture_snapshot=capture,
            config=cfg,
            client=client,
            step=0,
            subgoal=subgoal,
            url=url,
            log=log,
            latency_trace_id=latency_trace_id,
            executor=None,
        )
        stats = JevSessionStats(
            mode="shadow",
            decisions=1,
            outcome=JevLoopStatus.SHADOW_COMPLETE.value,
            outcome_reason=shadow.reason or "shadow evaluation complete",
        )
        if shadow.status in {"fallback", "rejected", "unavailable"}:
            stats.fallbacks = 1
        record_jev_session_summary(log, stats, latency_trace_id=latency_trace_id)
        return JevLoopResult(
            status=JevLoopStatus.SHADOW_COMPLETE,
            steps=1,
            gate=gate,
            decision=shadow.decision,
            actions=shadow.candidates,
            reason=shadow.reason
            or "shadow evaluation complete; vision agent continues",
            snapshot_revision=shadow.snapshot_revision,
            fallback_prompt="",
        )

    if gate.verdict is not JevGateVerdict.ALLOW:
        stats = JevSessionStats(
            mode="active",
            outcome=JevLoopStatus.UNAVAILABLE.value,
            outcome_reason=gate.reason,
            fallbacks=1,
        )
        record_jev_session_summary(log, stats, latency_trace_id=latency_trace_id)
        return JevLoopResult(
            status=JevLoopStatus.UNAVAILABLE,
            gate=gate,
            reason=gate.reason,
            fallback_prompt=format_jev_handoff_prompt(
                original_task=original,
                result=JevLoopResult(
                    status=JevLoopStatus.UNAVAILABLE,
                    gate=gate,
                    reason=gate.reason,
                ),
            ),
        )

    owns_client = client is None
    jev = client or JevClient(cfg)
    executed: list[GroundedAction] = []
    effects: list[str] = []
    recent: list[GroundedAction] = []
    last_decision: JevDecision | None = None
    last_snapshot: UISnapshot | None = None
    wait_ms_total = 0.0
    consecutive_failures = 0
    consecutive_no_effect = 0
    last_sig: tuple[Any, ...] | None = None
    last_sig_revision: int | None = None
    steps = 0
    stats = JevSessionStats(mode="active")
    loop_started = time.perf_counter() if clock is None else clock()

    def _finish(
        status: JevLoopStatus,
        reason: str,
        *,
        mode: str = "fallback",
        decision: JevDecision | None = None,
        actions: Sequence[GroundedAction] = (),
    ) -> JevLoopResult:
        snap_public = None if last_snapshot is None else last_snapshot.to_public_dict()
        handoff_mode = (
            "verification"
            if status is JevLoopStatus.COMPLETED_PENDING_VERIFICATION
            else mode
        )
        now = time.perf_counter() if clock is None else clock()
        stats.loop_wall_ms = (now - loop_started) * 1000.0
        stats.wait_ms_total = wait_ms_total
        stats.executed = len(executed)
        stats.outcome = status.value
        stats.outcome_reason = reason
        if status in {
            JevLoopStatus.FALLBACK,
            JevLoopStatus.MAX_STEPS,
            JevLoopStatus.UNAVAILABLE,
        }:
            stats.fallbacks = max(stats.fallbacks, 1)
        record_jev_session_summary(log, stats, latency_trace_id=latency_trace_id)
        draft = JevLoopResult(
            status=status,
            steps=steps,
            gate=gate,
            decision=decision or last_decision,
            actions=tuple(actions),
            executed_actions=tuple(executed),
            observed_effects=tuple(effects),
            reason=reason,
            snapshot_revision=None if last_snapshot is None else last_snapshot.revision,
            latest_snapshot_public=snap_public,
            wait_ms_total=wait_ms_total,
            fallback_prompt="",
        )
        prompt = ""
        if status in {
            JevLoopStatus.FALLBACK,
            JevLoopStatus.MAX_STEPS,
            JevLoopStatus.UNAVAILABLE,
            JevLoopStatus.COMPLETED_PENDING_VERIFICATION,
        }:
            prompt = format_jev_handoff_prompt(
                original_task=original,
                result=draft,
                mode=handoff_mode,
            )
        return JevLoopResult(
            status=status,
            steps=steps,
            gate=gate,
            decision=decision or last_decision,
            actions=tuple(actions),
            executed_actions=tuple(executed),
            observed_effects=tuple(effects),
            reason=reason,
            snapshot_revision=None if last_snapshot is None else last_snapshot.revision,
            latest_snapshot_public=snap_public,
            wait_ms_total=wait_ms_total,
            fallback_prompt=prompt,
        )

    try:
        while steps < cfg.max_steps:
            if _interrupted():
                return _finish(JevLoopStatus.ABORTED, "stop / mark-done requested")

            timer = StepTimer(clock)
            try:
                snapshot = capture()
            except Exception as exc:
                return _finish(
                    JevLoopStatus.FALLBACK,
                    f"snapshot capture failed: {type(exc).__name__}",
                )
            timer.mark("snapshot")
            snapshot_ms = (timer.marks["snapshot"] - timer.t0) * 1000.0
            last_snapshot = snapshot

            if not _snapshot_usable(snapshot):
                stats.fallbacks += 1
                return _finish(
                    JevLoopStatus.FALLBACK,
                    snapshot.error or "AX snapshot empty or unusable",
                )

            candidates = enumerate_grounded_actions(
                snapshot, goal, recent_actions=recent, config=cfg
            )
            timer.mark("candidates")
            candidate_gen_ms = timer.span_ms("snapshot", "candidates")
            try:
                decision = jev.decide(
                    goal=goal,
                    snapshot=snapshot,
                    candidates=candidates,
                    recent_actions=recent,
                    step=steps,
                    subgoal=subgoal,
                    url=url,
                )
            except Exception as exc:
                consecutive_failures += 1
                stats.provider_failures += 1
                stats.decisions += 1
                last_decision = JevDecision(
                    error=str(exc),
                    fallback_reason=f"provider error: {type(exc).__name__}",
                )
                if consecutive_failures > cfg.max_consecutive_failures:
                    return _finish(
                        JevLoopStatus.FALLBACK,
                        "consecutive provider failures limit reached",
                        decision=last_decision,
                        actions=candidates,
                    )
                continue

            timer.mark("decide")
            stats.decisions += 1
            last_decision = decision
            if decision.error:
                consecutive_failures += 1
                stats.provider_failures += 1
                _record_active(
                    log,
                    step=steps,
                    status="unavailable",
                    decision=decision,
                    gate=None,
                    snapshot=snapshot,
                    candidates=candidates,
                    reason=decision.fallback_reason or decision.error,
                    latency_trace_id=latency_trace_id,
                    snapshot_ms=snapshot_ms,
                    candidate_gen_ms=candidate_gen_ms,
                    step_total_ms=timer.ms_since(),
                )
                if consecutive_failures > cfg.max_consecutive_failures:
                    return _finish(
                        (
                            JevLoopStatus.UNAVAILABLE
                            if "unavailable" in (decision.error or "")
                            else JevLoopStatus.FALLBACK
                        ),
                        decision.fallback_reason or decision.error,
                        decision=decision,
                        actions=candidates,
                    )
                continue
            consecutive_failures = 0

            gate_result = evaluate_decision_gate(
                decision,
                candidates,
                cfg,
                confirmed=False,
                steps_used=steps,
                goal=goal,
            )
            timer.mark("gate")
            gate_ms = timer.span_ms("decide", "gate")
            chosen = gate_result.action
            if chosen is None and decision.selected_candidate_id:
                by_id = {c.action_id: c for c in candidates}
                chosen = by_id.get(decision.selected_candidate_id)

            if gate_result.requires_verification or (
                chosen is not None and _op(chosen) == OP_DONE
            ):
                _record_active(
                    log,
                    step=steps,
                    status="pending_verification",
                    decision=decision,
                    gate=gate_result,
                    snapshot=snapshot,
                    candidates=candidates,
                    reason=gate_result.reason,
                    would_desc="" if chosen is None else chosen.description,
                    latency_trace_id=latency_trace_id,
                    snapshot_ms=snapshot_ms,
                    candidate_gen_ms=candidate_gen_ms,
                    gate_ms=gate_ms,
                    step_total_ms=timer.ms_since(),
                )
                steps += 1
                return _finish(
                    JevLoopStatus.COMPLETED_PENDING_VERIFICATION,
                    gate_result.reason or "completion requires verification",
                    decision=decision,
                    actions=candidates,
                )

            # Confirmation phase — must run before generic fallback rejection.
            if gate_result.allowed_pending_confirmation and chosen is not None:
                stats.safety_rejects += 0  # pending, not yet a reject
                confirmed = bool(auto)
                if not auto:
                    if confirm_fn is None:
                        stats.safety_rejects += 1
                        return _finish(
                            JevLoopStatus.FALLBACK,
                            "safety confirmation cannot be resolved",
                            decision=decision,
                            actions=candidates,
                        )
                    # Safe description only — never sensitive arguments.
                    prompt_label = chosen.description or chosen.action_id
                    try:
                        confirmed = bool(
                            confirm_fn(
                                [prompt_label],
                                client=llm_client,
                                voice=voice,
                            )
                        )
                    except SystemExit:
                        raise
                    except Exception:
                        confirmed = False
                    if not confirmed:
                        stats.safety_rejects += 1
                        return _finish(
                            JevLoopStatus.FALLBACK,
                            "safety confirmation declined or unresolved",
                            decision=decision,
                            actions=candidates,
                        )
                gate_result = evaluate_decision_gate(
                    decision,
                    candidates,
                    cfg,
                    confirmed=True,
                    steps_used=steps,
                    goal=goal,
                )
                timer.mark("gate")
                gate_ms = timer.span_ms("decide", "gate")
                chosen = gate_result.action or chosen
                if not gate_result.allowed:
                    stats.fallbacks += 1
                    return _finish(
                        JevLoopStatus.FALLBACK,
                        gate_result.reason or "post-confirmation gate rejected",
                        decision=decision,
                        actions=candidates,
                    )

            elif not gate_result.allowed or chosen is None:
                stats.fallbacks += 1
                if gate_result.requires_confirmation or "confirmation" in (
                    gate_result.reason or ""
                ):
                    stats.safety_rejects += 1
                _record_active(
                    log,
                    step=steps,
                    status="fallback",
                    decision=decision,
                    gate=gate_result,
                    snapshot=snapshot,
                    candidates=candidates,
                    reason=gate_result.reason,
                    would_desc="" if chosen is None else chosen.description,
                    latency_trace_id=latency_trace_id,
                    snapshot_ms=snapshot_ms,
                    candidate_gen_ms=candidate_gen_ms,
                    gate_ms=gate_ms,
                    step_total_ms=timer.ms_since(),
                )
                return _finish(
                    JevLoopStatus.FALLBACK,
                    gate_result.reason or "gate rejected",
                    decision=decision,
                    actions=candidates,
                )

            if _op(chosen) == OP_ESCALATE:
                return _finish(
                    JevLoopStatus.FALLBACK,
                    "escalate to vision agent",
                    decision=decision,
                    actions=candidates,
                )

            unsupported = _unsupported_active(chosen)
            if unsupported:
                return _finish(
                    JevLoopStatus.FALLBACK,
                    unsupported,
                    decision=decision,
                    actions=candidates,
                )

            # Dynamic confirmation (label/task) even if the grounded flag was clear.
            needs_confirm = bool(chosen.requires_confirmation)
            if not needs_confirm:
                el = None
                if chosen.element_id:
                    el = next(
                        (e for e in snapshot.elements if e.id == chosen.element_id),
                        None,
                    )
                needs_confirm = action_requires_confirmation(
                    op=_op(chosen),
                    element=el,
                    task=goal,
                    text=str(chosen.arguments.get("text") or ""),
                )
            if needs_confirm and not chosen.requires_confirmation:
                # Late classification — treat like needs-confirmation.
                confirmed = bool(auto)
                if not auto:
                    if confirm_fn is None:
                        stats.safety_rejects += 1
                        return _finish(
                            JevLoopStatus.FALLBACK,
                            "safety confirmation cannot be resolved",
                            decision=decision,
                            actions=candidates,
                        )
                    try:
                        confirmed = bool(
                            confirm_fn(
                                [chosen.description or chosen.action_id],
                                client=llm_client,
                                voice=voice,
                            )
                        )
                    except SystemExit:
                        raise
                    except Exception:
                        confirmed = False
                    if not confirmed:
                        stats.safety_rejects += 1
                        return _finish(
                            JevLoopStatus.FALLBACK,
                            "safety confirmation declined or unresolved",
                            decision=decision,
                            actions=candidates,
                        )

            # Freshness: always recapture immediately before execution (never
            # execute against the decision-time snapshot alone).
            timer.mark("freshness_start")
            try:
                fresh_snap = capture()
            except Exception as exc:
                return _finish(
                    JevLoopStatus.FALLBACK,
                    f"freshness recapture failed: {type(exc).__name__}",
                    decision=decision,
                    actions=candidates,
                )
            last_snapshot = fresh_snap
            validation = validate_grounded_action(chosen, snapshot, fresh_snap)
            freshness_tries = 0
            while not validation.ok and freshness_tries < _MAX_FRESHNESS_RETRIES:
                freshness_tries += 1
                if _interrupted():
                    return _finish(JevLoopStatus.ABORTED, "stop / mark-done requested")
                try:
                    fresh_snap = capture()
                except Exception as exc:
                    return _finish(
                        JevLoopStatus.FALLBACK,
                        f"freshness recapture failed: {type(exc).__name__}",
                        decision=decision,
                        actions=candidates,
                    )
                last_snapshot = fresh_snap
                validation = validate_grounded_action(chosen, snapshot, fresh_snap)
                if validation.ok:
                    break

            timer.mark("freshness")
            freshness_ms = timer.span_ms("freshness_start", "freshness")

            if not validation.ok:
                stats.freshness_rejects += 1
                _record_active(
                    log,
                    step=steps,
                    status="stale",
                    decision=decision,
                    gate=gate_result,
                    snapshot=fresh_snap,
                    candidates=candidates,
                    reason=f"freshness validation failed: {validation.reason}",
                    latency_trace_id=latency_trace_id,
                    snapshot_ms=snapshot_ms,
                    candidate_gen_ms=candidate_gen_ms,
                    gate_ms=gate_ms,
                    freshness_ms=freshness_ms,
                    step_total_ms=timer.ms_since(),
                )
                # Recapture path: do not execute; count as a soft retry then fallback.
                consecutive_no_effect += 1
                if (
                    consecutive_no_effect >= 2
                    or freshness_tries >= _MAX_FRESHNESS_RETRIES
                ):
                    return _finish(
                        JevLoopStatus.FALLBACK,
                        f"freshness validation repeatedly failed: {validation.reason}",
                        decision=decision,
                        actions=candidates,
                    )
                continue

            # If confirmation targeted a specific element and soft-match rebound
            # to a different control, prior confirmation is invalid.
            if (
                chosen.requires_confirmation
                and chosen.element_id
                and validation.element is not None
                and validation.element.id != chosen.element_id
            ):
                return _finish(
                    JevLoopStatus.FALLBACK,
                    "action changed after confirmation; confirmation invalidated",
                    decision=decision,
                    actions=candidates,
                )
            # Repeated identical action against unchanged revision → fallback.
            sig = action_signature(chosen)
            if (
                last_sig is not None
                and sig == last_sig
                and last_sig_revision is not None
                and fresh_snap.revision == last_sig_revision
            ):
                stats.repeated_action += 1
                return _finish(
                    JevLoopStatus.FALLBACK,
                    "same action repeats against unchanged state",
                    decision=decision,
                    actions=candidates,
                )

            plan = plan_execution(chosen, fresh_snap, validation=validation)
            if plan.method == "unavailable":
                return _finish(
                    JevLoopStatus.FALLBACK,
                    plan.notes or "action unsupported for execution",
                    decision=decision,
                    actions=candidates,
                )

            if _interrupted():
                return _finish(JevLoopStatus.ABORTED, "stop / mark-done requested")

            before_revision = fresh_snap.revision
            timer.mark("exec_start")
            try:
                exec_out = executor(
                    chosen,
                    fresh_snap,
                    desktop=desktop,
                    validation=validation,
                    ax_perform=ax_fn,
                    dry_run=False,
                    should_stop=_interrupted,
                    coords_are_screen=True,
                )
            except Exception as exc:
                # pyautogui fail-safe / ActionStopped
                name = type(exc).__name__
                if (
                    name in {"ActionStopped", "FailSafeException"}
                    or "stopped" in str(exc).lower()
                ):
                    return _finish(JevLoopStatus.ABORTED, f"interrupted: {name}")
                return _finish(
                    JevLoopStatus.FALLBACK,
                    f"execution failed: {name}",
                    decision=decision,
                    actions=candidates,
                )
            timer.mark("exec")
            execute_ms = timer.span_ms("exec_start", "exec")

            if not exec_out.get("ok"):
                return _finish(
                    JevLoopStatus.FALLBACK,
                    f"execution failed: {exec_out.get('reason') or 'unknown'}",
                    decision=decision,
                    actions=candidates,
                )

            executed.append(chosen)
            recent.append(chosen)
            if len(recent) > 8:
                recent = recent[-8:]
            steps += 1
            last_sig = sig
            last_sig_revision = before_revision
            if stats.time_to_first_action_ms is None:
                now = time.perf_counter() if clock is None else clock()
                stats.time_to_first_action_ms = (now - loop_started) * 1000.0
                if latency_trace_id:
                    try:
                        from latency_report import mark

                        mark(
                            latency_trace_id,
                            "jev_first_action",
                            metadata={"step": steps, "execute_ms": execute_ms},
                        )
                        mark(latency_trace_id, "first_computer_action")
                    except Exception:
                        pass

            # Wait actions already slept; treat as intentional no structural change.
            if _op(chosen) == OP_WAIT:
                effects.append("waited")
                consecutive_no_effect = 0
                wait_outcome = WaitOutcome(
                    changed=False,
                    wait_ms=float(chosen.arguments.get("ms") or 500),
                    before_revision=before_revision,
                    after_revision=before_revision,
                    snapshot=fresh_snap,
                )
                wait_ms_total += wait_outcome.wait_ms
                last_snapshot = fresh_snap
                _record_active(
                    log,
                    step=steps,
                    status="executed",
                    decision=decision,
                    gate=gate_result,
                    snapshot=fresh_snap,
                    candidates=candidates,
                    reason="wait",
                    would_desc=chosen.description,
                    latency_trace_id=latency_trace_id,
                    wait_ms=wait_outcome.wait_ms,
                    effect="waited",
                    snapshot_ms=snapshot_ms,
                    candidate_gen_ms=candidate_gen_ms,
                    gate_ms=gate_ms,
                    freshness_ms=freshness_ms,
                    execute_ms=execute_ms,
                    step_total_ms=timer.ms_since(),
                )
                stats.note_timing(
                    snapshot_ms=snapshot_ms,
                    candidate_gen_ms=candidate_gen_ms,
                    jev_latency_ms=decision.latency_ms,
                    gate_ms=gate_ms,
                    freshness_ms=freshness_ms,
                    execute_ms=execute_ms,
                    wait_ms=wait_outcome.wait_ms,
                    step_total_ms=timer.ms_since(),
                )
                continue

            wait_outcome = wait_for_revision_change(
                before=fresh_snap,
                capture_snapshot=capture,
                deadline_seconds=state_deadline_seconds,
                poll_seconds=state_poll_seconds,
                sleep_fn=sleep_fn,
                should_stop=_interrupted,
                clock=clock,
            )
            wait_ms_total += wait_outcome.wait_ms
            if wait_outcome.interrupted:
                effects.append("interrupted_during_wait")
                return _finish(JevLoopStatus.ABORTED, "stop / mark-done during wait")

            if wait_outcome.snapshot is not None:
                last_snapshot = wait_outcome.snapshot

            if wait_outcome.changed:
                effect = (
                    f"revision {wait_outcome.before_revision}"
                    f"→{wait_outcome.after_revision}"
                )
                effects.append(effect)
                consecutive_no_effect = 0
                last_sig_revision = wait_outcome.after_revision
            else:
                effects.append("no_observable_effect")
                consecutive_no_effect += 1
                stats.no_effect += 1
                _record_active(
                    log,
                    step=steps,
                    status="no_effect",
                    decision=decision,
                    gate=gate_result,
                    snapshot=last_snapshot,
                    candidates=candidates,
                    reason="no meaningful state change",
                    would_desc=chosen.description,
                    latency_trace_id=latency_trace_id,
                    wait_ms=wait_outcome.wait_ms,
                    effect="no_observable_effect",
                    snapshot_ms=snapshot_ms,
                    candidate_gen_ms=candidate_gen_ms,
                    gate_ms=gate_ms,
                    freshness_ms=freshness_ms,
                    execute_ms=execute_ms,
                    step_total_ms=timer.ms_since(),
                )
                if consecutive_no_effect >= 2:
                    return _finish(
                        JevLoopStatus.FALLBACK,
                        "two consecutive actions produced no meaningful state change",
                        decision=decision,
                        actions=candidates,
                    )
                continue

            _record_active(
                log,
                step=steps,
                status="executed",
                decision=decision,
                gate=gate_result,
                snapshot=last_snapshot,
                candidates=candidates,
                reason="ok",
                would_desc=chosen.description,
                latency_trace_id=latency_trace_id,
                wait_ms=wait_outcome.wait_ms,
                effect=effects[-1],
                snapshot_ms=snapshot_ms,
                candidate_gen_ms=candidate_gen_ms,
                gate_ms=gate_ms,
                freshness_ms=freshness_ms,
                execute_ms=execute_ms,
                step_total_ms=timer.ms_since(),
            )
            stats.note_timing(
                snapshot_ms=snapshot_ms,
                candidate_gen_ms=candidate_gen_ms,
                jev_latency_ms=decision.latency_ms,
                gate_ms=gate_ms,
                freshness_ms=freshness_ms,
                execute_ms=execute_ms,
                wait_ms=wait_outcome.wait_ms,
                step_total_ms=timer.ms_since(),
            )

        return _finish(
            JevLoopStatus.MAX_STEPS,
            "step budget exhausted",
            decision=last_decision,
        )
    finally:
        if owns_client:
            try:
                jev.close()
            except Exception:
                pass


def jev_fast_loop_enabled(config: JevConfig | None = None) -> bool:
    """True when callers should invoke :func:`run_jev_fast_loop`."""
    cfg = config or load_jev_config()
    return bool(cfg.fast_loop)
