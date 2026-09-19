"""Step-6 acceptance checks for Jev integration (offline, no live API/desktop)."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from jev.actions import enumerate_grounded_actions
from jev.client import build_jev_state, typesafe_sdk_available
from jev.config import load_jev_config
from jev.diagnostics import scrub_for_logs
from jev.loop import run_jev_fast_loop
from jev.models import (
    ActionKind,
    ElementFrame,
    GroundedAction,
    JevDecision,
    JevLoopStatus,
    UIElement,
    UISnapshot,
)


ROOT = Path(__file__).resolve().parents[1]


def _el(eid: str = "btn") -> UIElement:
    return UIElement(
        id=eid,
        role="AXButton",
        label="Save",
        frame=ElementFrame(10, 10, 80, 24),
        supported_actions=("AXPress",),
    )


def _snap(*els: UIElement) -> UISnapshot:
    snap = UISnapshot(
        revision=1,
        app_name="Notes",
        process_id=1,
        window_title="Doc",
        elements=tuple(els) or (_el(),),
    )
    for el in snap.elements:
        snap.register_handle(el.id, object())
    return snap


class AcceptanceAuditTests(unittest.TestCase):
    def test_fast_loop_off_preserves_disabled(self) -> None:
        cfg = load_jev_config({"JEV_FAST_LOOP": "0", "TYPESAFE_API_KEY": "x"})
        out = run_jev_fast_loop(task="click Save", config=cfg)
        self.assertEqual(out.status, JevLoopStatus.DISABLED)

    def test_missing_key_active_falls_back_cleanly(self) -> None:
        cfg = load_jev_config(
            {
                "JEV_FAST_LOOP": "1",
                "JEV_SHADOW_MODE": "0",
                "TYPESAFE_API_KEY": "",
            }
        )
        out = run_jev_fast_loop(task="click Save", config=cfg)
        self.assertEqual(out.status, JevLoopStatus.UNAVAILABLE)
        self.assertIn("api key", out.reason.lower())

    def test_shadow_never_executes(self) -> None:
        snap = _snap()
        cands = enumerate_grounded_actions(snap, "click Save")
        click = next(c for c in cands if c.arguments.get("op") == "click_element")

        class Fake:
            def decide(self, **kwargs):
                return JevDecision(
                    selected_candidate_id=click.action_id,
                    confidence=0.99,
                    margin=0.5,
                    selected_probability=0.8,
                    second_probability=0.2,
                )

            def close(self):
                pass

        exec_fn = MagicMock()
        out = run_jev_fast_loop(
            task="click Save",
            config=load_jev_config(
                {
                    "JEV_FAST_LOOP": "1",
                    "JEV_SHADOW_MODE": "1",
                    "TYPESAFE_API_KEY": "test-not-real",
                }
            ),
            client=Fake(),  # type: ignore[arg-type]
            capture_snapshot=lambda: snap,
            execute_fn=exec_fn,
        )
        self.assertEqual(out.status, JevLoopStatus.SHADOW_COMPLETE)
        exec_fn.assert_not_called()

    def test_sensitive_values_not_in_jev_state(self) -> None:
        field = UIElement(
            id="pw",
            role="AXTextField",
            label="Password",
            value="hunter2-secret",
            sensitive=True,
            frame=ElementFrame(1, 1, 40, 20),
        )
        snap = _snap(field)
        cfg = load_jev_config({"JEV_FAST_LOOP": "1", "TYPESAFE_API_KEY": "x"})
        state = build_jev_state(
            goal="login",
            snapshot=snap,
            candidates=(),
            config=cfg,
        )
        blob = str(state.to_public_dict())
        self.assertNotIn("hunter2-secret", blob)

    def test_logs_scrub_api_keys(self) -> None:
        cleaned = scrub_for_logs({"TYPESAFE_API_KEY": "sk-abc", "ok": True})
        self.assertEqual(cleaned["TYPESAFE_API_KEY"], "[redacted]")

    def test_sdk_import_is_lazy(self) -> None:
        # typesafe_sdk_available must not raise; optional package may be absent.
        self.assertIsInstance(typesafe_sdk_available(), bool)

    def test_client_module_has_no_eager_typesafe_import(self) -> None:
        tree = ast.parse((ROOT / "jev" / "client.py").read_text())
        for node in tree.body:
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("typesafe")
            ):
                self.fail("top-level typesafe import couples optional SDK")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("typesafe"):
                        self.fail("top-level typesafe import couples optional SDK")

    def test_agent_wires_after_recipes_only_when_enabled(self) -> None:
        src = (ROOT / "agent.py").read_text()
        body_start = src.index("def _run_agent_session(")
        body_end = src.index("\ndef _bootstrap_agent_run(", body_start)
        body = src[body_start:body_end]
        self.assertIn("jev_fast_loop_enabled", body)
        self.assertLess(
            body.index("_apply_recipe_start"), body.index("run_jev_fast_loop")
        )


if __name__ == "__main__":
    unittest.main()
