"""Unit tests for Jev configuration parsing (no process env mutation)."""

from __future__ import annotations

import os
import unittest

from jev.config import JevConfig, api_key_status, load_jev_config


class JevConfigDefaultsTests(unittest.TestCase):
    def test_disabled_by_default(self) -> None:
        cfg = load_jev_config({})
        self.assertFalse(cfg.fast_loop)
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.api_key_status, "unavailable")

    def test_shadow_mode_defaults_on(self) -> None:
        cfg = load_jev_config({})
        self.assertTrue(cfg.shadow_mode)

    def test_missing_api_key_is_unavailable(self) -> None:
        self.assertEqual(api_key_status({}), "unavailable")
        self.assertEqual(api_key_status({"TYPESAFE_API_KEY": ""}), "unavailable")
        self.assertEqual(api_key_status({"TYPESAFE_API_KEY": "   "}), "unavailable")
        cfg = load_jev_config({"JEV_FAST_LOOP": "1"})
        self.assertEqual(cfg.api_key_status, "unavailable")
        self.assertFalse(cfg.enabled)

    def test_default_numeric_and_model_values(self) -> None:
        cfg = load_jev_config({})
        self.assertEqual(cfg.model, "jev-latest")
        self.assertAlmostEqual(cfg.min_confidence, 0.70)
        self.assertAlmostEqual(cfg.min_margin, 0.20)
        self.assertAlmostEqual(cfg.complete_threshold, 0.85)
        self.assertAlmostEqual(cfg.stuck_threshold, 0.70)
        self.assertEqual(cfg.max_steps, 20)
        self.assertEqual(cfg.max_candidates, 220)
        self.assertAlmostEqual(cfg.request_timeout_seconds, 3.0)
        self.assertEqual(cfg.max_consecutive_failures, 2)


class JevConfigEnablementTests(unittest.TestCase):
    def test_explicit_enable_requires_key(self) -> None:
        cfg = load_jev_config(
            {
                "JEV_FAST_LOOP": "1",
                "TYPESAFE_API_KEY": "ts_test_key",
                "JEV_SHADOW_MODE": "0",
            }
        )
        self.assertTrue(cfg.fast_loop)
        self.assertFalse(cfg.shadow_mode)
        self.assertTrue(cfg.has_api_key)
        self.assertEqual(cfg.api_key_status, "available")
        self.assertTrue(cfg.enabled)

    def test_truthy_aliases(self) -> None:
        for value in ("1", "true", "TRUE", "yes", "on"):
            cfg = load_jev_config({"JEV_FAST_LOOP": value, "TYPESAFE_API_KEY": "k"})
            self.assertTrue(cfg.fast_loop, value)

    def test_falsey_aliases(self) -> None:
        for value in ("0", "false", "no", "off", ""):
            cfg = load_jev_config({"JEV_FAST_LOOP": value, "TYPESAFE_API_KEY": "k"})
            self.assertFalse(cfg.fast_loop, value)


class JevConfigValidationTests(unittest.TestCase):
    def test_invalid_floats_fall_back_then_clamp(self) -> None:
        cfg = load_jev_config(
            {
                "JEV_MIN_CONFIDENCE": "not-a-float",
                "JEV_MIN_MARGIN": "abc",
                "JEV_COMPLETE_THRESHOLD": "",
                "JEV_STUCK_THRESHOLD": "NaN",
                "JEV_REQUEST_TIMEOUT_SECONDS": "oops",
            }
        )
        self.assertAlmostEqual(cfg.min_confidence, 0.70)
        self.assertAlmostEqual(cfg.min_margin, 0.20)
        self.assertAlmostEqual(cfg.complete_threshold, 0.85)
        # NaN clamps to the low bound of [0, 1].
        self.assertAlmostEqual(cfg.stuck_threshold, 0.0)
        self.assertAlmostEqual(cfg.request_timeout_seconds, 3.0)

    def test_invalid_integers_fall_back(self) -> None:
        cfg = load_jev_config(
            {
                "JEV_MAX_STEPS": "nope",
                "JEV_MAX_CANDIDATES": "x",
                "JEV_MAX_CONSECUTIVE_FAILURES": "bad",
            }
        )
        self.assertEqual(cfg.max_steps, 20)
        self.assertEqual(cfg.max_candidates, 220)
        self.assertEqual(cfg.max_consecutive_failures, 2)

    def test_confidence_thresholds_clamped_to_unit_interval(self) -> None:
        cfg = load_jev_config(
            {
                "JEV_MIN_CONFIDENCE": "-1",
                "JEV_MIN_MARGIN": "2.5",
                "JEV_COMPLETE_THRESHOLD": "1.5",
                "JEV_STUCK_THRESHOLD": "-0.2",
            }
        )
        self.assertAlmostEqual(cfg.min_confidence, 0.0)
        self.assertAlmostEqual(cfg.min_margin, 1.0)
        self.assertAlmostEqual(cfg.complete_threshold, 1.0)
        self.assertAlmostEqual(cfg.stuck_threshold, 0.0)

    def test_candidate_and_step_bounds(self) -> None:
        low = load_jev_config(
            {
                "JEV_MAX_STEPS": "0",
                "JEV_MAX_CANDIDATES": "-5",
                "JEV_MAX_CONSECUTIVE_FAILURES": "-1",
                "JEV_REQUEST_TIMEOUT_SECONDS": "0",
            }
        )
        self.assertEqual(low.max_steps, 1)
        self.assertEqual(low.max_candidates, 1)
        self.assertEqual(low.max_consecutive_failures, 0)
        self.assertAlmostEqual(low.request_timeout_seconds, 0.1)

        high = load_jev_config(
            {
                "JEV_MAX_STEPS": "9999",
                "JEV_MAX_CANDIDATES": "99999",
                "JEV_MAX_CONSECUTIVE_FAILURES": "999",
                "JEV_REQUEST_TIMEOUT_SECONDS": "999",
            }
        )
        self.assertEqual(high.max_steps, 200)
        self.assertEqual(high.max_candidates, 253)
        self.assertEqual(high.max_consecutive_failures, 20)
        self.assertAlmostEqual(high.request_timeout_seconds, 60.0)

    def test_choice_hard_ceiling_constant(self) -> None:
        from jev.config import JEV_CHOICE_MAX_OPTIONS, JEV_MAX_CANDIDATES_HARD_CEILING

        self.assertEqual(JEV_CHOICE_MAX_OPTIONS, 255)
        self.assertEqual(JEV_MAX_CANDIDATES_HARD_CEILING, 253)
        self.assertLessEqual(JEV_MAX_CANDIDATES_HARD_CEILING, JEV_CHOICE_MAX_OPTIONS)


class JevConfigSecretSafetyTests(unittest.TestCase):
    def test_api_key_never_in_repr_or_public_dict(self) -> None:
        secret = "ts_super_secret_key_do_not_leak"
        cfg = load_jev_config(
            {
                "JEV_FAST_LOOP": "1",
                "TYPESAFE_API_KEY": secret,
            }
        )
        text = repr(cfg)
        self.assertNotIn(secret, text)
        self.assertIn("api_key_status='available'", text)
        public = cfg.to_public_dict()
        self.assertNotIn("api_key", public)
        self.assertNotIn(secret, str(public))
        self.assertEqual(public["api_key_status"], "available")
        self.assertTrue(public["enabled"])

    def test_does_not_require_mutating_os_environ(self) -> None:
        before = dict(os.environ)
        load_jev_config({"JEV_FAST_LOOP": "1", "TYPESAFE_API_KEY": "k"})
        self.assertEqual(dict(os.environ), before)

    def test_dataclass_construction(self) -> None:
        cfg = JevConfig(fast_loop=True, api_key="x")
        self.assertTrue(cfg.enabled)
        self.assertIn("unavailable", repr(JevConfig()))


if __name__ == "__main__":
    unittest.main()
