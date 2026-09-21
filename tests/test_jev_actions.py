"""Unit tests for Jev grounded-action generation, safety, freshness, and gates."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from jev.actions import (
    OP_CLICK,
    OP_DONE,
    OP_ENTER,
    OP_ESCALATE,
    OP_FOCUS,
    OP_TYPE,
    OP_WAIT,
    action_requires_confirmation,
    candidates_by_id,
    dedupe_elements,
    enumerate_grounded_actions,
    evaluate_decision_gate,
    execute_grounded_action,
    extract_task_text,
    plan_execution,
    validate_grounded_action,
)
from jev.config import JevConfig
from jev.models import (
    ActionKind,
    ElementFrame,
    GroundedAction,
    JevDecision,
    UIElement,
    UISnapshot,
)


def _el(
    eid: str,
    *,
    role: str = "AXButton",
    label: str = "Save",
    value: str = "",
    enabled: bool = True,
    sensitive: bool = False,
    focused: bool = False,
    frame: tuple[float, float, float, float] | None = (10, 10, 80, 24),
    actions: tuple[str, ...] = ("AXPress",),
) -> UIElement:
    ef = None if frame is None else ElementFrame(*frame)
    return UIElement(
        id=eid,
        role=role,
        label=label,
        value=value,
        enabled=enabled,
        sensitive=sensitive,
        focused=focused,
        frame=ef,
        supported_actions=actions,
    )


def _snap(*elements: UIElement, **kwargs) -> UISnapshot:
    snap = UISnapshot(
        revision=1,
        app_name=kwargs.get("app_name", "Notes"),
        bundle_id=kwargs.get("bundle_id", "com.apple.Notes"),
        process_id=kwargs.get("process_id", 99),
        window_title=kwargs.get("window_title", "Doc"),
        elements=tuple(elements),
    )
    for el in elements:
        snap.register_handle(el.id, object())
    return snap


class ExtractTaskTextTests(unittest.TestCase):
    def test_quoted_text(self) -> None:
        self.assertEqual(
            extract_task_text('Search for "Ashtavakra Gita"'), "Ashtavakra Gita"
        )

    def test_url(self) -> None:
        self.assertEqual(
            extract_task_text("Open https://example.com/path and screenshot"),
            "https://example.com/path",
        )

    def test_explicit_phrase(self) -> None:
        self.assertEqual(extract_task_text("search for Mulki weather"), "Mulki weather")

    def test_ambiguous_multiple_quotes(self) -> None:
        self.assertIsNone(extract_task_text('Compare "alpha" and "beta"'))

    def test_rejects_password_tasks(self) -> None:
        self.assertIsNone(extract_task_text('Type password "hunter2" into the field'))
        self.assertIsNone(extract_task_text("enter the OTP 123456"))
        self.assertIsNone(extract_task_text("fill in my credit card 4111"))


class EnumerateCandidatesTests(unittest.TestCase):
    def test_candidates_by_role(self) -> None:
        snap = _snap(
            _el("b1", role="AXButton", label="Go"),
            _el(
                "t1",
                role="AXTextField",
                label="Query",
                value="",
                actions=("AXConfirm",),
            ),
            _el("l1", role="AXLink", label="Docs"),
        )
        actions = enumerate_grounded_actions(
            snap, 'search for "kites"', config=JevConfig(max_candidates=50)
        )
        ops = {a.arguments["op"] for a in actions}
        self.assertIn(OP_CLICK, ops)
        self.assertIn(OP_FOCUS, ops)
        self.assertIn(OP_TYPE, ops)
        self.assertIn(OP_ENTER, ops)
        self.assertIn(OP_WAIT, ops)
        self.assertIn(OP_DONE, ops)
        self.assertIn(OP_ESCALATE, ops)
        typed = [a for a in actions if a.arguments.get("op") == OP_TYPE]
        self.assertTrue(typed)
        self.assertEqual(typed[0].arguments["text"], "kites")
        self.assertNotIn("kites", typed[0].action_id)

    def test_disabled_excluded(self) -> None:
        snap = _snap(
            _el("b1", label="On"),
            _el("b2", label="Off", enabled=False),
        )
        actions = enumerate_grounded_actions(
            snap, "click", config=JevConfig(max_candidates=40)
        )
        click_labels = [
            a.description for a in actions if a.arguments.get("op") == OP_CLICK
        ]
        self.assertTrue(any("On" in d for d in click_labels))
        self.assertFalse(any("Off" in d for d in click_labels))

    def test_secure_fields_never_typeable(self) -> None:
        snap = _snap(
            _el(
                "p1",
                role="AXSecureTextField",
                label="Password",
                value="",
                sensitive=True,
                actions=("AXConfirm",),
            )
        )
        actions = enumerate_grounded_actions(
            snap, 'type "secret"', config=JevConfig(max_candidates=40)
        )
        self.assertFalse(any(a.arguments.get("op") == OP_TYPE for a in actions))
        self.assertFalse(
            any(
                a.arguments.get("op") == OP_CLICK and a.element_id == "p1"
                for a in actions
            )
        )

    def test_dedupe_nested_controls(self) -> None:
        outer = _el("o1", label="Save", frame=(0, 0, 200, 80), actions=())
        inner = _el("i1", label="Save", frame=(10, 10, 80, 24), actions=("AXPress",))
        deduped = dedupe_elements([outer, inner])
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].id, "i1")

    def test_candidate_limit_and_reserved(self) -> None:
        many = [
            _el(f"b{i}", label=f"B{i}", frame=(float(i), 0, 10, 10)) for i in range(30)
        ]
        snap = _snap(*many)
        actions = enumerate_grounded_actions(
            snap, "click something", config=JevConfig(max_candidates=8)
        )
        self.assertLessEqual(len(actions), 8)
        ops = [a.arguments["op"] for a in actions]
        self.assertIn(OP_WAIT, ops)
        self.assertIn(OP_DONE, ops)
        self.assertIn(OP_ESCALATE, ops)

    def test_deterministic_ranking(self) -> None:
        snap = _snap(
            _el("b2", label="Beta", frame=(20, 0, 10, 10)),
            _el("b1", label="Alpha", frame=(0, 0, 10, 10)),
        )
        a = enumerate_grounded_actions(snap, "x", config=JevConfig(max_candidates=40))
        b = enumerate_grounded_actions(snap, "x", config=JevConfig(max_candidates=40))
        self.assertEqual([x.action_id for x in a], [x.action_id for x in b])

    def test_candidate_id_lookup(self) -> None:
        snap = _snap(_el("b1"))
        actions = enumerate_grounded_actions(
            snap, "go", config=JevConfig(max_candidates=20)
        )
        by_id = candidates_by_id(actions)
        for action in actions:
            self.assertIs(by_id[action.action_id], action)

    def test_always_escalate_when_empty_tree(self) -> None:
        snap = _snap()
        actions = enumerate_grounded_actions(
            snap, "do stuff", config=JevConfig(max_candidates=5)
        )
        self.assertTrue(any(a.arguments.get("op") == OP_ESCALATE for a in actions))


class SafetyTests(unittest.TestCase):
    def test_confirmation_flags(self) -> None:
        buy = _el("b1", label="Buy now")
        self.assertTrue(action_requires_confirmation(op=OP_CLICK, element=buy))
        save = _el("b2", label="Save draft")
        self.assertFalse(action_requires_confirmation(op=OP_CLICK, element=save))
        self.assertTrue(
            action_requires_confirmation(
                op=OP_CLICK, element=save, task="delete the file"
            )
        )
        snap = _snap(buy)
        actions = enumerate_grounded_actions(
            snap, "purchase item", config=JevConfig(max_candidates=20)
        )
        click = next(a for a in actions if a.arguments.get("op") == OP_CLICK)
        self.assertTrue(click.requires_confirmation)


class FreshnessTests(unittest.TestCase):
    def test_valid_freshness(self) -> None:
        el = _el("b1")
        observed = _snap(el)
        current = _snap(el)
        action = GroundedAction(
            action_id="cand_x",
            kind=ActionKind.CLICK,
            element_id="b1",
            arguments={"op": OP_CLICK},
        )
        result = validate_grounded_action(action, observed, current)
        self.assertTrue(result.ok)
        self.assertIsNotNone(result.current_frame)

    def test_missing_moved_disabled_relabeled_role_change(self) -> None:
        el = _el("b1", label="Save")
        observed = _snap(el)
        action = GroundedAction(
            action_id="cand_x",
            kind=ActionKind.CLICK,
            element_id="b1",
            arguments={"op": OP_CLICK},
        )
        missing = _snap()
        self.assertFalse(validate_grounded_action(action, observed, missing).ok)

        disabled = _snap(_el("b1", label="Save", enabled=False))
        self.assertFalse(validate_grounded_action(action, observed, disabled).ok)

        relabeled = _snap(_el("b1", label="Cancel"))
        self.assertFalse(validate_grounded_action(action, observed, relabeled).ok)

        role_changed = _snap(_el("b1", role="AXStaticText", label="Save", actions=()))
        self.assertFalse(validate_grounded_action(action, observed, role_changed).ok)

        moved = _snap(_el("b1", label="Save", frame=(500, 500, 80, 24)))
        # Same id/label/role — frame change alone is ok; execution uses current frame.
        ok = validate_grounded_action(action, observed, moved)
        self.assertTrue(ok.ok)
        self.assertEqual(ok.current_frame.x, 500)  # type: ignore[union-attr]

    def test_sensitive_status_change_rejected(self) -> None:
        el = _el("t1", role="AXTextField", label="Code", actions=("AXConfirm",))
        observed = _snap(el)
        current = _snap(
            _el(
                "t1",
                role="AXSecureTextField",
                label="Code",
                sensitive=True,
                actions=("AXConfirm",),
            )
        )
        action = GroundedAction(
            action_id="c",
            kind=ActionKind.TYPE,
            element_id="t1",
            arguments={"op": OP_TYPE, "text": "abc"},
        )
        self.assertFalse(validate_grounded_action(action, observed, current).ok)

    def test_plan_uses_current_frame(self) -> None:
        el = _el("b1", frame=(100, 200, 40, 20))
        snap = _snap(el)
        action = GroundedAction(
            action_id="c",
            kind=ActionKind.CLICK,
            element_id="b1",
            arguments={"op": OP_CLICK},
        )
        validation = validate_grounded_action(action, snap, snap)
        # Prefer coordinate path by clearing AXPress.
        el2 = _el("b1", frame=(100, 200, 40, 20), actions=())
        snap2 = _snap(el2)
        validation = validate_grounded_action(action, snap2, snap2)
        plan = plan_execution(action, snap2, validation=validation)
        self.assertEqual(plan.method, "coordinate_click")
        self.assertEqual(plan.screen_x, 120.0)
        self.assertEqual(plan.screen_y, 210.0)

    def test_execute_dry_run_default(self) -> None:
        el = _el("b1")
        snap = _snap(el)
        action = next(
            a
            for a in enumerate_grounded_actions(
                snap, "x", config=JevConfig(max_candidates=20)
            )
            if a.arguments.get("op") == OP_CLICK
        )
        desktop = MagicMock()
        out = execute_grounded_action(action, snap, desktop=desktop)
        self.assertTrue(out["dry_run"])
        desktop.run_actions.assert_not_called()


class DecisionGateTests(unittest.TestCase):
    def _cfg(self) -> JevConfig:
        return JevConfig(
            min_confidence=0.70,
            min_margin=0.20,
            complete_threshold=0.85,
            stuck_threshold=0.70,
            max_steps=20,
        )

    def test_high_confidence_large_margin_succeeds(self) -> None:
        action = GroundedAction(
            action_id="cand_ok",
            kind=ActionKind.CLICK,
            element_id="b1",
            arguments={"op": OP_CLICK},
        )
        decision = JevDecision(
            selected_candidate_id="cand_ok",
            selected_probability=0.9,
            second_probability=0.05,
            margin=0.85,
            confidence=0.9,
        )
        result = evaluate_decision_gate(decision, [action], self._cfg())
        self.assertTrue(result.allowed)
        self.assertIs(result.action, action)

    def test_low_confidence_and_narrow_margin_fail(self) -> None:
        action = GroundedAction(
            action_id="cand_ok",
            kind=ActionKind.CLICK,
            arguments={"op": OP_CLICK},
        )
        low = JevDecision(
            selected_candidate_id="cand_ok",
            confidence=0.4,
            margin=0.5,
            selected_probability=0.4,
            second_probability=0.1,
        )
        self.assertFalse(evaluate_decision_gate(low, [action], self._cfg()).allowed)
        narrow = JevDecision(
            selected_candidate_id="cand_ok",
            confidence=0.9,
            margin=0.05,
            selected_probability=0.5,
            second_probability=0.45,
        )
        self.assertFalse(evaluate_decision_gate(narrow, [action], self._cfg()).allowed)

    def test_unknown_id_rejected(self) -> None:
        decision = JevDecision(
            selected_candidate_id="cand_missing",
            confidence=0.99,
            margin=0.9,
        )
        result = evaluate_decision_gate(decision, [], self._cfg())
        self.assertFalse(result.allowed)
        self.assertIn("unknown", result.reason)

    def test_stuck_and_completion_behavior(self) -> None:
        done = GroundedAction(
            action_id="cand_done",
            kind=ActionKind.COMPLETE,
            arguments={"op": OP_DONE},
        )
        stuck = JevDecision(
            selected_candidate_id="cand_done",
            confidence=0.99,
            margin=0.9,
            stuck_probability=0.95,
            complete_probability=0.99,
        )
        self.assertFalse(evaluate_decision_gate(stuck, [done], self._cfg()).allowed)

        complete = JevDecision(
            selected_candidate_id="cand_done",
            confidence=0.99,
            margin=0.9,
            stuck_probability=0.1,
            complete_probability=0.99,
        )
        result = evaluate_decision_gate(complete, [done], self._cfg())
        self.assertFalse(result.allowed)
        self.assertTrue(result.requires_verification)

    def test_unsafe_unresolved_rejected(self) -> None:
        from jev.models import JevGateVerdict

        action = GroundedAction(
            action_id="cand_buy",
            kind=ActionKind.CLICK,
            arguments={"op": OP_CLICK},
            requires_confirmation=True,
        )
        decision = JevDecision(
            selected_candidate_id="cand_buy",
            confidence=0.99,
            margin=0.9,
        )
        result = evaluate_decision_gate(
            decision, [action], self._cfg(), confirmed=False
        )
        self.assertFalse(result.allowed)
        self.assertTrue(result.requires_confirmation)
        self.assertTrue(result.allowed_pending_confirmation)
        self.assertEqual(result.verdict, JevGateVerdict.NEEDS_CONFIRMATION)
        ok = evaluate_decision_gate(decision, [action], self._cfg(), confirmed=True)
        self.assertTrue(ok.allowed)

    def test_stale_validation_rejects(self) -> None:
        action = GroundedAction(
            action_id="cand_ok",
            kind=ActionKind.CLICK,
            arguments={"op": OP_CLICK},
        )
        decision = JevDecision(
            selected_candidate_id="cand_ok",
            confidence=0.99,
            margin=0.9,
        )
        from jev.models import ValidationResult

        result = evaluate_decision_gate(
            decision,
            [action],
            self._cfg(),
            validation=ValidationResult(ok=False, reason="element missing"),
        )
        self.assertFalse(result.allowed)
        self.assertIn("stale", result.reason)


if __name__ == "__main__":
    unittest.main()
