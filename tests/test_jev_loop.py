"""Mocked tests for the Jev active fast loop (no network, no desktop)."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from jev.actions import OP_CLICK, OP_DONE, OP_TYPE, OP_WAIT
from jev.config import JevConfig
from jev.loop import (
    action_signature,
    format_jev_handoff_prompt,
    jev_fast_loop_enabled,
    run_jev_fast_loop,
    wait_for_revision_change,
)
from jev.models import (
    ActionKind,
    ElementFrame,
    GroundedAction,
    JevDecision,
    JevLoopResult,
    JevLoopStatus,
    UIElement,
    UISnapshot,
)


def _el(
    eid: str,
    *,
    role: str = "AXButton",
    label: str = "Save",
    enabled: bool = True,
    sensitive: bool = False,
    frame: tuple[float, float, float, float] | None = (10, 10, 80, 24),
    actions: tuple[str, ...] = ("AXPress",),
) -> UIElement:
    ef = None if frame is None else ElementFrame(*frame)
    return UIElement(
        id=eid,
        role=role,
        label=label,
        enabled=enabled,
        sensitive=sensitive,
        frame=ef,
        supported_actions=actions,
    )


def _snap(*elements: UIElement, revision: int = 1, **kwargs) -> UISnapshot:
    snap = UISnapshot(
        revision=revision,
        app_name=kwargs.get("app_name", "Notes"),
        bundle_id=kwargs.get("bundle_id", "com.apple.Notes"),
        process_id=kwargs.get("process_id", 99),
        window_title=kwargs.get("window_title", "Doc"),
        elements=tuple(elements),
        error=kwargs.get("error", ""),
    )
    for el in elements:
        snap.register_handle(el.id, object())
    return snap


def _cfg(**kwargs) -> JevConfig:
    base = dict(
        fast_loop=True,
        shadow_mode=False,
        api_key="test-key-not-real",
        model="jev-test",
        min_confidence=0.70,
        min_margin=0.20,
        complete_threshold=0.85,
        stuck_threshold=0.70,
        max_steps=5,
        max_candidates=220,
        request_timeout_seconds=3.0,
        max_consecutive_failures=2,
    )
    base.update(kwargs)
    return JevConfig(**base)


class FakeJev:
    def __init__(self, decisions: list[JevDecision] | JevDecision):
        if isinstance(decisions, list):
            self._decisions = list(decisions)
        else:
            self._decisions = [decisions]
        self.calls = 0
        self.closed = False

    def decide(self, **kwargs: Any) -> JevDecision:
        self.calls += 1
        if not self._decisions:
            return JevDecision(error="exhausted", fallback_reason="exhausted")
        return self._decisions.pop(0)

    def close(self) -> None:
        self.closed = True


def _decision_for(action_id: str, **kwargs) -> JevDecision:
    conf = kwargs.pop("confidence", 0.95)
    margin = kwargs.pop("margin", 0.5)
    stuck = kwargs.pop("stuck_probability", 0.0)
    complete = kwargs.pop("complete_probability", 0.0)
    return JevDecision(
        selected_candidate_id=action_id,
        selected_probability=0.8,
        second_probability=0.3,
        margin=margin,
        confidence=conf,
        stuck_probability=stuck,
        complete_probability=complete,
        distribution={action_id: 0.8},
        model="jev-test",
        **kwargs,
    )


def _first_click_id(snap: UISnapshot, goal: str = "click Save") -> str:
    from jev.actions import enumerate_grounded_actions

    cands = enumerate_grounded_actions(snap, goal, config=_cfg())
    for c in cands:
        if c.arguments.get("op") == OP_CLICK and c.element_id == "btn":
            return c.action_id
    for c in cands:
        if c.arguments.get("op") == OP_CLICK:
            return c.action_id
    raise AssertionError("no click candidate")


class WaitRevisionTests(unittest.TestCase):
    def test_changed_revision_counts_as_effect(self) -> None:
        before = _snap(_el("btn"), revision=1)
        after = _snap(_el("btn"), revision=2)
        calls = {"n": 0}

        def capture() -> UISnapshot:
            calls["n"] += 1
            return after

        clock = {"t": 0.0}

        def now() -> float:
            return clock["t"]

        def sleep(dt: float) -> None:
            clock["t"] += dt

        out = wait_for_revision_change(
            before=before,
            capture_snapshot=capture,
            deadline_seconds=1.0,
            poll_seconds=0.05,
            sleep_fn=sleep,
            clock=now,
        )
        self.assertTrue(out.changed)
        self.assertEqual(out.after_revision, 2)
        self.assertGreater(out.wait_ms, 0)

    def test_unchanged_revision_counts_as_no_effect(self) -> None:
        before = _snap(_el("btn"), revision=3)
        clock = {"t": 0.0}

        def now() -> float:
            return clock["t"]

        def sleep(dt: float) -> None:
            clock["t"] += dt

        out = wait_for_revision_change(
            before=before,
            capture_snapshot=lambda: before,
            deadline_seconds=0.12,
            poll_seconds=0.05,
            sleep_fn=sleep,
            clock=now,
        )
        self.assertFalse(out.changed)
        self.assertEqual(out.after_revision, 3)


class DisabledAndShadowTests(unittest.TestCase):
    def test_disabled_returns_immediately(self) -> None:
        cfg = _cfg(fast_loop=False)
        self.assertFalse(jev_fast_loop_enabled(cfg))
        out = run_jev_fast_loop(task="click Save", config=cfg)
        self.assertEqual(out.status, JevLoopStatus.DISABLED)
        self.assertEqual(out.executed_actions, ())

    def test_shadow_never_executes(self) -> None:
        snap = _snap(_el("btn", label="Save"))
        aid = _first_click_id(snap)
        client = FakeJev(_decision_for(aid))
        executed = MagicMock()
        out = run_jev_fast_loop(
            task="click Save",
            config=_cfg(shadow_mode=True),
            client=client,  # type: ignore[arg-type]
            capture_snapshot=lambda: snap,
            execute_fn=executed,
        )
        self.assertEqual(out.status, JevLoopStatus.SHADOW_COMPLETE)
        executed.assert_not_called()
        self.assertEqual(out.executed_actions, ())


class ActiveLoopTests(unittest.TestCase):
    def test_high_confidence_executes_once(self) -> None:
        snap1 = _snap(_el("btn", label="Save"), revision=1)
        snap2 = _snap(_el("btn", label="Save"), revision=2)
        aid = _first_click_id(snap1)
        client = FakeJev(_decision_for(aid))
        # decision snap, freshness snap (same), wait polls → changed
        captures = [snap1, snap1, snap2]
        exec_calls: list[str] = []

        def capture() -> UISnapshot:
            return captures.pop(0) if captures else snap2

        def execute(action, snapshot, **kwargs):
            exec_calls.append(action.action_id)
            self.assertFalse(kwargs.get("dry_run", True))
            return {"ok": True, "reason": "ax_press", "dry_run": False}

        clock = {"t": 0.0}

        out = run_jev_fast_loop(
            task="click Save",
            config=_cfg(max_steps=1),
            client=client,  # type: ignore[arg-type]
            capture_snapshot=capture,
            execute_fn=execute,
            sleep_fn=lambda dt: clock.__setitem__("t", clock["t"] + dt),
            clock=lambda: clock["t"],
            state_deadline_seconds=0.2,
            state_poll_seconds=0.05,
        )
        self.assertEqual(len(exec_calls), 1)
        self.assertEqual(out.executed_actions[0].action_id, aid)
        self.assertTrue(any(e.startswith("revision") for e in out.observed_effects))
        self.assertEqual(out.status, JevLoopStatus.MAX_STEPS)

    def test_active_max_steps_after_one(self) -> None:
        snap1 = _snap(_el("btn", label="Save"), revision=1)
        snap2 = _snap(_el("btn", label="Done"), revision=2)
        aid = _first_click_id(snap1)
        client = FakeJev(_decision_for(aid))
        state = {"n": 0}

        def capture() -> UISnapshot:
            state["n"] += 1
            # 1=decide, 2=freshness, 3+=wait / later
            return snap1 if state["n"] <= 2 else snap2

        out = run_jev_fast_loop(
            task="click Save",
            config=_cfg(max_steps=1),
            client=client,  # type: ignore[arg-type]
            capture_snapshot=capture,
            execute_fn=lambda *a, **k: {"ok": True, "reason": "ok", "dry_run": False},
            sleep_fn=lambda dt: None,
            clock=lambda: 0.0,
            state_deadline_seconds=0.01,
            state_poll_seconds=0.0,
        )
        self.assertEqual(len(out.executed_actions), 1)
        self.assertIn(out.status, {JevLoopStatus.MAX_STEPS, JevLoopStatus.FALLBACK})

    def test_freshness_failure_recaptures_not_executes(self) -> None:
        """Stale element → recapture path; executor must not run on stale decision."""
        el = _el("btn", label="Save")
        snap_a = _snap(el, revision=1, window_title="Doc")
        # Different window → validation fails on freshness recapture
        snap_b = _snap(
            _el("btn", label="Save"), revision=2, window_title="Other App Totally"
        )
        aid = _first_click_id(snap_a)
        client = FakeJev(
            [
                _decision_for(aid),
                _decision_for(aid),
            ]
        )
        exec_mock = MagicMock(return_value={"ok": True, "dry_run": False})
        # decide=snap_a, then freshness retries all return snap_b
        captures = [snap_a, snap_b, snap_b, snap_b, snap_b, snap_b]

        out = run_jev_fast_loop(
            task="click Save",
            config=_cfg(max_steps=3),
            client=client,  # type: ignore[arg-type]
            capture_snapshot=lambda: captures.pop(0) if captures else snap_b,
            execute_fn=exec_mock,
            sleep_fn=lambda dt: None,
            clock=lambda: 0.0,
        )
        exec_mock.assert_not_called()
        self.assertEqual(out.status, JevLoopStatus.FALLBACK)
        self.assertIn("freshness", out.reason.lower())

    def test_two_no_effect_actions_fallback(self) -> None:
        snap = _snap(
            _el("btn", label="Save"),
            _el("btn2", label="Open", frame=(100, 10, 80, 24)),
            revision=1,
        )
        from jev.actions import enumerate_grounded_actions

        cands = enumerate_grounded_actions(snap, "click Save or Open", config=_cfg())
        clicks = [c for c in cands if c.arguments.get("op") == OP_CLICK]
        self.assertGreaterEqual(len(clicks), 2)
        a1, a2 = clicks[0].action_id, clicks[1].action_id
        client = FakeJev([_decision_for(a1), _decision_for(a2)])
        clock = {"t": 0.0}

        def sleep(dt: float) -> None:
            clock["t"] += max(dt, 0.2)  # jump past deadline quickly

        out = run_jev_fast_loop(
            task="click Save or Open",
            config=_cfg(max_steps=5),
            client=client,  # type: ignore[arg-type]
            capture_snapshot=lambda: snap,
            execute_fn=lambda *a, **k: {"ok": True, "reason": "ok", "dry_run": False},
            sleep_fn=sleep,
            clock=lambda: clock["t"],
            state_deadline_seconds=0.1,
            state_poll_seconds=0.05,
        )
        self.assertEqual(out.status, JevLoopStatus.FALLBACK)
        self.assertIn("no meaningful state change", out.reason)
        self.assertEqual(len(out.executed_actions), 2)

    def test_repeated_unchanged_action_fallback(self) -> None:
        snap = _snap(_el("btn", label="Save"), revision=1)
        aid = _first_click_id(snap)
        # First action "succeeds" with effect by bumping revision then we reset...
        # Simpler: execute once with effect, then same action on same revision.
        snaps = {
            "r": 1,
            "phase": 0,
        }

        def capture() -> UISnapshot:
            return _snap(_el("btn", label="Save"), revision=snaps["r"])

        decisions = [_decision_for(aid), _decision_for(aid), _decision_for(aid)]
        client = FakeJev(decisions)
        clock = {"t": 0.0}

        def execute(action, snapshot, **kwargs):
            # After first exec, bump revision once so first action counts as effect,
            # then leave revision sticky so second identical action triggers repeat.
            if snaps["phase"] == 0:
                snaps["r"] = 2
                snaps["phase"] = 1
            return {"ok": True, "reason": "ok", "dry_run": False}

        def sleep(dt: float) -> None:
            clock["t"] += dt

        out = run_jev_fast_loop(
            task="click Save",
            config=_cfg(max_steps=5),
            client=client,  # type: ignore[arg-type]
            capture_snapshot=capture,
            execute_fn=execute,
            sleep_fn=sleep,
            clock=lambda: clock["t"],
            state_deadline_seconds=0.2,
            state_poll_seconds=0.05,
        )
        # After first effect revision=2; second execute leaves r=2; third decision
        # same action against unchanged → repeated. Or second no-effect then repeat.
        self.assertEqual(out.status, JevLoopStatus.FALLBACK)
        self.assertTrue(
            "repeat" in out.reason.lower() or "no meaningful" in out.reason.lower()
        )

    def test_low_confidence_fallback(self) -> None:
        snap = _snap(_el("btn", label="Save"))
        aid = _first_click_id(snap)
        client = FakeJev(_decision_for(aid, confidence=0.2, margin=0.5))
        exec_mock = MagicMock()
        out = run_jev_fast_loop(
            task="click Save",
            config=_cfg(),
            client=client,  # type: ignore[arg-type]
            capture_snapshot=lambda: snap,
            execute_fn=exec_mock,
        )
        exec_mock.assert_not_called()
        self.assertEqual(out.status, JevLoopStatus.FALLBACK)
        self.assertIn("confidence", out.reason.lower())

    def test_narrow_margin_fallback(self) -> None:
        snap = _snap(_el("btn", label="Save"))
        aid = _first_click_id(snap)
        client = FakeJev(_decision_for(aid, confidence=0.95, margin=0.01))
        exec_mock = MagicMock()
        out = run_jev_fast_loop(
            task="click Save",
            config=_cfg(),
            client=client,  # type: ignore[arg-type]
            capture_snapshot=lambda: snap,
            execute_fn=exec_mock,
        )
        exec_mock.assert_not_called()
        self.assertEqual(out.status, JevLoopStatus.FALLBACK)
        self.assertIn("margin", out.reason.lower())

    def test_stuck_probability_fallback(self) -> None:
        snap = _snap(_el("btn", label="Save"))
        aid = _first_click_id(snap)
        client = FakeJev(_decision_for(aid, stuck_probability=0.99))
        exec_mock = MagicMock()
        out = run_jev_fast_loop(
            task="click Save",
            config=_cfg(),
            client=client,  # type: ignore[arg-type]
            capture_snapshot=lambda: snap,
            execute_fn=exec_mock,
        )
        exec_mock.assert_not_called()
        self.assertEqual(out.status, JevLoopStatus.FALLBACK)
        self.assertIn("stuck", out.reason.lower())

    def test_consecutive_failures_stop(self) -> None:
        snap = _snap(_el("btn", label="Save"))
        client = FakeJev(
            [
                JevDecision(
                    error="provider error: boom", fallback_reason="provider error"
                ),
                JevDecision(
                    error="provider error: boom", fallback_reason="provider error"
                ),
                JevDecision(
                    error="provider error: boom", fallback_reason="provider error"
                ),
            ]
        )
        out = run_jev_fast_loop(
            task="click Save",
            config=_cfg(max_consecutive_failures=2),
            client=client,  # type: ignore[arg-type]
            capture_snapshot=lambda: snap,
            execute_fn=MagicMock(),
        )
        self.assertIn(out.status, {JevLoopStatus.FALLBACK, JevLoopStatus.UNAVAILABLE})
        self.assertTrue(
            "fail" in out.reason.lower() or "provider" in out.reason.lower()
        )

    def test_empty_snapshot_fallback(self) -> None:
        snap = UISnapshot(revision=0, error="accessibility disabled")
        out = run_jev_fast_loop(
            task="click Save",
            config=_cfg(),
            client=FakeJev(_decision_for("x")),  # type: ignore[arg-type]
            capture_snapshot=lambda: snap,
            execute_fn=MagicMock(),
        )
        self.assertEqual(out.status, JevLoopStatus.FALLBACK)
        self.assertIn("accessibility", out.reason.lower())

    def test_stop_signal_aborts(self) -> None:
        snap = _snap(_el("btn", label="Save"))
        aid = _first_click_id(snap)
        client = FakeJev(_decision_for(aid))
        out = run_jev_fast_loop(
            task="click Save",
            config=_cfg(),
            client=client,  # type: ignore[arg-type]
            capture_snapshot=lambda: snap,
            execute_fn=MagicMock(),
            should_stop=lambda: True,
        )
        self.assertEqual(out.status, JevLoopStatus.ABORTED)

    def test_completion_requires_verification(self) -> None:
        snap = _snap(_el("btn", label="Save"))
        from jev.actions import enumerate_grounded_actions

        cands = enumerate_grounded_actions(snap, "done", config=_cfg())
        done = next(c for c in cands if c.arguments.get("op") == OP_DONE)
        client = FakeJev(
            _decision_for(done.action_id, complete_probability=0.99, confidence=0.99)
        )
        exec_mock = MagicMock()
        out = run_jev_fast_loop(
            task="finish the task",
            original_task="finish the task",
            config=_cfg(),
            client=client,  # type: ignore[arg-type]
            capture_snapshot=lambda: snap,
            execute_fn=exec_mock,
        )
        exec_mock.assert_not_called()
        self.assertEqual(out.status, JevLoopStatus.COMPLETED_PENDING_VERIFICATION)
        self.assertIn("verification", out.reason.lower())
        self.assertIn("Verify", out.fallback_prompt)

    def test_fallback_context_includes_actions_and_state(self) -> None:
        snap = _snap(_el("btn", label="Save"), revision=4)
        aid = _first_click_id(snap)
        client = FakeJev(_decision_for(aid, confidence=0.1))
        out = run_jev_fast_loop(
            task="click Save",
            original_task="Please click Save",
            config=_cfg(),
            client=client,  # type: ignore[arg-type]
            capture_snapshot=lambda: snap,
            execute_fn=MagicMock(),
        )
        self.assertIn("Please click Save", out.fallback_prompt)
        self.assertIn("revision=4", out.fallback_prompt)
        self.assertIn("Jev handoff", out.fallback_prompt)

    def test_safety_confirmation_required(self) -> None:
        snap = _snap(_el("btn", label="Delete Forever"))
        from jev.actions import enumerate_grounded_actions

        cands = enumerate_grounded_actions(snap, "delete forever", config=_cfg())
        click = next(
            c
            for c in cands
            if c.arguments.get("op") == OP_CLICK and c.requires_confirmation
        )
        client = FakeJev(_decision_for(click.action_id))
        exec_mock = MagicMock()
        out = run_jev_fast_loop(
            task="delete forever",
            config=_cfg(),
            client=client,  # type: ignore[arg-type]
            capture_snapshot=lambda: snap,
            execute_fn=exec_mock,
            auto=False,
            confirm_fn=None,
        )
        exec_mock.assert_not_called()
        self.assertEqual(out.status, JevLoopStatus.FALLBACK)
        self.assertIn("confirmation", out.reason.lower())

    def test_safety_confirmation_declined(self) -> None:
        snap = _snap(_el("btn", label="Delete"))
        from jev.actions import enumerate_grounded_actions

        cands = enumerate_grounded_actions(snap, "delete the file", config=_cfg())
        click = next(c for c in cands if c.requires_confirmation)
        client = FakeJev(_decision_for(click.action_id))
        exec_mock = MagicMock()
        out = run_jev_fast_loop(
            task="delete the file",
            config=_cfg(),
            client=client,  # type: ignore[arg-type]
            capture_snapshot=lambda: snap,
            execute_fn=exec_mock,
            auto=False,
            confirm_fn=lambda *a, **k: False,
        )
        exec_mock.assert_not_called()
        self.assertIn("confirmation", out.reason.lower())

    def test_secure_typing_impossible(self) -> None:
        field = _el(
            "pw",
            role="AXTextField",
            label="Password",
            sensitive=True,
            actions=("AXPress",),
        )
        snap = _snap(field)
        from jev.actions import enumerate_grounded_actions

        cands = enumerate_grounded_actions(
            snap, 'type password "secret" into the field', config=_cfg()
        )
        # Enumeration should not offer sensitive type; if forced, loop blocks.
        type_actions = [c for c in cands if c.arguments.get("op") == OP_TYPE]
        self.assertEqual(type_actions, [])
        forced = GroundedAction(
            action_id="forced-type",
            kind=ActionKind.TYPE,
            element_id="pw",
            description="type secret",
            arguments={"op": OP_TYPE, "text": "secret"},
            sensitive=True,
        )
        client = FakeJev(_decision_for("forced-type"))
        # Patch enumerate to inject forced candidate
        with patch("jev.loop.enumerate_grounded_actions", return_value=[forced]):
            out = run_jev_fast_loop(
                task="type password",
                config=_cfg(),
                client=client,  # type: ignore[arg-type]
                capture_snapshot=lambda: snap,
                execute_fn=MagicMock(),
            )
        self.assertEqual(out.status, JevLoopStatus.FALLBACK)
        self.assertTrue(
            "secure" in out.reason.lower() or "sensitive" in out.reason.lower()
        )

    def test_handoff_prompt_lists_executed(self) -> None:
        action = GroundedAction(
            action_id="a1",
            kind=ActionKind.CLICK,
            description="Click Save",
            arguments={"op": OP_CLICK},
        )
        result = JevLoopResult(
            status=JevLoopStatus.FALLBACK,
            steps=1,
            executed_actions=(action,),
            observed_effects=("revision 1→2",),
            reason="escalate",
            latest_snapshot_public={"revision": 2, "app_name": "Notes", "elements": []},
        )
        text = format_jev_handoff_prompt(original_task="Save the doc", result=result)
        self.assertIn("Click Save", text)
        self.assertIn("revision 1→2", text)
        self.assertIn("Do not restart", text)


class AgentIntegrationGuardTests(unittest.TestCase):
    def test_agent_skips_jev_when_disabled(self) -> None:
        """Behavioral: jev_fast_loop_enabled false ⇒ agent must not call the loop."""
        self.assertFalse(jev_fast_loop_enabled(_cfg(fast_loop=False)))
        with patch("jev.loop.run_jev_fast_loop") as mocked:
            # Simulate the agent guard.
            from jev.config import load_jev_config
            from jev.loop import jev_fast_loop_enabled as enabled

            cfg = load_jev_config(
                {
                    "JEV_FAST_LOOP": "0",
                    "JEV_SHADOW_MODE": "1",
                    "TYPESAFE_API_KEY": "",
                }
            )
            if enabled(cfg):
                run_jev_fast_loop(task="x", config=cfg)
            mocked.assert_not_called()

    def test_agent_session_wires_jev_after_recipes(self) -> None:
        from pathlib import Path

        src = Path(__file__).resolve().parents[1].joinpath("agent.py").read_text()
        # Locate _run_agent_session body roughly via unique markers.
        start = src.index("def _run_agent_session(")
        end = src.index("\ndef _bootstrap_agent_run(", start)
        body = src[start:end]
        self.assertIn("run_jev_fast_loop", body)
        self.assertIn("jev_fast_loop_enabled", body)
        recipe_idx = body.index("_apply_recipe_start")
        jev_idx = body.index("run_jev_fast_loop")
        route_idx = body.index("resolve_agent_model")
        self.assertLess(recipe_idx, jev_idx)
        self.assertLess(jev_idx, route_idx)


class SignatureTests(unittest.TestCase):
    def test_action_signature_stable(self) -> None:
        a = GroundedAction(
            action_id="1",
            kind=ActionKind.CLICK,
            element_id="e",
            arguments={"op": OP_CLICK},
        )
        b = GroundedAction(
            action_id="2",
            kind=ActionKind.CLICK,
            element_id="e",
            arguments={"op": OP_CLICK},
        )
        self.assertEqual(action_signature(a), action_signature(b))


if __name__ == "__main__":
    unittest.main()
