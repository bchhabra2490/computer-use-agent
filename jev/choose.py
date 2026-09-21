"""Agent-facing Jev Choice helper (advisory only; inspired by jev-ax-pilot).

The pre-agent fast loop remains the only path that may execute computer actions.
``jev_choose`` only ranks options and never clicks, types, pays, or marks done.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, Callable

from jev.actions import classify_jev_input_privacy, enumerate_grounded_actions
from jev.client import JevClient
from jev.config import (
    JEV_CHOICE_MAX_OPTIONS,
    JevConfig,
    jev_choose_tool_enabled,
    load_jev_config,
)
from jev.models import ActionKind, GroundedAction, JevDecision, UISnapshot
from jev.session import get_jev_session, update_jev_session
from jev.text_candidates import extract_text_candidates, goal_names_destructive

# Agent-authored option lists — hard reject above this (no silent truncate).
JEV_CHOOSE_MAX_AGENT_OPTIONS = 32
JEV_AX_PROPOSE_MAX_CANDIDATES = 60
_OPTION_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")

# Internally namespaced pseudo-options (never accept bare reserved ids from callers).
PSEUDO_ASK_USER = "__jev_ask_user"
PSEUDO_USE_VISION = "__jev_use_vision"
PSEUDO_STUCK = "__jev_stuck"
PSEUDO_DONE = "__jev_done"

PSEUDO_OPTIONS: tuple[tuple[str, str], ...] = (
    (PSEUDO_ASK_USER, "Ask the user a clarifying question (ambiguity / confirmation)"),
    (PSEUDO_USE_VISION, "Continue with the vision computer-use agent / screenshots"),
    (PSEUDO_STUCK, "No listed option can make progress toward the goal"),
    (PSEUDO_DONE, "The goal is already achieved; verify on screen then mark_done"),
)

# Caller-facing reserved ids that must be rejected (map to internal names).
RESERVED_CALLER_IDS: frozenset[str] = frozenset(
    {
        "ask_user",
        "use_vision",
        "stuck",
        "done",
        PSEUDO_ASK_USER,
        PSEUDO_USE_VISION,
        PSEUDO_STUCK,
        PSEUDO_DONE,
    }
)

_PUBLIC_RECOMMENDATION = {
    PSEUDO_ASK_USER: "ask_user",
    PSEUDO_USE_VISION: "use_vision",
    PSEUDO_STUCK: "use_vision",
    PSEUDO_DONE: "verify_then_done",
}


def normalize_agent_options(
    options: Sequence[Mapping[str, Any] | Any] | None,
    *,
    limit: int = JEV_CHOOSE_MAX_AGENT_OPTIONS,
    require_min: int = 2,
) -> tuple[list[tuple[str, str]], str | None]:
    """Validate agent options → ``[(id, description), ...]`` or an error.

    Never silently truncates: more than ``limit`` options is an error.
    """
    if options is None:
        return [], None
    if not isinstance(options, Sequence) or isinstance(options, (str, bytes)):
        return [], "Error: options must be a list"
    if not options and require_min > 0:
        return [], "Error: options must be a non-empty list"

    supplied = len(options)
    max_allowed = max(2, min(int(limit), JEV_CHOOSE_MAX_OPTIONS))
    if supplied > max_allowed:
        return [], (
            f"Error: too many options (max={max_allowed}, supplied={supplied})"
        )
    if supplied < require_min:
        return [], f"Error: provide at least {require_min} options"

    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for i, raw in enumerate(options):
        if isinstance(raw, Mapping):
            oid = str(raw.get("id") or "").strip()
            desc = str(raw.get("description") or raw.get("label") or "").strip()
        else:
            return [], f"Error: options[{i}] must be an object with id and description"
        if not oid or not _OPTION_ID_RE.match(oid):
            return [], (
                f"Error: options[{i}].id must be 1–64 chars of "
                "[A-Za-z0-9_.:-]"
            )
        if oid in RESERVED_CALLER_IDS or oid.startswith("__jev_"):
            return [], (
                f"Error: options[{i}].id {oid!r} is reserved; "
                "use a non-reserved id (internal pseudos are added automatically)"
            )
        if oid in seen:
            return [], f"Error: duplicate option id {oid!r}"
        if not desc:
            return [], f"Error: options[{i}].description is required"
        if len(desc) > 240:
            desc = desc[:240] + "…"
        seen.add(oid)
        out.append((oid, desc))
    return out, None


def inject_pseudo_options(
    pairs: Sequence[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Append namespaced pseudo options; never exceed provider Choice ceiling."""
    seen = {oid for oid, _ in pairs}
    out = list(pairs)
    room = JEV_CHOICE_MAX_OPTIONS - len(out)
    for oid, desc in PSEUDO_OPTIONS:
        if room <= 0:
            break
        if oid not in seen:
            out.append((oid, desc))
            seen.add(oid)
            room -= 1
    return out


def advisory_candidates_from_options(
    pairs: Sequence[tuple[str, str]],
) -> list[GroundedAction]:
    """Build non-executable candidates for Choice criteria only."""
    return [
        GroundedAction(
            action_id=oid,
            kind=ActionKind.NOOP,
            description=desc,
            arguments={"op": "advisory_choice", "text": desc},
            requires_confirmation=False,
            sensitive=False,
        )
        for oid, desc in pairs
    ]


def _empty_snapshot(*, app_name: str = "", window_title: str = "") -> UISnapshot:
    return UISnapshot(
        revision=0,
        captured_at=datetime.now(timezone.utc),
        app_name=(app_name or "").strip(),
        window_title=(window_title or "").strip(),
        elements=(),
    )


def ax_option_pairs(
    *,
    goal: str,
    config: JevConfig,
    snapshot: UISnapshot | None = None,
) -> tuple[list[tuple[str, str]], UISnapshot, str | None]:
    """Flatten frontmost AX into option pairs + snapshot."""
    snap = snapshot
    if snap is None:
        try:
            from accessibility import capture_ui_snapshot

            snap = capture_ui_snapshot()
        except Exception as exc:
            return (
                [],
                _empty_snapshot(),
                f"Error: AX snapshot failed ({type(exc).__name__})",
            )
    if snap.error:
        return [], snap, f"Error: AX unavailable ({snap.error})"
    capped = JevConfig(
        fast_loop=config.fast_loop,
        shadow_mode=config.shadow_mode,
        choose_tool=config.choose_tool,
        api_key=config.api_key,
        model=config.model,
        min_confidence=config.min_confidence,
        min_margin=config.min_margin,
        complete_threshold=config.complete_threshold,
        stuck_threshold=config.stuck_threshold,
        max_steps=config.max_steps,
        max_candidates=min(int(config.max_candidates), JEV_AX_PROPOSE_MAX_CANDIDATES),
        request_timeout_seconds=config.request_timeout_seconds,
        max_consecutive_failures=config.max_consecutive_failures,
    )
    actions = enumerate_grounded_actions(snap, goal, config=capped)
    pairs: list[tuple[str, str]] = []
    for action in actions:
        op = str(action.arguments.get("op") or "")
        if op in {"escalate", "done"}:
            continue
        # Grounded ids must not collide with reserved pseudo namespace.
        if action.action_id in RESERVED_CALLER_IDS or action.action_id.startswith(
            "__jev_"
        ):
            continue
        desc = (action.description or op or action.kind.value).strip()
        if not desc:
            continue
        pairs.append((action.action_id, desc[:240]))
    if not pairs:
        return (
            [],
            snap,
            "Error: no grounded AX candidates (try agent options or open the target app)",
        )
    return inject_pseudo_options(pairs), snap, None


def recommendation_from_decision(
    decision: JevDecision,
    *,
    config: JevConfig,
    selected_description: str = "",
    goal: str = "",
) -> tuple[str, str]:
    """Map Noul/confidence into a short agent-facing recommendation."""
    if decision.error:
        return "use_vision", decision.fallback_reason or decision.error or "jev error"
    stuck = float(decision.stuck_probability or 0.0)
    complete = float(decision.complete_probability or 0.0)
    conf = float(decision.confidence or 0.0)
    margin = float(decision.margin or 0.0)
    destructive = float(decision.is_destructive_probability or 0.0)
    selected = decision.selected_candidate_id or ""

    if destructive >= 0.5 and not goal_names_destructive(goal):
        return (
            "ask_user",
            "is_destructive high and goal does not name that operation",
        )
    if selected in _PUBLIC_RECOMMENDATION:
        public = _PUBLIC_RECOMMENDATION[selected]
        if selected == PSEUDO_DONE or complete >= config.complete_threshold:
            return (
                "verify_then_done",
                "complete/done — verify on screen then mark_done",
            )
        if public == "ask_user":
            return "ask_user", "selected option is to ask the user"
        return "use_vision", "selected escalate / stuck / vision path"
    # Descriptions containing the word "done" are NOT completion unless id matches.
    if stuck >= config.stuck_threshold:
        return (
            "use_vision",
            "stuck probability high — continue with screenshots / computer tool",
        )
    if complete >= config.complete_threshold:
        return (
            "verify_then_done",
            "complete probability high — verify on screen then mark_done",
        )
    if conf < config.min_confidence or margin < config.min_margin:
        return (
            "use_vision",
            "low confidence or narrow margin — do not treat as authoritative",
        )
    desc_l = (selected_description or "").lower()
    if any(
        tok in desc_l
        for tok in ("pay", "payment", "purchase", "place order", "book now", "checkout")
    ):
        return (
            "ask_user",
            "payment/booking-like option — confirm with the user before acting",
        )
    return "proceed", "use the selected option; execute yourself via computer tool"


def format_jev_choose_result(
    decision: JevDecision,
    *,
    pairs: Sequence[tuple[str, str]],
    config: JevConfig,
    goal: str = "",
    source: str = "agent",
    text_candidates: Sequence[str] | None = None,
    app_name: str = "",
    window_title: str = "",
) -> dict[str, Any]:
    """JSON-serializable tool payload (no secrets)."""
    by_id = {oid: desc for oid, desc in pairs}
    selected = decision.selected_candidate_id or ""
    selected_desc = by_id.get(selected, "")
    rec, reason = recommendation_from_decision(
        decision,
        config=config,
        selected_description=selected_desc,
        goal=goal,
    )
    ok = not bool(decision.error)
    payload: dict[str, Any] = {
        "ok": ok,
        "advisory": True,
        "execute_yourself": True,
        "source": source,
        "selected_id": selected or None,
        "selected_description": selected_desc or None,
        "confidence": decision.confidence,
        "margin": decision.margin,
        "complete_probability": decision.complete_probability,
        "stuck_probability": decision.stuck_probability,
        "is_destructive_probability": decision.is_destructive_probability,
        "needs_text_probability": decision.needs_text_probability,
        "recommendation": rec,
        "reason": reason if ok else (decision.fallback_reason or decision.error),
        "text_candidates": list(text_candidates or ()),
        "app": app_name or None,
        "window": window_title or None,
        "model": decision.model or config.model,
        "latency_ms": decision.latency_ms,
        "distribution": dict(decision.distribution or {}),
        "option_count": len(pairs),
    }
    if decision.error:
        payload["error"] = decision.error
    return payload


def run_jev_choose(
    *,
    goal: str,
    options: Sequence[Mapping[str, Any] | Any] | None = None,
    subgoal: str = "",
    app: str = "",
    window: str = "",
    url: str = "",
    source: str = "agent",
    config: JevConfig | None = None,
    system_one: Callable[..., Any] | None = None,
    client: JevClient | None = None,
    snapshot: UISnapshot | None = None,
) -> dict[str, Any]:
    """Run one advisory Choice among agent- or AX-supplied options."""
    cfg = config or load_jev_config()
    if not jev_choose_tool_enabled(cfg) and system_one is None:
        return {
            "ok": False,
            "advisory": True,
            "execute_yourself": True,
            "error": "jev_choose unavailable (disabled, missing API key, or SDK)",
            "recommendation": "use_vision",
            "reason": "jev_choose unavailable",
        }

    source_norm = (source or "agent").strip().lower()
    if source_norm not in {"agent", "ax"}:
        return {
            "ok": False,
            "advisory": True,
            "execute_yourself": True,
            "error": "Error: source must be 'agent' or 'ax'",
            "recommendation": "use_vision",
            "reason": "invalid source",
        }

    privacy = classify_jev_input_privacy(goal, subgoal)
    if not privacy.allowed:
        return {
            "ok": False,
            "advisory": True,
            "execute_yourself": True,
            "error": privacy.reason or "sensitive task",
            "recommendation": "use_vision",
            "reason": privacy.reason or "sensitive task",
        }

    session = get_jev_session()
    snap = _empty_snapshot(app_name=app, window_title=window)

    if source_norm == "ax":
        # Capture first so we can compare revision to the fast-loop attempt.
        pairs, snap, err = ax_option_pairs(goal=goal, config=cfg, snapshot=snapshot)
        if err:
            return {
                "ok": False,
                "advisory": True,
                "execute_yourself": True,
                "source": "ax",
                "error": err,
                "recommendation": "use_vision",
                "reason": err,
            }
        if session is not None and not session.may_call_ax(snap.revision):
            return {
                "ok": False,
                "advisory": True,
                "execute_yourself": True,
                "source": "ax",
                "error": (
                    "Error: jev_choose source=ax blocked — pre-agent Jev already "
                    "evaluated this UI state; wait for a new snapshot revision "
                    "or use source=agent for a distinct symbolic choice"
                ),
                "recommendation": "use_vision",
                "reason": "duplicate ax jev call blocked",
                "session": session.to_public_dict(),
            }
    else:
        pairs, err = normalize_agent_options(options)
        if err:
            return {
                "ok": False,
                "advisory": True,
                "execute_yourself": True,
                "error": err,
                "recommendation": "use_vision",
                "reason": err,
            }
        pairs = inject_pseudo_options(pairs)
        if len(pairs) > JEV_CHOICE_MAX_OPTIONS:
            return {
                "ok": False,
                "advisory": True,
                "execute_yourself": True,
                "error": (
                    f"Error: options plus internal pseudos exceed provider limit "
                    f"(max={JEV_CHOICE_MAX_OPTIONS}, total={len(pairs)})"
                ),
                "recommendation": "use_vision",
                "reason": "choice criteria exceed provider limit",
            }

    text_cands = extract_text_candidates(f"{goal} {subgoal}".strip())
    candidates = advisory_candidates_from_options(pairs)
    owns = client is None
    jev = client or JevClient(config=cfg)
    try:
        decision = jev.choose_among_options(
            goal=goal,
            candidates=candidates,
            snapshot=snap,
            subgoal=subgoal,
            url=url,
            system_one=system_one,
        )
    finally:
        if owns:
            jev.close()

    result = format_jev_choose_result(
        decision,
        pairs=pairs,
        config=cfg,
        goal=goal,
        source=source_norm,
        text_candidates=text_cands,
        app_name=snap.app_name or app,
        window_title=snap.window_title or window,
    )

    if source_norm == "ax" and session is not None:
        update_jev_session(
            session.after_ax_choose(
                snapshot_revision=snap.revision, ok=bool(result.get("ok"))
            )
        )
    return result


def run_jev_choose_tool(args: Mapping[str, Any], *, client: Any | None = None) -> str:
    """Registry handler: parse args → JSON string for the model."""
    del client
    goal = str(args.get("goal") or "").strip()
    if not goal:
        return json.dumps(
            {
                "ok": False,
                "error": "Error: goal is required",
                "recommendation": "use_vision",
            }
        )
    source = str(args.get("source") or "agent").strip().lower() or "agent"
    options = args.get("options")
    if source == "agent" and not isinstance(options, list):
        return json.dumps(
            {
                "ok": False,
                "error": "Error: options must be a list when source=agent",
                "recommendation": "use_vision",
            }
        )
    result = run_jev_choose(
        goal=goal,
        options=options if isinstance(options, list) else None,
        subgoal=str(args.get("subgoal") or "").strip(),
        app=str(args.get("app") or "").strip(),
        window=str(args.get("window") or "").strip(),
        url=str(args.get("url") or "").strip(),
        source=source,
    )
    return json.dumps(result, ensure_ascii=False)
