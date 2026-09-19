"""Offline tests for the agent-facing jev_choose tool."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from jev.choose import (
    advisory_candidates_from_options,
    inject_pseudo_options,
    normalize_agent_options,
    recommendation_from_decision,
    run_jev_choose,
    run_jev_choose_tool,
)
from jev.config import JevConfig, jev_choose_tool_enabled, load_jev_config
from jev.models import ActionKind, JevDecision


def _cfg(**kwargs) -> JevConfig:
    base = dict(
        fast_loop=False,
        shadow_mode=True,
        choose_tool=True,
        api_key="k",
        model="jev-latest",
        min_confidence=0.70,
        min_margin=0.20,
        complete_threshold=0.85,
        stuck_threshold=0.70,
        max_steps=20,
        max_candidates=220,
        request_timeout_seconds=3.0,
        max_consecutive_failures=2,
    )
    base.update(kwargs)
    return JevConfig(**base)


class NormalizeOptionsTests(unittest.TestCase):
    def test_ok_pair(self) -> None:
        pairs, err = normalize_agent_options(
            [
                {"id": "ewr", "description": "Newark Liberty (EWR)"},
                {"id": "del", "description": "New Delhi (DEL)"},
            ]
        )
        self.assertIsNone(err)
        self.assertEqual(len(pairs), 2)

    def test_requires_two(self) -> None:
        pairs, err = normalize_agent_options(
            [{"id": "only", "description": "one"}]
        )
        self.assertEqual(pairs, [])
        self.assertIn("at least 2", err or "")

    def test_bad_id(self) -> None:
        _, err = normalize_agent_options(
            [
                {"id": "bad id!", "description": "x"},
                {"id": "ok", "description": "y"},
            ]
        )
        self.assertIn("id must be", err or "")

    def test_advisory_candidates(self) -> None:
        cands = advisory_candidates_from_options(
            [("a", "Alpha"), ("b", "Beta")]
        )
        self.assertEqual(cands[0].kind, ActionKind.NOOP)
        self.assertEqual(cands[0].arguments.get("op"), "advisory_choice")


class RecommendationTests(unittest.TestCase):
    def test_stuck_use_vision(self) -> None:
        d = JevDecision(
            selected_candidate_id="a",
            confidence=0.95,
            margin=0.5,
            stuck_probability=0.9,
            complete_probability=0.1,
        )
        rec, _ = recommendation_from_decision(d, config=_cfg())
        self.assertEqual(rec, "use_vision")

    def test_inject_pseudos(self) -> None:
        pairs = inject_pseudo_options(
            [("ewr", "Newark"), ("del", "Delhi")]
        )
        ids = {oid for oid, _ in pairs}
        self.assertIn("ask_user", ids)
        self.assertIn("use_vision", ids)
        self.assertIn("stuck", ids)
        self.assertIn("done", ids)

    def test_payment_ask_user(self) -> None:
        d = JevDecision(
            selected_candidate_id="pay",
            confidence=0.95,
            margin=0.5,
            stuck_probability=0.1,
            complete_probability=0.1,
        )
        rec, _ = recommendation_from_decision(
            d, config=_cfg(), selected_description="Click Pay now"
        )
        self.assertEqual(rec, "ask_user")

    def test_destructive_noul_ask_user(self) -> None:
        d = JevDecision(
            selected_candidate_id="btn",
            confidence=0.95,
            margin=0.5,
            stuck_probability=0.1,
            complete_probability=0.1,
            is_destructive_probability=0.8,
        )
        rec, _ = recommendation_from_decision(
            d, config=_cfg(), selected_description="OK", goal="open settings"
        )
        self.assertEqual(rec, "ask_user")


class RunJevChooseTests(unittest.TestCase):
    def test_disabled_tool(self) -> None:
        out = run_jev_choose(
            goal="pick airport",
            options=[
                {"id": "ewr", "description": "Newark"},
                {"id": "del", "description": "Delhi"},
            ],
            config=_cfg(choose_tool=False),
        )
        self.assertFalse(out["ok"])
        self.assertIn("disabled", out.get("error") or "")

    def test_privacy_bypass(self) -> None:
        out = run_jev_choose(
            goal="enter password hunter2 on the form",
            options=[
                {"id": "a", "description": "type it"},
                {"id": "b", "description": "ask_user"},
            ],
            config=_cfg(),
        )
        self.assertFalse(out["ok"])

    def test_mocked_choice(self) -> None:
        def fake_system_one(state, questions, **kwargs):
            del state, kwargs
            action_q = questions["action"]
            criteria = (
                action_q["criteria"]
                if isinstance(action_q, dict)
                else dict(action_q.criteria)
            )
            probs = {cid: 0.1 for cid in criteria}
            probs["ewr"] = 0.8
            return SimpleNamespace(
                choices={
                    "action": SimpleNamespace(
                        choice="ewr",
                        confidence=0.9,
                        probabilities=probs,
                    )
                },
                nouls={
                    "complete": SimpleNamespace(noul=0.05),
                    "stuck": SimpleNamespace(noul=0.1),
                },
                answers={},
                usage=None,
                model="jev-latest",
            )

        out = run_jev_choose(
            goal="Choose origin airport for New Jersey to Bangalore",
            options=[
                {"id": "ewr", "description": "Newark Liberty (EWR)"},
                {"id": "del", "description": "New Delhi (DEL)"},
                {"id": "ask_user", "description": "ask_user to clarify origin"},
            ],
            source="agent",
            config=_cfg(),
            system_one=fake_system_one,
        )
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["selected_id"], "ewr")
        self.assertEqual(out["recommendation"], "proceed")
        self.assertTrue(out["execute_yourself"])
        self.assertEqual(out["source"], "agent")
        self.assertGreaterEqual(out["option_count"], 4)  # + pseudos if missing

    def test_tool_handler_json(self) -> None:
        with patch(
            "jev.choose.run_jev_choose",
            return_value={
                "ok": True,
                "selected_id": "ewr",
                "recommendation": "proceed",
                "advisory": True,
                "execute_yourself": True,
            },
        ):
            raw = run_jev_choose_tool(
                {
                    "goal": "pick",
                    "source": "agent",
                    "options": [
                        {"id": "ewr", "description": "Newark"},
                        {"id": "del", "description": "Delhi"},
                    ],
                    "subgoal": None,
                    "app": None,
                    "window": None,
                    "url": None,
                }
            )
        data = json.loads(raw)
        self.assertTrue(data["ok"])
        self.assertEqual(data["selected_id"], "ewr")


class ConfigChooseToolTests(unittest.TestCase):
    def test_default_on(self) -> None:
        cfg = load_jev_config({})
        self.assertTrue(cfg.choose_tool)
        self.assertTrue(jev_choose_tool_enabled(cfg))

    def test_can_disable(self) -> None:
        cfg = load_jev_config({"JEV_CHOOSE_TOOL": "0"})
        self.assertFalse(cfg.choose_tool)


if __name__ == "__main__":
    unittest.main()
