"""Unit tests for Jev typed domain models (no TypeSafe SDK)."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from jev.models import (
    ActionKind,
    ElementFrame,
    GroundedAction,
    JevDecision,
    JevGateResult,
    JevGateVerdict,
    JevLoopResult,
    JevLoopStatus,
    TokenUsage,
    UIElement,
    UISnapshot,
)


class UIElementTests(unittest.TestCase):
    def test_sensitive_value_redacted_in_repr_and_public_dict(self) -> None:
        el = UIElement(
            id="e1",
            role="AXSecureTextField",
            label="Password",
            value="hunter2",
            sensitive=True,
            supported_actions=("set_value", "focus"),
        )
        self.assertNotIn("hunter2", repr(el))
        self.assertIn("[sensitive]", repr(el))
        public = el.to_public_dict()
        self.assertEqual(public["value"], "")
        self.assertTrue(public["sensitive"])
        self.assertEqual(el.safe_value(), "")

    def test_non_sensitive_value_preserved(self) -> None:
        el = UIElement(id="e2", role="AXButton", label="Save", value="Save")
        self.assertIn("Save", repr(el))
        self.assertEqual(el.to_public_dict()["value"], "Save")


class UISnapshotTests(unittest.TestCase):
    def test_native_handles_excluded_from_public_state(self) -> None:
        native = object()
        snap = UISnapshot(
            revision=3,
            captured_at=datetime(2026, 9, 19, 7, 0, tzinfo=timezone.utc),
            app_name="Safari",
            bundle_id="com.apple.Safari",
            process_id=1234,
            window_title="Home",
            focused_element_id="e1",
            elements=(
                UIElement(
                    id="e1",
                    role="AXButton",
                    label="Go",
                    frame=ElementFrame(10, 20, 80, 30),
                    supported_actions=("click",),
                ),
            ),
        )
        snap.register_handle("e1", native)
        self.assertIs(snap.get_handle("e1"), native)
        self.assertEqual(snap.handle_count, 1)

        public = snap.to_public_dict()
        payload = json.dumps(public)
        self.assertNotIn("_handles", public)
        self.assertNotIn("handles", public)
        self.assertNotIn(str(id(native)), payload)
        self.assertEqual(public["revision"], 3)
        self.assertEqual(public["app_name"], "Safari")
        self.assertEqual(public["elements"][0]["id"], "e1")
        self.assertEqual(public["elements"][0]["frame"]["width"], 80.0)
        self.assertTrue(public["available"])
        self.assertEqual(public["error"], "")

        # repr must not dump the native object identity in a serializable way
        self.assertNotIn("_handles", repr(snap))

    def test_register_handle_requires_id(self) -> None:
        snap = UISnapshot()
        with self.assertRaises(ValueError):
            snap.register_handle("", object())


class GroundedActionTests(unittest.TestCase):
    def test_construction_and_kind_coercion(self) -> None:
        action = GroundedAction(
            action_id="a1",
            kind="click",
            element_id="e1",
            description="Click Go",
            arguments={"button": "left"},
        )
        self.assertIs(action.kind, ActionKind.CLICK)
        self.assertEqual(action.to_public_dict()["kind"], "click")

    def test_sensitive_arguments_redacted(self) -> None:
        action = GroundedAction(
            action_id="a2",
            kind=ActionKind.TYPE,
            element_id="e-pass",
            description="Type into password field",
            arguments={"text": "hunter2"},
            sensitive=True,
            requires_confirmation=True,
        )
        self.assertNotIn("hunter2", repr(action))
        public = action.to_public_dict()
        self.assertEqual(public["arguments"]["text"], "[sensitive]")
        self.assertTrue(public["requires_confirmation"])


class JevDecisionAndGateTests(unittest.TestCase):
    def test_decision_construction(self) -> None:
        decision = JevDecision(
            selected_candidate_id="c1",
            selected_probability=0.82,
            second_probability=0.11,
            margin=0.71,
            confidence=0.82,
            complete_probability=0.05,
            stuck_probability=0.02,
            distribution={"c1": 0.82, "c2": 0.11, "noop": 0.07},
            model="jev-latest",
            latency_ms=42.5,
            token_usage=TokenUsage(input_tokens=10, output_tokens=2, total_tokens=12),
        )
        public = decision.to_public_dict()
        self.assertEqual(public["selected_candidate_id"], "c1")
        self.assertAlmostEqual(public["margin"], 0.71)
        self.assertEqual(public["token_usage"]["total_tokens"], 12)
        self.assertIsNone(public["error"])

    def test_gate_may_execute(self) -> None:
        allow = JevGateResult(
            verdict=JevGateVerdict.ALLOW,
            reason="confidence ok",
            shadow=False,
            config_enabled=True,
        )
        self.assertTrue(allow.may_execute)
        shadow = JevGateResult(
            verdict="shadow",
            reason="shadow mode",
            shadow=True,
            config_enabled=True,
        )
        self.assertFalse(shadow.may_execute)
        self.assertEqual(shadow.to_public_dict()["verdict"], "shadow")


class JevLoopResultTests(unittest.TestCase):
    def test_loop_result_public_dict(self) -> None:
        result = JevLoopResult(
            status=JevLoopStatus.FALLBACK,
            steps=2,
            gate=JevGateResult(
                verdict=JevGateVerdict.FALLBACK,
                reason="below confidence",
                config_enabled=True,
            ),
            decision=JevDecision(
                selected_candidate_id="c9",
                confidence=0.4,
                fallback_reason="low confidence",
            ),
            actions=(
                GroundedAction(
                    action_id="a1",
                    kind=ActionKind.NOOP,
                    description="No-op",
                ),
            ),
            reason="hand off to vision agent",
            snapshot_revision=7,
        )
        public = result.to_public_dict()
        self.assertEqual(public["status"], "fallback")
        self.assertEqual(public["steps"], 2)
        self.assertEqual(public["snapshot_revision"], 7)
        self.assertEqual(public["actions"][0]["kind"], "noop")
        # Must be JSON-serializable for TaskLog later.
        json.dumps(public)


if __name__ == "__main__":
    unittest.main()
