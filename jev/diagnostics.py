"""Lightweight Jev diagnostics — TaskLog + latency_report only.

No separate monitoring stack. Payloads are public/safe: never include API keys,
native AX handles, or secure-field values.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|typesafe|password|passwd|secret|token|credential|otp|cvv)",
    re.IGNORECASE,
)
_SECRET_VALUE_RE = re.compile(
    r"(?i)(api[_-]?key|typesafe_api_key|password|secret|token)\s*[:=]\s*\S+"
)


def scrub_for_logs(value: Any, *, depth: int = 0) -> Any:
    """Recursively drop/redact keys that look like secrets."""
    if depth > 6:
        return "[truncated]"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_s = str(key)
            if _SECRET_KEY_RE.search(key_s):
                out[key_s] = "[redacted]"
            else:
                out[key_s] = scrub_for_logs(item, depth=depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [scrub_for_logs(v, depth=depth + 1) for v in value]
    if isinstance(value, str):
        if _SECRET_VALUE_RE.search(value):
            return _SECRET_VALUE_RE.sub(r"\1=[redacted]", value)
        return value
    return value


@dataclass
class JevSessionStats:
    """Aggregate counters for one fast-loop attempt (shadow or active)."""

    mode: str = "disabled"
    decisions: int = 0
    executed: int = 0
    fallbacks: int = 0
    no_effect: int = 0
    repeated_action: int = 0
    safety_rejects: int = 0
    provider_failures: int = 0
    freshness_rejects: int = 0
    wait_ms_total: float = 0.0
    loop_wall_ms: float | None = None
    time_to_first_action_ms: float | None = None
    outcome: str = ""
    outcome_reason: str = ""
    timings_ms: list[dict[str, float | None]] = field(default_factory=list)

    def note_timing(self, **kwargs: float | None) -> None:
        self.timings_ms.append({k: v for k, v in kwargs.items()})

    def rates(self) -> dict[str, float | None]:
        d = max(1, self.decisions)
        e = max(1, self.executed) if self.executed else 0

        def _rate(num: int, den: int) -> float | None:
            if den <= 0:
                return None
            return round(num / den, 4)

        return {
            "fallback_rate": _rate(self.fallbacks, d),
            "no_effect_rate": _rate(self.no_effect, e if e else d),
            "repeated_action_rate": _rate(self.repeated_action, d),
            "safety_reject_rate": _rate(self.safety_rejects, d),
            "provider_failure_rate": _rate(self.provider_failures, d),
            "freshness_reject_rate": _rate(self.freshness_rejects, d),
        }

    def to_public_dict(self) -> dict[str, Any]:
        return scrub_for_logs(
            {
                "mode": self.mode,
                "decisions": self.decisions,
                "executed": self.executed,
                "fallbacks": self.fallbacks,
                "no_effect": self.no_effect,
                "repeated_action": self.repeated_action,
                "safety_rejects": self.safety_rejects,
                "provider_failures": self.provider_failures,
                "freshness_rejects": self.freshness_rejects,
                "wait_ms_total": self.wait_ms_total,
                "loop_wall_ms": self.loop_wall_ms,
                "time_to_first_action_ms": self.time_to_first_action_ms,
                "outcome": self.outcome,
                "outcome_reason": (self.outcome_reason or "")[:240],
                "rates": self.rates(),
                # Bound timing samples so logs stay small.
                "timings_ms": self.timings_ms[-40:],
            }
        )


def record_jev_session_summary(
    log: Any | None,
    stats: JevSessionStats,
    *,
    latency_trace_id: str | None = None,
) -> None:
    """Write one session summary to TaskLog + optional latency milestone."""
    payload = stats.to_public_dict()
    summary = (
        f"jev session mode={stats.mode} outcome={stats.outcome} "
        f"decisions={stats.decisions} executed={stats.executed} "
        f"fallbacks={stats.fallbacks}"
    )
    if log is not None:
        try:
            log.record("jev_session", summary[:200], payload)
        except Exception:
            pass
    if latency_trace_id:
        try:
            from latency_report import mark

            mark(
                latency_trace_id,
                "jev_session_complete",
                metadata={
                    "mode": stats.mode,
                    "outcome": stats.outcome,
                    "executed": stats.executed,
                    "fallbacks": stats.fallbacks,
                    "loop_wall_ms": stats.loop_wall_ms,
                    "time_to_first_action_ms": stats.time_to_first_action_ms,
                    "rates": stats.rates(),
                },
            )
        except Exception:
            pass


class StepTimer:
    """Simple wall-clock helper for one decision cycle."""

    def __init__(self, clock: Any | None = None) -> None:
        self._clock = clock or time.perf_counter
        self.t0 = self._clock()
        self.marks: dict[str, float] = {}

    def mark(self, name: str) -> None:
        self.marks[name] = self._clock()

    def ms_since(self, start_name: str | None = None) -> float:
        start = self.t0 if start_name is None else self.marks.get(start_name, self.t0)
        return (self._clock() - start) * 1000.0

    def span_ms(self, start_name: str, end_name: str) -> float | None:
        a = self.marks.get(start_name)
        b = self.marks.get(end_name)
        if a is None or b is None:
            return None
        return (b - a) * 1000.0
