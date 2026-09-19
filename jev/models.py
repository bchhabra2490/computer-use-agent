"""Typed domain models for the Jev fast computer-use policy.

Independent of the TypeSafe SDK so offline unit tests need no network or
vendor package. Native AX handles stay in a local-only registry and never
appear in public serialization. Password / secure field values are redacted
in ``repr`` and public dict forms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ElementFrame:
    """Screen-space rectangle in Cocoa / logical points (origin top-left)."""

    x: float
    y: float
    width: float
    height: float

    def to_public_dict(self) -> dict[str, float]:
        return {
            "x": float(self.x),
            "y": float(self.y),
            "width": float(self.width),
            "height": float(self.height),
        }


class ActionKind(str, Enum):
    """Grounded desktop actions the policy may propose."""

    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    TYPE = "type"
    KEYPRESS = "keypress"
    SCROLL = "scroll"
    WAIT = "wait"
    FOCUS = "focus"
    SET_VALUE = "set_value"
    CONFIRM = "confirm"
    COMPLETE = "complete"
    ESCALATE = "escalate"
    NOOP = "noop"


class JevGateVerdict(str, Enum):
    """Whether the fast loop may run, shadow, or must fall back."""

    DISABLED = "disabled"
    SHADOW = "shadow"
    ALLOW = "allow"
    FALLBACK = "fallback"
    REJECT = "reject"
    NEEDS_CONFIRMATION = "needs_confirmation"


class JevLoopStatus(str, Enum):
    """Terminal status for one Jev fast-loop attempt."""

    DISABLED = "disabled"
    SHADOW_COMPLETE = "shadow_complete"
    COMPLETED_PENDING_VERIFICATION = "completed_pending_verification"
    FALLBACK = "fallback"
    MAX_STEPS = "max_steps"
    ABORTED = "aborted"
    UNAVAILABLE = "unavailable"
    # Back-compat aliases used by earlier steps/tests.
    SHADOW = "shadow"
    COMPLETED = "completed"
    STUCK = "stuck"
    ERROR = "error"


@dataclass(frozen=True)
class UIElement:
    """Serializable UI node. Never carries a native AX handle."""

    id: str
    role: str = ""
    label: str = ""
    value: str = ""
    description: str = ""
    enabled: bool = True
    focused: bool = False
    selected: bool = False
    frame: ElementFrame | None = None
    supported_actions: tuple[str, ...] = ()
    sensitive: bool = False

    def safe_value(self) -> str:
        """Value safe for logs; empty when the field is sensitive."""
        return "" if self.sensitive else self.value

    def __repr__(self) -> str:
        value = "[sensitive]" if self.sensitive else self.value
        return (
            "UIElement("
            f"id={self.id!r}, role={self.role!r}, label={self.label!r}, "
            f"value={value!r}, description={self.description!r}, "
            f"enabled={self.enabled!r}, focused={self.focused!r}, "
            f"selected={self.selected!r}, frame={self.frame!r}, "
            f"supported_actions={self.supported_actions!r}, "
            f"sensitive={self.sensitive!r})"
        )

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "label": self.label,
            "value": self.safe_value(),
            "description": self.description,
            "enabled": self.enabled,
            "focused": self.focused,
            "selected": self.selected,
            "frame": None if self.frame is None else self.frame.to_public_dict(),
            "supported_actions": list(self.supported_actions),
            "sensitive": self.sensitive,
        }


@dataclass
class UISnapshot:
    """Structured UI capture for Jev.

    ``elements`` are the public, serializable candidates. Native AX handles
    (or any non-JSON object) live only in ``_handles`` and are omitted from
    ``repr``, equality, and :meth:`to_public_dict`.
    """

    revision: int = 0
    captured_at: datetime = field(default_factory=_utc_now)
    app_name: str = ""
    bundle_id: str = ""
    process_id: int | None = None
    window_title: str = ""
    focused_element_id: str | None = None
    elements: tuple[UIElement, ...] = ()
    error: str = ""
    capture_ms: float | None = None
    _handles: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def register_handle(self, element_id: str, handle: Any) -> None:
        """Store a local-only native handle keyed by public element id."""
        key = (element_id or "").strip()
        if not key:
            raise ValueError("element_id is required to register a handle")
        self._handles[key] = handle

    def get_handle(self, element_id: str) -> Any | None:
        return self._handles.get(element_id)

    def clear_handles(self) -> None:
        self._handles.clear()

    @property
    def handle_count(self) -> int:
        return len(self._handles)

    @property
    def available(self) -> bool:
        """False when Accessibility was unavailable or the target app was missing."""
        return not bool(self.error)

    def public_elements(self) -> tuple[UIElement, ...]:
        return self.elements

    def to_public_dict(self) -> dict[str, Any]:
        captured = self.captured_at
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=timezone.utc)
        return {
            "revision": self.revision,
            "captured_at": captured.isoformat(),
            "app_name": self.app_name,
            "bundle_id": self.bundle_id,
            "process_id": self.process_id,
            "window_title": self.window_title,
            "focused_element_id": self.focused_element_id,
            "elements": [el.to_public_dict() for el in self.elements],
            "error": self.error,
            "capture_ms": self.capture_ms,
            "available": self.available,
            # Explicitly absent: native handles must never serialize.
        }


@dataclass(frozen=True)
class GroundedAction:
    """Validated action tied to a snapshot element when relevant."""

    action_id: str
    kind: ActionKind
    element_id: str | None = None
    description: str = ""
    arguments: Mapping[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    sensitive: bool = False

    def __post_init__(self) -> None:
        kind = self.kind
        if isinstance(kind, str):
            object.__setattr__(self, "kind", ActionKind(kind))
        # Freeze a plain dict copy so callers cannot mutate shared state.
        object.__setattr__(self, "arguments", dict(self.arguments or {}))

    def __repr__(self) -> str:
        if self.sensitive:
            args = {str(k): "[sensitive]" for k in self.arguments}
        else:
            args = {
                str(k): (
                    "[sensitive]"
                    if str(k).lower() in {"password", "passwd", "secret"}
                    else v
                )
                for k, v in self.arguments.items()
            }
        return (
            "GroundedAction("
            f"action_id={self.action_id!r}, kind={self.kind!r}, "
            f"element_id={self.element_id!r}, description={self.description!r}, "
            f"arguments={args!r}, requires_confirmation={self.requires_confirmation!r}, "
            f"sensitive={self.sensitive!r})"
        )

    def to_public_dict(self) -> dict[str, Any]:
        if self.sensitive:
            public_args = {str(k): "[sensitive]" for k in self.arguments}
        else:
            public_args = {
                str(k): (
                    "[sensitive]"
                    if str(k).lower() in {"password", "passwd", "secret"}
                    else v
                )
                for k, v in self.arguments.items()
            }
        return {
            "action_id": self.action_id,
            "kind": (
                self.kind.value if isinstance(self.kind, ActionKind) else str(self.kind)
            ),
            "element_id": self.element_id,
            "description": self.description,
            "arguments": public_args,
            "requires_confirmation": self.requires_confirmation,
            "sensitive": self.sensitive,
        }


@dataclass(frozen=True)
class TokenUsage:
    """Optional token accounting from a Jev inference call."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    def to_public_dict(self) -> dict[str, int | None]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True)
class JevDecision:
    """Bounded policy decision returned by a Jev inference call."""

    selected_candidate_id: str | None = None
    selected_probability: float = 0.0
    second_probability: float = 0.0
    margin: float = 0.0
    confidence: float = 0.0
    complete_probability: float = 0.0
    stuck_probability: float = 0.0
    # ax-pilot-inspired Nouls (optional; 0.0 when absent from older mocks).
    is_destructive_probability: float = 0.0
    needs_text_probability: float = 0.0
    distribution: Mapping[str, float] = field(default_factory=dict)
    model: str = ""
    latency_ms: float | None = None
    token_usage: TokenUsage | None = None
    error: str | None = None
    fallback_reason: str | None = None

    def __post_init__(self) -> None:
        dist = {str(k): float(v) for k, v in dict(self.distribution or {}).items()}
        object.__setattr__(self, "distribution", dist)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "selected_candidate_id": self.selected_candidate_id,
            "selected_probability": self.selected_probability,
            "second_probability": self.second_probability,
            "margin": self.margin,
            "confidence": self.confidence,
            "complete_probability": self.complete_probability,
            "stuck_probability": self.stuck_probability,
            "is_destructive_probability": self.is_destructive_probability,
            "needs_text_probability": self.needs_text_probability,
            "distribution": dict(self.distribution),
            "model": self.model,
            "latency_ms": self.latency_ms,
            "token_usage": (
                None if self.token_usage is None else self.token_usage.to_public_dict()
            ),
            "error": self.error,
            "fallback_reason": self.fallback_reason,
        }


@dataclass(frozen=True)
class JevGateResult:
    """Outcome of the pre-loop gate (enable / shadow / fall back)."""

    verdict: JevGateVerdict
    reason: str = ""
    shadow: bool = False
    config_enabled: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.verdict, str):
            object.__setattr__(self, "verdict", JevGateVerdict(self.verdict))

    @property
    def may_execute(self) -> bool:
        return self.verdict is JevGateVerdict.ALLOW and not self.shadow

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "reason": self.reason,
            "shadow": self.shadow,
            "config_enabled": self.config_enabled,
            "may_execute": self.may_execute,
        }


@dataclass(frozen=True)
class JevLoopResult:
    """Result of one Jev fast-loop attempt (shadow or active)."""

    status: JevLoopStatus
    steps: int = 0
    gate: JevGateResult | None = None
    decision: JevDecision | None = None
    actions: tuple[GroundedAction, ...] = ()
    executed_actions: tuple[GroundedAction, ...] = ()
    observed_effects: tuple[str, ...] = ()
    reason: str = ""
    snapshot_revision: int | None = None
    latest_snapshot_public: Mapping[str, Any] | None = None
    wait_ms_total: float = 0.0
    fallback_prompt: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            object.__setattr__(self, "status", JevLoopStatus(self.status))
        object.__setattr__(self, "actions", tuple(self.actions or ()))
        object.__setattr__(self, "executed_actions", tuple(self.executed_actions or ()))
        object.__setattr__(self, "observed_effects", tuple(self.observed_effects or ()))

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "steps": self.steps,
            "gate": None if self.gate is None else self.gate.to_public_dict(),
            "decision": (
                None if self.decision is None else self.decision.to_public_dict()
            ),
            "actions": [a.to_public_dict() for a in self.actions],
            "executed_actions": [a.to_public_dict() for a in self.executed_actions],
            "observed_effects": list(self.observed_effects),
            "reason": self.reason,
            "snapshot_revision": self.snapshot_revision,
            "latest_snapshot_public": (
                None
                if self.latest_snapshot_public is None
                else dict(self.latest_snapshot_public)
            ),
            "wait_ms_total": self.wait_ms_total,
            "fallback_prompt": self.fallback_prompt,
        }


@dataclass(frozen=True)
class ValidationResult:
    """Freshness / compatibility check before executing a grounded action."""

    ok: bool
    reason: str = ""
    current_frame: ElementFrame | None = None
    element: UIElement | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "current_frame": (
                None
                if self.current_frame is None
                else self.current_frame.to_public_dict()
            ),
            "element_id": None if self.element is None else self.element.id,
        }


@dataclass(frozen=True)
class DecisionGateResult:
    """Pure confidence / safety gate over a JevDecision + candidates."""

    allowed: bool
    reason: str = ""
    requires_verification: bool = False
    requires_confirmation: bool = False
    action: GroundedAction | None = None
    verdict: JevGateVerdict = JevGateVerdict.FALLBACK

    def __post_init__(self) -> None:
        if isinstance(self.verdict, str):
            object.__setattr__(self, "verdict", JevGateVerdict(self.verdict))

    @property
    def allowed_pending_confirmation(self) -> bool:
        """True when the action is otherwise OK but needs a human confirmation."""
        return (
            self.requires_confirmation
            and not self.allowed
            and self.verdict is JevGateVerdict.NEEDS_CONFIRMATION
        )

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "requires_verification": self.requires_verification,
            "requires_confirmation": self.requires_confirmation,
            "allowed_pending_confirmation": self.allowed_pending_confirmation,
            "action": None if self.action is None else self.action.to_public_dict(),
            "verdict": self.verdict.value,
        }


@dataclass(frozen=True)
class PrivacyGateResult:
    """Whether goal/subgoal may be sent to TypeSafe / Jev."""

    allowed: bool
    reason: str = ""
    category: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        # Never include raw goal/subgoal text.
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "category": self.category,
        }
