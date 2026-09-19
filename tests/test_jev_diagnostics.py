"""Diagnostics scrubbing and session summary (no network / desktop)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from jev.diagnostics import (
    JevSessionStats,
    record_jev_session_summary,
    scrub_for_logs,
)


class ScrubTests(unittest.TestCase):
    def test_redacts_secret_keys(self) -> None:
        payload = scrub_for_logs(
            {
                "status": "ok",
                "api_key": "sk-live-should-not-appear",
                "TYPESAFE_API_KEY": "secret",
                "nested": {"password": "hunter2", "label": "Save"},
            }
        )
        self.assertEqual(payload["api_key"], "[redacted]")
        self.assertEqual(payload["TYPESAFE_API_KEY"], "[redacted]")
        self.assertEqual(payload["nested"]["password"], "[redacted]")
        self.assertEqual(payload["nested"]["label"], "Save")
        blob = str(payload)
        self.assertNotIn("sk-live", blob)
        self.assertNotIn("hunter2", blob)

    def test_redacts_inline_secret_assignment(self) -> None:
        text = scrub_for_logs("typesafe_api_key=abc123 password: hunter2")
        self.assertNotIn("abc123", text)
        self.assertNotIn("hunter2", text)


class SessionStatsTests(unittest.TestCase):
    def test_rates_and_public_dict(self) -> None:
        stats = JevSessionStats(
            mode="active",
            decisions=4,
            executed=2,
            fallbacks=1,
            no_effect=1,
            safety_rejects=1,
            outcome="fallback",
            outcome_reason="confidence below minimum",
        )
        public = stats.to_public_dict()
        self.assertEqual(public["mode"], "active")
        self.assertEqual(public["rates"]["fallback_rate"], 0.25)
        self.assertNotIn("api_key", public)

    def test_record_session_summary(self) -> None:
        log = MagicMock()
        stats = JevSessionStats(mode="shadow", decisions=1, outcome="shadow_complete")
        record_jev_session_summary(log, stats)
        log.record.assert_called_once()
        args = log.record.call_args[0]
        self.assertEqual(args[0], "jev_session")
        self.assertNotIn("TYPESAFE", str(args))


if __name__ == "__main__":
    unittest.main()
