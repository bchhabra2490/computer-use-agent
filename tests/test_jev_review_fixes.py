"""Regression tests for the five Jev review findings (offline only)."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock

from jev.actions import (
    OP_CLICK,
    OP_SCROLL_DOWN,
    classify_jev_input_privacy,
    dedupe_elements,
    enumerate_grounded_actions,
    evaluate_decision_gate,
    execute_grounded_action,
    plan_execution,
    prune_candidates_for_choice,
    resolve_safe_scroll_point,
)
from jev.client import JevClient, build_choice_criteria, build_jev_state
from jev.config import (
    JEV_CHOICE_MAX_OPTIONS,
    JEV_MAX_CANDIDATES_HARD_CEILING,
    JevConfig,
    load_jev_config,
)
from jev.loop import run_jev_fast_loop
from jev.models import (
    ActionKind,
    ElementFrame,
    GroundedAction,
    JevDecision,
    JevGateVerdict,
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
    focused: bool = False,
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
        focused=focused,
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
        focused_element_id=kwargs.get("focused_element_id"),
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


_MONS = [
    {"index": 0, "x": 0, "y": 0, "width": 1440, "height": 900, "main": True},
    {"index": 1, "x": -1920, "y": 0, "width": 1920, "height": 1080, "main": False},
]


class SafeScrollTests(unittest.TestCase):
    def test_global_scroll_never_uses_origin_or_corners(self) -> None:
        snap = _snap(_el("btn", label="Save", frame=(200, 200, 80, 24)))
        action = GroundedAction(
            action_id="scroll",
            kind=ActionKind.SCROLL,
            arguments={"op": OP_SCROLL_DOWN, "scroll_y": 400, "scroll_x": 0},
        )
        plan = plan_execution(action, snap, monitors=_MONS, pointer=(500, 400))
        self.assertEqual(plan.method, "scroll")
        self.assertIsNotNone(plan.screen_x)
        self.assertIsNotNone(plan.screen_y)
        self.assertFalse(plan.screen_x == 0 and plan.screen_y == 0)
        # Corners of main display.
        for cx, cy in ((0, 0), (1439, 0), (0, 899), (1439, 899)):
            self.assertFalse(
                abs(plan.screen_x - cx) <= 48 and abs(plan.screen_y - cy) <= 48
            )

    def test_focused_element_center_preferred(self) -> None:
        focused = _el("f1", label="Pane", focused=True, frame=(300, 300, 100, 100))
        other = _el("o1", label="Other", frame=(50, 50, 40, 40))
        snap = _snap(focused, other, focused_element_id="f1")
        pt = resolve_safe_scroll_point(
            snap, monitors=_MONS, pointer=(10, 10)  # unsafe corner-ish
        )
        self.assertIsNotNone(pt)
        self.assertAlmostEqual(pt[0], 350, delta=1)
        self.assertAlmostEqual(pt[1], 350, delta=1)

    def test_safe_display_fallback_without_element(self) -> None:
        snap = UISnapshot(revision=1, app_name="X", elements=())
        pt = resolve_safe_scroll_point(
            snap, monitors=_MONS, pointer=(-1910, 10)  # near left display corner
        )
        self.assertIsNotNone(pt)
        # Main display center ~ (720, 450)
        self.assertAlmostEqual(pt[0], 720, delta=1)
        self.assertAlmostEqual(pt[1], 450, delta=1)

    def test_multi_monitor_pointer_accepted_when_safe(self) -> None:
        snap = UISnapshot(revision=1, elements=())
        pt = resolve_safe_scroll_point(snap, monitors=_MONS, pointer=(-960, 540))
        self.assertIsNotNone(pt)
        self.assertAlmostEqual(pt[0], -960, delta=1)

    def test_no_resolvable_point_unavailable(self) -> None:
        snap = UISnapshot(revision=1, elements=())
        # Tiny monitors where margin cannot fit.
        tiny = [{"index": 0, "x": 0, "y": 0, "width": 20, "height": 20, "main": True}]
        pt = resolve_safe_scroll_point(snap, monitors=tiny, pointer=(0, 0))
        self.assertIsNone(pt)
        action = GroundedAction(
            action_id="scroll",
            kind=ActionKind.SCROLL,
            arguments={"op": OP_SCROLL_DOWN, "scroll_y": 100},
        )
        plan = plan_execution(action, snap, monitors=tiny, pointer=(0, 0))
        self.assertEqual(plan.method, "unavailable")

    def test_zero_scroll_unavailable(self) -> None:
        snap = _snap(_el("btn"))
        action = GroundedAction(
            action_id="scroll",
            kind=ActionKind.SCROLL,
            arguments={"op": OP_SCROLL_DOWN, "scroll_y": 0, "scroll_x": 0},
        )
        plan = plan_execution(action, snap, monitors=_MONS)
        self.assertEqual(plan.method, "unavailable")

    def test_scroll_execute_never_defaults_to_origin(self) -> None:
        snap = _snap(_el("btn", frame=(200, 200, 40, 40)))
        action = GroundedAction(
            action_id="scroll",
            kind=ActionKind.SCROLL,
            arguments={"op": OP_SCROLL_DOWN, "scroll_y": 100},
        )
        desktop = MagicMock()
        out = execute_grounded_action(
            action,
            snap,
            desktop=desktop,
            dry_run=False,
            coords_are_screen=True,
        )
        # May succeed with safe point or fail unavailable — never click (0,0).
        if out.get("ok"):
            call = desktop.run_actions.call_args[0][0][0]
            self.assertFalse(call["x"] == 0 and call["y"] == 0)
        else:
            self.assertIn(out.get("reason"), {"no safe scroll point", "unavailable"})


class DedupeDistinctLabelTests(unittest.TestCase):
    def test_two_edit_buttons_retained(self) -> None:
        a = _el("e1", label="Edit", frame=(10, 10, 60, 24))
        b = _el("e2", label="Edit", frame=(10, 200, 60, 24))
        kept = dedupe_elements([a, b])
        self.assertEqual(len(kept), 2)
        ids = {el.id for el in kept}
        self.assertEqual(ids, {"e1", "e2"})

    def test_nested_duplicate_collapses(self) -> None:
        outer = _el("o1", label="Save", frame=(0, 0, 200, 80), actions=())
        inner = _el("i1", label="Save", frame=(10, 10, 80, 24), actions=("AXPress",))
        kept = dedupe_elements([outer, inner])
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].id, "i1")

    def test_overlapping_identical_collapse(self) -> None:
        a = _el("a1", label="Open", frame=(10, 10, 80, 24))
        b = _el("a2", label="Open", frame=(12, 12, 76, 22))
        kept = dedupe_elements([a, b])
        self.assertEqual(len(kept), 1)

    def test_same_label_distinct_descriptions(self) -> None:
        snap = _snap(
            _el("e1", label="Edit", frame=(10, 10, 60, 24)),
            _el("e2", label="Edit", frame=(10, 400, 60, 24)),
        )
        actions = enumerate_grounded_actions(
            snap, "edit row", config=_cfg(max_candidates=40)
        )
        clicks = [
            a
            for a in actions
            if a.arguments.get("op") == OP_CLICK and a.element_id in {"e1", "e2"}
        ]
        self.assertEqual(len(clicks), 2)
        descs = {c.description for c in clicks}
        self.assertEqual(len(descs), 2)
        self.assertTrue(any("of 2" in d for d in descs))

    def test_deterministic_ids_and_order(self) -> None:
        snap = _snap(
            _el("e2", label="Edit", frame=(10, 400, 60, 24)),
            _el("e1", label="Edit", frame=(10, 10, 60, 24)),
        )
        a = enumerate_grounded_actions(snap, "x", config=_cfg(max_candidates=40))
        b = enumerate_grounded_actions(snap, "x", config=_cfg(max_candidates=40))
        self.assertEqual([x.action_id for x in a], [x.action_id for x in b])


class PrivacyGateTests(unittest.TestCase):
    def test_password_otp_key_payment_bypass(self) -> None:
        cases = [
            ('Type password "hunter2" into the field', "password"),
            ("enter the OTP 123456", "otp"),
            ("paste api key sk-abcdefghijklmnopqrstuvwxyz", "api_key"),
            ("use private key -----BEGIN PRIVATE KEY-----", "private_key"),
            ("fill cvv 123 on the card form", "payment"),
        ]
        for goal, category in cases:
            with self.subTest(goal=goal):
                result = classify_jev_input_privacy(goal)
                self.assertFalse(result.allowed)
                self.assertEqual(result.category, category)
                self.assertNotIn("hunter2", result.reason)
                self.assertNotIn("123456", result.reason)
                self.assertNotIn("sk-", result.reason)

    def test_password_manager_comparison_not_leaked(self) -> None:
        result = classify_jev_input_privacy("password manager comparison article")
        # Should not classify as credential assignment; may allow topical search.
        self.assertTrue(result.allowed)

    def test_loop_bypasses_provider(self) -> None:
        client = MagicMock()
        out = run_jev_fast_loop(
            task='Type password "hunter2" into login',
            config=_cfg(),
            client=client,
            capture_snapshot=lambda: _snap(_el("btn")),
            execute_fn=MagicMock(),
        )
        self.assertEqual(out.status, JevLoopStatus.FALLBACK)
        self.assertIn("sensitive", out.reason.lower())
        self.assertNotIn("hunter2", out.reason)
        self.assertEqual(out.fallback_prompt, "")
        client.decide.assert_not_called()

    def test_build_jev_state_redacts_goal(self) -> None:
        snap = _snap(_el("btn"))
        state = build_jev_state(
            goal="password is hunter2",
            snapshot=snap,
            candidates=(),
            config=_cfg(),
        )
        public = state.to_public_dict()
        self.assertNotIn("hunter2", str(public))
        self.assertIn("redacted", public["goal"])

    def test_client_decide_never_calls_provider(self) -> None:
        client = JevClient(_cfg())
        fake = MagicMock()
        client._sdk_client = fake
        client._owns_client = False
        decision = client.decide(
            goal="enter OTP 999888",
            snapshot=_snap(_el("btn")),
            candidates=[
                GroundedAction(
                    action_id="c1",
                    kind=ActionKind.ESCALATE,
                    arguments={"op": "escalate"},
                )
            ],
            system_one=fake.system_one,
        )
        self.assertIsNotNone(decision.error)
        self.assertNotIn("999888", decision.error or "")
        fake.system_one.assert_not_called()


class ConfirmationFlowTests(unittest.TestCase):
    def test_confirm_fn_reached_and_accepted(self) -> None:
        snap1 = _snap(_el("btn", label="Delete Forever"), revision=1)
        snap2 = _snap(_el("btn", label="Delete Forever"), revision=2)
        from jev.actions import enumerate_grounded_actions

        cands = enumerate_grounded_actions(snap1, "delete forever", config=_cfg())
        click = next(c for c in cands if c.requires_confirmation)
        confirms: list[Any] = []

        def confirm_fn(actions, **kwargs):
            confirms.append(actions)
            return True

        captures = [snap1, snap1, snap2]

        class Fake:
            def decide(self, **kwargs):
                return JevDecision(
                    selected_candidate_id=click.action_id,
                    confidence=0.95,
                    margin=0.5,
                    selected_probability=0.8,
                    second_probability=0.2,
                )

            def close(self):
                pass

        out = run_jev_fast_loop(
            task="delete forever",
            config=_cfg(max_steps=1),
            client=Fake(),  # type: ignore[arg-type]
            capture_snapshot=lambda: captures.pop(0) if captures else snap2,
            execute_fn=lambda *a, **k: {"ok": True, "reason": "ok", "dry_run": False},
            confirm_fn=confirm_fn,
            auto=False,
            sleep_fn=lambda dt: None,
            clock=lambda: 0.0,
            state_deadline_seconds=0.01,
            state_poll_seconds=0.0,
        )
        self.assertEqual(len(confirms), 1)
        self.assertEqual(len(out.executed_actions), 1)

    def test_declined_never_executes(self) -> None:
        snap = _snap(_el("btn", label="Delete"))
        cands = enumerate_grounded_actions(snap, "delete the file", config=_cfg())
        click = next(c for c in cands if c.requires_confirmation)
        exec_mock = MagicMock()

        class Fake:
            def decide(self, **kwargs):
                return JevDecision(
                    selected_candidate_id=click.action_id,
                    confidence=0.95,
                    margin=0.5,
                    selected_probability=0.8,
                    second_probability=0.2,
                )

            def close(self):
                pass

        out = run_jev_fast_loop(
            task="delete the file",
            config=_cfg(),
            client=Fake(),  # type: ignore[arg-type]
            capture_snapshot=lambda: snap,
            execute_fn=exec_mock,
            confirm_fn=lambda *a, **k: False,
            auto=False,
        )
        exec_mock.assert_not_called()
        self.assertIn("confirmation", out.reason.lower())

    def test_shadow_never_confirms(self) -> None:
        snap = _snap(_el("btn", label="Delete Forever"))
        confirm = MagicMock(return_value=True)
        exec_mock = MagicMock()
        cands = enumerate_grounded_actions(snap, "delete forever", config=_cfg())
        click = next(c for c in cands if c.requires_confirmation)

        class Fake:
            def decide(self, **kwargs):
                return JevDecision(
                    selected_candidate_id=click.action_id,
                    confidence=0.95,
                    margin=0.5,
                    selected_probability=0.8,
                    second_probability=0.2,
                )

            def close(self):
                pass

        out = run_jev_fast_loop(
            task="delete forever",
            config=_cfg(shadow_mode=True),
            client=Fake(),  # type: ignore[arg-type]
            capture_snapshot=lambda: snap,
            execute_fn=exec_mock,
            confirm_fn=confirm,
            auto=False,
        )
        self.assertEqual(out.status, JevLoopStatus.SHADOW_COMPLETE)
        confirm.assert_not_called()
        exec_mock.assert_not_called()

    def test_gate_needs_confirmation_state(self) -> None:
        action = GroundedAction(
            action_id="x",
            kind=ActionKind.CLICK,
            arguments={"op": OP_CLICK},
            requires_confirmation=True,
        )
        decision = JevDecision(selected_candidate_id="x", confidence=0.99, margin=0.5)
        result = evaluate_decision_gate(decision, [action], _cfg(), confirmed=False)
        self.assertEqual(result.verdict, JevGateVerdict.NEEDS_CONFIRMATION)
        self.assertTrue(result.allowed_pending_confirmation)


class ChoiceLimitTests(unittest.TestCase):
    def test_default_and_clamp(self) -> None:
        cfg = load_jev_config({})
        self.assertEqual(cfg.max_candidates, 220)
        high = load_jev_config({"JEV_MAX_CANDIDATES": "9999"})
        self.assertEqual(high.max_candidates, JEV_MAX_CANDIDATES_HARD_CEILING)

    def test_criteria_never_exceeds_255(self) -> None:
        many = [
            GroundedAction(
                action_id=f"c{i}",
                kind=ActionKind.CLICK,
                arguments={"op": OP_CLICK},
                description=f"click {i}",
            )
            for i in range(400)
        ]
        many.append(
            GroundedAction(
                action_id="esc",
                kind=ActionKind.ESCALATE,
                arguments={"op": "escalate"},
                description="Escalate",
            )
        )
        criteria = build_choice_criteria(many)
        self.assertLessEqual(len(criteria), JEV_CHOICE_MAX_OPTIONS)
        self.assertIn("esc", criteria)

    def test_prune_preserves_reserved(self) -> None:
        items = [
            GroundedAction(
                action_id=f"p{i}",
                kind=ActionKind.CLICK,
                arguments={"op": OP_CLICK},
            )
            for i in range(300)
        ]
        for op, aid in (
            ("wait", "w"),
            ("done", "d"),
            ("escalate", "e"),
        ):
            items.append(
                GroundedAction(
                    action_id=aid,
                    kind=ActionKind.WAIT if op == "wait" else ActionKind.ESCALATE,
                    arguments={"op": op},
                )
            )
        pruned = prune_candidates_for_choice(items, limit=20)
        self.assertLessEqual(len(pruned), 20)
        ops = {str(a.arguments.get("op")) for a in pruned}
        self.assertIn("escalate", ops)

    def test_hard_limit_accepted(self) -> None:
        items = [
            GroundedAction(
                action_id=f"p{i}",
                kind=ActionKind.CLICK,
                arguments={"op": OP_CLICK},
            )
            for i in range(JEV_MAX_CANDIDATES_HARD_CEILING - 3)
        ]
        for op, aid in (("wait", "w"), ("done", "d"), ("escalate", "e")):
            items.append(
                GroundedAction(
                    action_id=aid,
                    kind=ActionKind.ESCALATE,
                    arguments={"op": op},
                )
            )
        pruned = prune_candidates_for_choice(
            items, limit=JEV_MAX_CANDIDATES_HARD_CEILING
        )
        self.assertEqual(len(pruned), JEV_MAX_CANDIDATES_HARD_CEILING)


if __name__ == "__main__":
    unittest.main()
