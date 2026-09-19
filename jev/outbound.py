"""Centralized outbound sanitization for hosted Jev (system_one) payloads.

Inspects every string that leaves the machine. Never echoes detected secrets
in reasons or logs. Used by both the fast loop and ``jev_choose``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from jev.actions import (
    _SECRET_ASSIGN_RE,
    _SECRET_BLOB_RE,
    classify_jev_input_privacy,
    looks_like_secret_task,
)

# Query / fragment keys that must never leave the host.
_SENSITIVE_QUERY_RE = re.compile(
    r"(?i)(password|passwd|passcode|pwd|pin|otp|token|secret|api[_-]?key|"
    r"access[_-]?token|refresh[_-]?token|auth|bearer|session|credential|"
    r"cvv|cvc|card|ssn|private[_-]?key)"
)

_REDACTED = "[redacted]"


@dataclass(frozen=True)
class OutboundSanitizeResult:
    """Outcome of sanitizing a hosted Jev request payload."""

    allowed: bool
    state: dict[str, Any]
    criteria: dict[str, str]
    reason: str = ""
    category: str = ""


def _category_for_text(raw: str) -> str:
    if re.search(r"(?i)\botp|one[\s-]?time|verification\s*code", raw):
        return "otp"
    if re.search(r"(?i)api[\s_-]?key|access[\s_-]?token|bearer|sk-", raw):
        return "api_key"
    if re.search(r"(?i)private\s*key|seed\s*phrase|recovery|mnemonic", raw):
        return "private_key"
    if re.search(r"(?i)cvv|cvc|credit\s*card|card\s*number", raw):
        return "payment"
    if re.search(r"(?i)password|passwd|passcode|\bpin\b", raw):
        return "password"
    return "sensitive_data"


def string_contains_secret(text: str) -> bool:
    """True when ``text`` appears to contain credentials or payment secrets."""
    raw = (text or "").strip()
    if not raw:
        return False
    if _SECRET_ASSIGN_RE.search(raw) or _SECRET_BLOB_RE.search(raw):
        return True
    return looks_like_secret_task(raw)


def sanitize_url_for_jev(url: str) -> str:
    """Keep only scheme + host (drop userinfo, path, query, fragment)."""
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except Exception:
        return ""
    if not parts.scheme or not parts.hostname:
        # Relative or opaque — drop entirely if it looks secret-bearing.
        if string_contains_secret(raw) or "?" in raw or "#" in raw:
            return ""
        return raw[:120]
    # Drop credentials in netloc; rebuild host only.
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme.lower(), host, "", "", ""))


def redact_string(text: str) -> str:
    """Return text unchanged, empty, or a scrubbed placeholder — never the secret."""
    raw = text or ""
    if not raw.strip():
        return ""
    if string_contains_secret(raw):
        return _REDACTED
    return raw


def _scan_fail(category: str) -> OutboundSanitizeResult:
    return OutboundSanitizeResult(
        allowed=False,
        state={},
        criteria={},
        reason=f"outbound payload contains sensitive data ({category}); bypassing Jev",
        category=category,
    )


def sanitize_outbound_for_jev(
    *,
    state: Mapping[str, Any],
    criteria: Mapping[str, str],
    goal: str = "",
    subgoal: str = "",
) -> OutboundSanitizeResult:
    """Sanitize public state + Choice criteria immediately before ``system_one``.

    If the decision cannot be represented safely after redaction, ``allowed`` is
    False and the provider must not be called.
    """
    # Goal / subgoal hard gate (existing classifier + full scan).
    privacy = classify_jev_input_privacy(goal, subgoal)
    if not privacy.allowed:
        return OutboundSanitizeResult(
            allowed=False,
            state={},
            criteria={},
            reason=privacy.reason,
            category=privacy.category or "sensitive_task",
        )
    for label, text in (("goal", goal), ("subgoal", subgoal)):
        if string_contains_secret(text):
            return _scan_fail(_category_for_text(text))

    safe_criteria: dict[str, str] = {}
    for cid, desc in dict(criteria or {}).items():
        key = str(cid)
        value = str(desc or "")
        if string_contains_secret(value) or string_contains_secret(key):
            return _scan_fail(_category_for_text(value or key))
        safe_criteria[key] = value[:240]

    if not safe_criteria:
        return OutboundSanitizeResult(
            allowed=False,
            state={},
            criteria={},
            reason="no safe choice criteria after sanitization; bypassing Jev",
            category="empty_criteria",
        )

    out: dict[str, Any] = dict(state or {})
    # Goal / subgoal already checked; keep as provided (may be redacted upstream).
    out["goal"] = str(out.get("goal") or goal or "")
    out["subgoal"] = str(out.get("subgoal") or subgoal or "")

    url = sanitize_url_for_jev(str(out.get("url") or ""))
    if string_contains_secret(str(out.get("url") or "")):
        # Original URL had secrets — only host form is allowed; if empty, fail.
        if not url:
            return _scan_fail("url")
    out["url"] = url

    for field in ("application", "window", "app_name", "window_title"):
        if field in out:
            raw = str(out.get(field) or "")
            if string_contains_secret(raw):
                return _scan_fail(_category_for_text(raw))
            out[field] = raw

    # Focused element + element list.
    focused = out.get("focused_element")
    if isinstance(focused, Mapping):
        out["focused_element"] = _sanitize_element_dict(dict(focused))
        if out["focused_element"] is None:
            return _scan_fail("ui_element")
    elements_in = out.get("elements")
    if isinstance(elements_in, Sequence) and not isinstance(elements_in, (str, bytes)):
        cleaned_els: list[dict[str, Any]] = []
        for el in elements_in:
            if not isinstance(el, Mapping):
                continue
            cleaned = _sanitize_element_dict(dict(el))
            if cleaned is None:
                return _scan_fail("ui_element")
            cleaned_els.append(cleaned)
        out["elements"] = cleaned_els

    recent = out.get("recent_actions")
    if isinstance(recent, Sequence) and not isinstance(recent, (str, bytes)):
        cleaned_ra: list[dict[str, Any]] = []
        for action in recent:
            if not isinstance(action, Mapping):
                continue
            cleaned = _sanitize_action_dict(dict(action))
            if cleaned is None:
                return _scan_fail("recent_action")
            cleaned_ra.append(cleaned)
        out["recent_actions"] = cleaned_ra

    text_cands = out.get("text_candidates")
    if isinstance(text_cands, Sequence) and not isinstance(text_cands, (str, bytes)):
        safe_cands: list[str] = []
        for cand in text_cands:
            s = str(cand or "")
            if string_contains_secret(s):
                return _scan_fail(_category_for_text(s))
            if s.strip():
                safe_cands.append(s)
        out["text_candidates"] = safe_cands

    facts = out.get("facts")
    if isinstance(facts, Mapping):
        safe_facts: dict[str, str] = {}
        for k, v in facts.items():
            ks, vs = str(k), str(v)
            if string_contains_secret(ks) or string_contains_secret(vs):
                return _scan_fail("facts")
            safe_facts[ks] = vs
        out["facts"] = safe_facts

    constraints = out.get("planner_constraints")
    if isinstance(constraints, Sequence) and not isinstance(constraints, (str, bytes)):
        safe_constraints: list[str] = []
        for c in constraints:
            s = str(c or "")
            if string_contains_secret(s):
                continue  # drop unsafe constraint lines; not decision-critical
            if s.strip():
                safe_constraints.append(s)
        out["planner_constraints"] = safe_constraints

    reminder = str(out.get("policy_reminder") or "")
    if string_contains_secret(reminder):
        out["policy_reminder"] = ""
    else:
        out["policy_reminder"] = reminder

    return OutboundSanitizeResult(
        allowed=True,
        state=out,
        criteria=safe_criteria,
        reason="ok",
        category="",
    )


def _sanitize_element_dict(el: MutableMapping[str, Any]) -> dict[str, Any] | None:
    """Redact or reject an element dict. Secure values stay empty."""
    sensitive = bool(el.get("sensitive"))
    label = str(el.get("label") or "")
    description = str(el.get("description") or "")
    value = "" if sensitive else str(el.get("value") or "")
    role = str(el.get("role") or "")
    for field_name, text in (
        ("label", label),
        ("description", description),
        ("value", value),
        ("role", role),
    ):
        if string_contains_secret(text):
            # Element cannot be represented safely — fail the whole payload
            # when the secret is in a decision-relevant field.
            return None
    return {
        "id": str(el.get("id") or ""),
        "role": role,
        "label": label,
        "value": value,
        "description": description,
        "enabled": bool(el.get("enabled", True)),
        "focused": bool(el.get("focused", False)),
        "selected": bool(el.get("selected", False)),
        "frame": el.get("frame"),
        "supported_actions": list(el.get("supported_actions") or []),
        "sensitive": sensitive,
    }


def _sanitize_action_dict(action: MutableMapping[str, Any]) -> dict[str, Any] | None:
    desc = str(action.get("description") or "")
    if string_contains_secret(desc):
        return None
    op = str(action.get("op") or "")
    if string_contains_secret(op):
        return None
    return {
        "action_id": str(action.get("action_id") or ""),
        "kind": str(action.get("kind") or ""),
        "element_id": action.get("element_id"),
        "description": desc,
        "op": op,
        "requires_confirmation": bool(action.get("requires_confirmation", False)),
        "sensitive": bool(action.get("sensitive", False)),
    }
