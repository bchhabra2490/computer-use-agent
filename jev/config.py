"""Centralized Jev / TypeSafe configuration.

Parsing accepts an optional env mapping so tests never need to mutate
``os.environ``. The API key is never included in public dicts or ``repr``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

_OFF = frozenset({"0", "false", "no", "off", ""})
_ON = frozenset({"1", "true", "yes", "on"})

ApiKeyStatus = Literal["available", "unavailable"]

JEV_ENV_KEYS: tuple[str, ...] = (
    "JEV_FAST_LOOP",
    "JEV_SHADOW_MODE",
    "JEV_CHOOSE_TOOL",
    "TYPESAFE_API_KEY",
    "JEV_MODEL",
    "JEV_MIN_CONFIDENCE",
    "JEV_MIN_MARGIN",
    "JEV_COMPLETE_THRESHOLD",
    "JEV_STUCK_THRESHOLD",
    "JEV_MAX_STEPS",
    "JEV_MAX_CANDIDATES",
    "JEV_REQUEST_TIMEOUT_SECONDS",
    "JEV_MAX_CONSECUTIVE_FAILURES",
)

_DEFAULTS = {
    "JEV_FAST_LOOP": "0",
    "JEV_SHADOW_MODE": "1",
    # Agent-facing Choice tool; default off — requires key + SDK when enabled.
    "JEV_CHOOSE_TOOL": "0",
    "JEV_MODEL": "jev-latest",
    "JEV_MIN_CONFIDENCE": "0.70",
    "JEV_MIN_MARGIN": "0.20",
    "JEV_COMPLETE_THRESHOLD": "0.85",
    "JEV_STUCK_THRESHOLD": "0.70",
    "JEV_MAX_STEPS": "20",
    "JEV_MAX_CANDIDATES": "220",
    "JEV_REQUEST_TIMEOUT_SECONDS": "3",
    "JEV_MAX_CONSECUTIVE_FAILURES": "2",
}

# TypeSafe Choice criteria hard limit (inclusive). Keep room for reserved
# policy candidates and any internal provider options.
JEV_CHOICE_MAX_OPTIONS = 255
JEV_MAX_CANDIDATES_HARD_CEILING = 253


def _env_get(env: Mapping[str, str], key: str, default: str = "") -> str:
    raw = env.get(key, default)
    if raw is None:
        return default
    return str(raw).strip()


def _parse_bool(raw: str, *, default: bool) -> bool:
    text = (raw or "").strip().lower()
    if text in _ON:
        return True
    if text in _OFF:
        return False
    return default


def _parse_float(raw: str, *, default: float) -> float:
    try:
        return float((raw or "").strip())
    except (TypeError, ValueError):
        return default


def _parse_int(raw: str, *, default: int) -> int:
    try:
        # Allow "20.0" style values from env editors.
        return int(float((raw or "").strip()))
    except (TypeError, ValueError):
        return default


def _clamp_float(value: float, lo: float, hi: float) -> float:
    if value != value:  # NaN
        return lo
    return max(lo, min(hi, value))


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def api_key_status(env: Mapping[str, str] | None = None) -> ApiKeyStatus:
    """Return ``available`` when TYPESAFE_API_KEY is non-empty, else ``unavailable``."""
    source = os.environ if env is None else env
    key = _env_get(source, "TYPESAFE_API_KEY", "")
    return "available" if key else "unavailable"


@dataclass(frozen=True)
class JevConfig:
    """Validated Jev settings for the optional fast computer-use policy.

    ``api_key`` is stored for future SDK use but is excluded from ``repr`` and
    public serialization. Prefer :meth:`api_key_status` / :attr:`has_api_key`
    when logging or reporting configuration.
    """

    fast_loop: bool = False
    shadow_mode: bool = True
    choose_tool: bool = False
    api_key: str = ""
    model: str = "jev-latest"
    min_confidence: float = 0.70
    min_margin: float = 0.20
    complete_threshold: float = 0.85
    stuck_threshold: float = 0.70
    max_steps: int = 20
    max_candidates: int = 220
    request_timeout_seconds: float = 3.0
    max_consecutive_failures: int = 2

    def __repr__(self) -> str:
        return (
            "JevConfig("
            f"fast_loop={self.fast_loop!r}, "
            f"shadow_mode={self.shadow_mode!r}, "
            f"choose_tool={self.choose_tool!r}, "
            f"api_key_status={self.api_key_status!r}, "
            f"model={self.model!r}, "
            f"min_confidence={self.min_confidence!r}, "
            f"min_margin={self.min_margin!r}, "
            f"complete_threshold={self.complete_threshold!r}, "
            f"stuck_threshold={self.stuck_threshold!r}, "
            f"max_steps={self.max_steps!r}, "
            f"max_candidates={self.max_candidates!r}, "
            f"request_timeout_seconds={self.request_timeout_seconds!r}, "
            f"max_consecutive_failures={self.max_consecutive_failures!r})"
        )

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)

    @property
    def api_key_status(self) -> ApiKeyStatus:
        return "available" if self.has_api_key else "unavailable"

    @property
    def enabled(self) -> bool:
        """True only when the fast loop is explicitly on and a key exists."""
        return self.fast_loop and self.has_api_key

    def to_public_dict(self) -> dict[str, Any]:
        """JSON-safe settings for logs/status — never includes the API key."""
        return {
            "fast_loop": self.fast_loop,
            "shadow_mode": self.shadow_mode,
            "choose_tool": self.choose_tool,
            "api_key_status": self.api_key_status,
            "enabled": self.enabled,
            "model": self.model,
            "min_confidence": self.min_confidence,
            "min_margin": self.min_margin,
            "complete_threshold": self.complete_threshold,
            "stuck_threshold": self.stuck_threshold,
            "max_steps": self.max_steps,
            "max_candidates": self.max_candidates,
            "request_timeout_seconds": self.request_timeout_seconds,
            "max_consecutive_failures": self.max_consecutive_failures,
        }


def load_jev_config(env: Mapping[str, str] | None = None) -> JevConfig:
    """Load and clamp Jev settings from ``env`` (default: ``os.environ``).

    Jev stays disabled unless ``JEV_FAST_LOOP`` is explicitly enabled.
    Shadow mode defaults to on. Invalid numerics fall back to defaults, then
    clamp into safe ranges. A missing API key is ``unavailable``, not an error.
    """
    source = os.environ if env is None else env

    fast_loop = _parse_bool(
        _env_get(source, "JEV_FAST_LOOP", _DEFAULTS["JEV_FAST_LOOP"]),
        default=False,
    )
    shadow_mode = _parse_bool(
        _env_get(source, "JEV_SHADOW_MODE", _DEFAULTS["JEV_SHADOW_MODE"]),
        default=True,
    )
    choose_tool = _parse_bool(
        _env_get(source, "JEV_CHOOSE_TOOL", _DEFAULTS["JEV_CHOOSE_TOOL"]),
        default=False,
    )
    api_key = _env_get(source, "TYPESAFE_API_KEY", "")
    model = _env_get(source, "JEV_MODEL", _DEFAULTS["JEV_MODEL"]) or "jev-latest"

    min_confidence = _clamp_float(
        _parse_float(
            _env_get(source, "JEV_MIN_CONFIDENCE", _DEFAULTS["JEV_MIN_CONFIDENCE"]),
            default=0.70,
        ),
        0.0,
        1.0,
    )
    min_margin = _clamp_float(
        _parse_float(
            _env_get(source, "JEV_MIN_MARGIN", _DEFAULTS["JEV_MIN_MARGIN"]),
            default=0.20,
        ),
        0.0,
        1.0,
    )
    complete_threshold = _clamp_float(
        _parse_float(
            _env_get(
                source,
                "JEV_COMPLETE_THRESHOLD",
                _DEFAULTS["JEV_COMPLETE_THRESHOLD"],
            ),
            default=0.85,
        ),
        0.0,
        1.0,
    )
    stuck_threshold = _clamp_float(
        _parse_float(
            _env_get(source, "JEV_STUCK_THRESHOLD", _DEFAULTS["JEV_STUCK_THRESHOLD"]),
            default=0.70,
        ),
        0.0,
        1.0,
    )
    max_steps = _clamp_int(
        _parse_int(
            _env_get(source, "JEV_MAX_STEPS", _DEFAULTS["JEV_MAX_STEPS"]),
            default=20,
        ),
        1,
        200,
    )
    max_candidates = _clamp_int(
        _parse_int(
            _env_get(source, "JEV_MAX_CANDIDATES", _DEFAULTS["JEV_MAX_CANDIDATES"]),
            default=220,
        ),
        1,
        JEV_MAX_CANDIDATES_HARD_CEILING,
    )
    request_timeout_seconds = _clamp_float(
        _parse_float(
            _env_get(
                source,
                "JEV_REQUEST_TIMEOUT_SECONDS",
                _DEFAULTS["JEV_REQUEST_TIMEOUT_SECONDS"],
            ),
            default=3.0,
        ),
        0.1,
        60.0,
    )
    max_consecutive_failures = _clamp_int(
        _parse_int(
            _env_get(
                source,
                "JEV_MAX_CONSECUTIVE_FAILURES",
                _DEFAULTS["JEV_MAX_CONSECUTIVE_FAILURES"],
            ),
            default=2,
        ),
        0,
        20,
    )

    return JevConfig(
        fast_loop=fast_loop,
        shadow_mode=shadow_mode,
        choose_tool=choose_tool,
        api_key=api_key,
        model=model,
        min_confidence=min_confidence,
        min_margin=min_margin,
        complete_threshold=complete_threshold,
        stuck_threshold=stuck_threshold,
        max_steps=max_steps,
        max_candidates=max_candidates,
        request_timeout_seconds=request_timeout_seconds,
        max_consecutive_failures=max_consecutive_failures,
    )


def jev_choose_tool_enabled(
    config: JevConfig | None = None,
    *,
    sdk_available: bool | None = None,
) -> bool:
    """True when the agent ``jev_choose`` tool should be exposed.

    Requires ``JEV_CHOOSE_TOOL=1``, a non-empty API key, and the TypeSafe SDK
    (unless ``sdk_available`` is injected by tests).
    """
    cfg = config if config is not None else load_jev_config()
    if not cfg.choose_tool:
        return False
    if not cfg.has_api_key:
        return False
    if sdk_available is None:
        # Lazy import only when deciding exposure — avoid SDK init at import time.
        try:
            from jev.client import typesafe_sdk_available

            sdk_available = typesafe_sdk_available()
        except Exception:
            sdk_available = False
    return bool(sdk_available)
