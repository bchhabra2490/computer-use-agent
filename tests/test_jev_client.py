"""Offline tests for the TypeSafe Jev client wrapper and shadow evaluator."""

from __future__ import annotations

import math
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from jev.actions import enumerate_grounded_actions
from jev.client import (
    JevClient,
    JevClientStats,
    build_choice_criteria,
    build_jev_state,
    parse_system_one_decision,
    typesafe_sdk_available,
)
from jev.config import JevConfig
from jev.models import (
    ActionKind,
    ElementFrame,
    GroundedAction,
    TokenUsage,
    UIElement,
    UISnapshot,
)
from jev.shadow import run_shadow_evaluation, shadow_evaluation_enabled


def _el(eid: str = "b1", **kwargs) -> UIElement:
    frame = kwargs.pop("frame", (10, 10, 40, 20))
    return UIElement(
        id=eid,
        role=kwargs.get("role", "AXButton"),
        label=kwargs.get("label", "Save"),
        value=kwargs.get("value", ""),
        enabled=kwargs.get("enabled", True),
        sensitive=kwargs.get("sensitive", False),
        focused=kwargs.get("focused", False),
        frame=None if frame is None else ElementFrame(*frame),
        supported_actions=kwargs.get("actions", ("AXPress",)),
    )


def _snap(*elements: UIElement) -> UISnapshot:
    snap = UISnapshot(
        revision=7,
        app_name="Notes",
        bundle_id="com.apple.Notes",
        process_id=42,
        window_title="Doc",
        focused_element_id=elements[0].id if elements else None,
        elements=tuple(elements),
    )
    for el in elements:
        snap.register_handle(el.id, object())
    return snap


def _cfg(**kwargs) -> JevConfig:
    base = dict(
        fast_loop=True,
        shadow_mode=True,
        api_key="ts_test_key_not_for_logging",
        model="jev-latest",
        min_confidence=0.70,
        min_margin=0.20,
        complete_threshold=0.85,
        stuck_threshold=0.70,
        max_steps=20,
        max_candidates=40,
        request_timeout_seconds=3.0,
        max_consecutive_failures=2,
    )
    base.update(kwargs)
    return JevConfig(**base)


def _fake_choice_answer(*, choice: str, confidence: float, probabilities: dict):
    return SimpleNamespace(
        type="choice",
        choice=choice,
        confidence=confidence,
        probabilities=probabilities,
    )


def _fake_noul(value: float):
    return SimpleNamespace(type="noul", noul=value)


def _fake_response(
    *, choice: str, confidence: float, probs: dict, complete=0.1, stuck=0.05
):
    action = _fake_choice_answer(
        choice=choice, confidence=confidence, probabilities=probs
    )
    return SimpleNamespace(
        model="jev-latest",
        usage=SimpleNamespace(input_tokens=11, output_tokens=3),
        answers={
            "action": action,
            "complete": _fake_noul(complete),
            "stuck": _fake_noul(stuck),
        },
        choices={"action": action},
        nouls={"complete": _fake_noul(complete), "stuck": _fake_noul(stuck)},
    )


class AvailabilityTests(unittest.TestCase):
    def test_disabled_config(self) -> None:
        client = JevClient(_cfg(fast_loop=False))
        snap = _snap(_el())
        cands = enumerate_grounded_actions(snap, "save", config=_cfg())
        decision = client.decide(goal="save", snapshot=snap, candidates=cands)
        self.assertEqual(decision.fallback_reason, "jev disabled")
        self.assertNotIn("ts_test_key", repr(decision))

    def test_missing_api_key(self) -> None:
        client = JevClient(_cfg(api_key=""))
        snap = _snap(_el())
        cands = enumerate_grounded_actions(snap, "save", config=_cfg())
        decision = client.decide(goal="save", snapshot=snap, candidates=cands)
        self.assertEqual(decision.fallback_reason, "api key unavailable")

    def test_sdk_missing(self) -> None:
        client = JevClient(_cfg())
        snap = _snap(_el())
        cands = enumerate_grounded_actions(snap, "save", config=_cfg())
        with patch("jev.client._import_sdk", return_value=None):
            decision = client.decide(goal="save", snapshot=snap, candidates=cands)
        self.assertIsNotNone(decision.fallback_reason)
        self.assertTrue(
            decision.fallback_reason.startswith("typesafe-sdk unavailable"),
            decision.fallback_reason,
        )


class StateConstructionTests(unittest.TestCase):
    def test_state_and_choice_criteria(self) -> None:
        secure = _el(
            "p1",
            role="AXSecureTextField",
            label="Password",
            value="",
            sensitive=True,
            actions=("AXConfirm",),
        )
        button = _el("b1", label="Save")
        snap = _snap(button, secure)
        snap.register_handle("b1", object())
        cands = enumerate_grounded_actions(
            snap, 'search for "kites"', config=_cfg(max_candidates=30)
        )
        state = build_jev_state(
            goal='search for "kites"',
            snapshot=snap,
            candidates=cands,
            config=_cfg(),
            step=2,
            url="https://example.com",
        )
        payload = state.to_public_dict()
        self.assertEqual(payload["goal"], 'search for "kites"')
        self.assertEqual(payload["application"], "Notes")
        self.assertEqual(payload["window"], "Doc")
        self.assertEqual(payload["url"], "https://example.com")
        self.assertIn("untrusted", payload["policy_reminder"].lower())
        self.assertEqual(payload["step"], 2)
        # Native handles never appear.
        blob = str(payload)
        self.assertNotIn("_handles", blob)
        # Secure values empty.
        secure_pub = next(e for e in payload["elements"] if e["id"] == "p1")
        self.assertEqual(secure_pub["value"], "")
        self.assertTrue(secure_pub["sensitive"])

        criteria = build_choice_criteria(cands)
        self.assertTrue(criteria)
        for cid, desc in criteria.items():
            self.assertTrue(cid.startswith("cand_"))
            self.assertNotIn("hunter2", desc)
            self.assertIsInstance(desc, str)


class ParseDecisionTests(unittest.TestCase):
    def test_valid_response_parsing(self) -> None:
        action = GroundedAction(
            action_id="cand_a",
            kind=ActionKind.CLICK,
            description="click Save",
            arguments={"op": "click_element"},
        )
        other = GroundedAction(
            action_id="cand_b",
            kind=ActionKind.ESCALATE,
            description="escalate",
            arguments={"op": "escalate"},
        )
        response = _fake_response(
            choice="cand_a",
            confidence=0.91,
            probs={"cand_a": 0.8, "cand_b": 0.15, "noise": 0.05},
            complete=0.12,
            stuck=0.04,
        )
        decision = parse_system_one_decision(
            response, candidates=[action, other], latency_ms=12.5, model="jev-latest"
        )
        self.assertIsNone(decision.error)
        self.assertEqual(decision.selected_candidate_id, "cand_a")
        self.assertAlmostEqual(decision.selected_probability, 0.8)
        self.assertAlmostEqual(decision.second_probability, 0.15)
        self.assertAlmostEqual(decision.margin, 0.65)
        self.assertAlmostEqual(decision.confidence, 0.91)
        self.assertAlmostEqual(decision.complete_probability, 0.12)
        self.assertAlmostEqual(decision.stuck_probability, 0.04)
        self.assertEqual(decision.latency_ms, 12.5)
        self.assertEqual(decision.token_usage.total_tokens, 14)  # type: ignore[union-attr]
        # Bounded to request candidates only.
        self.assertNotIn("noise", decision.distribution)

    def test_unknown_candidate(self) -> None:
        action = GroundedAction(
            action_id="cand_a", kind=ActionKind.CLICK, arguments={"op": "click_element"}
        )
        response = _fake_response(
            choice="cand_missing", confidence=0.9, probs={"cand_missing": 1.0}
        )
        decision = parse_system_one_decision(response, candidates=[action])
        self.assertIn("unknown", decision.error or "")

    def test_malformed_probabilities(self) -> None:
        action = GroundedAction(
            action_id="cand_a", kind=ActionKind.CLICK, arguments={"op": "click_element"}
        )
        response = _fake_response(
            choice="cand_a", confidence=0.9, probs={"cand_a": math.nan}
        )
        decision = parse_system_one_decision(response, candidates=[action])
        self.assertIn("invalid probability", decision.error or "")

        empty = _fake_response(choice="cand_a", confidence=0.9, probs={})
        empty.choices["action"].probabilities = {}
        decision = parse_system_one_decision(empty, candidates=[action])
        self.assertIn("empty probability", decision.error or "")

    def test_invalid_confidence(self) -> None:
        action = GroundedAction(
            action_id="cand_a", kind=ActionKind.CLICK, arguments={"op": "click_element"}
        )
        response = _fake_response(
            choice="cand_a", confidence=1.5, probs={"cand_a": 1.0}
        )
        decision = parse_system_one_decision(response, candidates=[action])
        self.assertIn("confidence", decision.error or "")

    def test_complete_stuck_and_usage(self) -> None:
        action = GroundedAction(
            action_id="cand_a", kind=ActionKind.COMPLETE, arguments={"op": "done"}
        )
        response = _fake_response(
            choice="cand_a",
            confidence=0.95,
            probs={"cand_a": 1.0},
            complete=0.97,
            stuck=0.02,
        )
        decision = parse_system_one_decision(
            response, candidates=[action], latency_ms=9.0
        )
        self.assertAlmostEqual(decision.complete_probability, 0.97)
        self.assertAlmostEqual(decision.stuck_probability, 0.02)
        self.assertEqual(decision.token_usage.input_tokens, 11)  # type: ignore[union-attr]


class ClientCallTests(unittest.TestCase):
    def test_decide_with_injected_system_one(self) -> None:
        snap = _snap(_el("b1"))
        cands = enumerate_grounded_actions(snap, "click save", config=_cfg())
        click = next(c for c in cands if c.arguments.get("op") == "click_element")
        probs = {
            c.action_id: (0.7 if c.action_id == click.action_id else 0.01)
            for c in cands
        }
        # Normalize a bit for runner-up.
        for c in cands:
            if c.action_id != click.action_id:
                probs[c.action_id] = 0.05
                break
        response = _fake_response(
            choice=click.action_id,
            confidence=0.88,
            probs=probs,
            complete=0.1,
            stuck=0.1,
        )
        seen = {}

        def fake_system_one(state, questions, **kwargs):
            seen["state"] = state
            seen["questions"] = questions
            seen["kwargs"] = kwargs
            return response

        # Provide a minimal sdk stub so Choice/Noul constructors work.
        class FakeChoice:
            def __init__(self, *, instructions=None, criteria=None, type="choice"):
                self.instructions = instructions
                self.criteria = criteria
                self.type = type

        class FakeNoul:
            def __init__(self, *, instructions=None, type="noul", criteria=None):
                self.instructions = instructions
                self.type = type

        sdk = {
            "Choice": FakeChoice,
            "Noul": FakeNoul,
            "RetryPolicy": MagicMock(),
            "TypeSafeClient": MagicMock(),
            "TypeSafeAPIError": Exception,
            "TypeSafeAPITimeoutError": Exception,
            "TypeSafeError": Exception,
        }
        client = JevClient(_cfg(), sdk_client=MagicMock())
        with patch("jev.client._import_sdk", return_value=sdk):
            decision = client.decide(
                goal="click save",
                snapshot=snap,
                candidates=cands,
                system_one=fake_system_one,
            )
        self.assertIsNone(decision.error)
        self.assertEqual(decision.selected_candidate_id, click.action_id)
        self.assertIn("policy_reminder", seen["state"])
        self.assertIn("action", seen["questions"])
        self.assertIn("complete", seen["questions"])
        self.assertIn("stuck", seen["questions"])
        # Candidate descriptions present; no native handles.
        criteria = seen["questions"]["action"].criteria
        self.assertIn(click.action_id, criteria)
        self.assertNotIn("_handles", str(seen["state"]))
        self.assertNotIn("ts_test_key", str(seen))

    def test_timeout_provider_error(self) -> None:
        snap = _snap(_el())
        cands = enumerate_grounded_actions(snap, "x", config=_cfg())

        class TimeoutErr(Exception):
            pass

        def boom(*args, **kwargs):
            raise TimeoutErr("timed out")

        class FakeChoice:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        class FakeNoul:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        sdk = {
            "Choice": FakeChoice,
            "Noul": FakeNoul,
            "RetryPolicy": MagicMock(),
            "TypeSafeClient": MagicMock(),
            "TypeSafeAPIError": Exception,
            "TypeSafeAPITimeoutError": TimeoutErr,
            "TypeSafeError": Exception,
        }
        client = JevClient(_cfg(), sdk_client=MagicMock(), stats=JevClientStats())
        with patch("jev.client._import_sdk", return_value=sdk):
            decision = client.decide(
                goal="x", snapshot=snap, candidates=cands, system_one=boom
            )
        self.assertEqual(decision.fallback_reason, "request timeout")
        self.assertEqual(client.stats.consecutive_failures, 1)


class ShadowModeTests(unittest.TestCase):
    def test_shadow_never_calls_executor(self) -> None:
        snap = _snap(_el("b1"))
        cands = enumerate_grounded_actions(snap, "click", config=_cfg())
        click = next(c for c in cands if c.arguments.get("op") == "click_element")
        probs = {c.action_id: 0.02 for c in cands}
        probs[click.action_id] = 0.8
        response = _fake_response(choice=click.action_id, confidence=0.9, probs=probs)

        class FakeChoice:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        class FakeNoul:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        sdk = {
            "Choice": FakeChoice,
            "Noul": FakeNoul,
            "RetryPolicy": MagicMock(),
            "TypeSafeClient": MagicMock(),
            "TypeSafeAPIError": Exception,
            "TypeSafeAPITimeoutError": Exception,
            "TypeSafeError": Exception,
        }

        def fake_system_one(state, questions, **kwargs):
            return response

        executor = MagicMock()
        log = MagicMock()
        client = JevClient(_cfg(), sdk_client=MagicMock())
        with (
            patch("jev.client._import_sdk", return_value=sdk),
            patch.object(client, "decide", wraps=None) as decide_mock,
        ):
            # Drive through decide via patched system_one on a fresh client.
            pass

        client = JevClient(_cfg(), sdk_client=MagicMock())
        with patch("jev.client._import_sdk", return_value=sdk):
            # Patch decide on the class used inside shadow by injecting client.
            decision = client.decide(
                goal="click",
                snapshot=snap,
                candidates=cands,
                system_one=fake_system_one,
            )
            client.decide = MagicMock(return_value=decision)  # type: ignore[method-assign]
            result = run_shadow_evaluation(
                goal="click",
                snapshot=snap,
                config=_cfg(),
                client=client,
                log=log,
                executor=executor,
            )
        executor.assert_not_called()
        self.assertIn(result.status, {"shadowed", "fallback", "rejected"})
        log.record.assert_called()
        kind = log.record.call_args[0][0]
        self.assertEqual(kind, "jev_decision")
        payload = log.record.call_args[0][2]
        self.assertNotIn("ts_test_key", str(payload))
        self.assertIn("confidence", payload)

    def test_disabled_path_unchanged(self) -> None:
        self.assertFalse(shadow_evaluation_enabled(_cfg(fast_loop=False)))
        snap = _snap(_el())
        result = run_shadow_evaluation(
            goal="x", snapshot=snap, config=_cfg(fast_loop=False)
        )
        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.decision.fallback_reason, "jev disabled")

    def test_typesafe_sdk_available_helper(self) -> None:
        # May be True or False depending on the environment; must not raise.
        self.assertIsInstance(typesafe_sdk_available(), bool)


if __name__ == "__main__":
    unittest.main()
