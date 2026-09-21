"""Deterministic grounded-action generation, safety, freshness, and gates.

Step 3 of the Jev integration. Pure/local logic only — no TypeSafe SDK calls
and no wiring into the live agent loop. Execution helpers default to dry-run.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Callable

from jev.config import (
    JEV_CHOICE_MAX_OPTIONS,
    JEV_MAX_CANDIDATES_HARD_CEILING,
    JevConfig,
    load_jev_config,
)
from jev.models import (
    ActionKind,
    DecisionGateResult,
    ElementFrame,
    GroundedAction,
    JevDecision,
    JevGateVerdict,
    PrivacyGateResult,
    UIElement,
    UISnapshot,
    ValidationResult,
)

# Semantic op names exposed to the policy / tests (not free-form from screen text).
OP_CLICK = "click_element"
OP_FOCUS = "focus_element"
OP_TYPE = "type_task_text"
OP_ENTER = "press_enter"
OP_ESCAPE = "press_escape"
OP_TAB = "press_tab"
OP_SCROLL_DOWN = "scroll_down"
OP_SCROLL_UP = "scroll_up"
OP_WAIT = "wait"
OP_DONE = "done"
OP_ESCALATE = "escalate"

_CLICK_ROLES = frozenset(
    {
        "AXButton",
        "AXLink",
        "AXCheckBox",
        "AXRadioButton",
        "AXPopUpButton",
        "AXMenuItem",
        "AXMenuButton",
        "AXTab",
        "AXCell",
        "AXRow",
        "AXComboBox",
        "AXImage",
    }
)
_FOCUS_ROLES = frozenset(
    {
        "AXTextField",
        "AXTextArea",
        "AXSearchField",
        "AXComboBox",
        "AXPopUpButton",
    }
)
_TYPE_ROLES = frozenset({"AXTextField", "AXTextArea", "AXSearchField", "AXComboBox"})

_CONFIRM_RE = re.compile(
    r"\b("
    r"send|submit|publish|post|purchase|buy|pay|checkout|order|"
    r"delete|remove|uninstall|install|erase|wipe|"
    r"password|credential|account|security|privacy|"
    r"sign[\s-]?out|log[\s-]?out|transfer|confirm|"
    r"place order|add to cart|pay now|donate"
    r")\b",
    re.I,
)
_SECRET_TASK_RE = re.compile(
    r"\b("
    r"password|passwd|passcode|pin\b|otp|one[\s-]?time|"
    r"credit\s*card|card\s*number|cvv|cvc|ssn|"
    r"api[\s_-]?key|access[\s_-]?token|bearer\s+token|secret|"
    r"private\s*key|seed\s*phrase|recovery\s*phrase|mnemonic|"
    r"auth(?:entication)?\s*code|verification\s*code"
    r")\b",
    re.I,
)
# Explicit credential assignment / paste patterns (conservative).
_SECRET_ASSIGN_RE = re.compile(
    r"(?ix)"
    r"(?:"
    r"(?:password|passwd|passcode|pin|otp|secret|token|api[\s_-]?key|"
    r"access[\s_-]?token|cvv|cvc|private\s*key|seed\s*phrase|recovery\s*phrase)"
    r"\s*(?:is|=|:|→|->)\s*\S+"
    r"|"
    r"(?:type|enter|paste|fill(?:\s+in)?)\s+"
    r"(?:my\s+|the\s+|a\s+)?"
    r"(?:password|passwd|passcode|pin|otp|secret|token|api[\s_-]?key|"
    r"cvv|private\s*key|seed\s*phrase)"
    r")"
)
# High-entropy secret-looking blobs (sk-..., long hex, PEM headers).
_SECRET_BLOB_RE = re.compile(
    r"(?ix)"
    r"(?:sk-[A-Za-z0-9]{16,}"
    r"|-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----"
    r"|\b(?:[A-Fa-f0-9]{32}|[A-Za-z0-9_\-]{40,})\b)"
)
_SCROLL_CORNER_MARGIN = 48.0
_FRAME_OVERLAP_IOU = 0.55
_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
_QUOTED_RE = re.compile(r"[\"']([^\"']{1,200})[\"']")
_EXPLICIT_RE = re.compile(
    r"(?i)\b(?:search(?:\s+for)?|type|enter|look\s+up|find|open|go\s+to|navigate\s+to)"
    r"\s+([A-Za-z0-9][\w .,'/-]{1,120})"
)

_ROLE_COMPAT = {
    "AXButton": frozenset({"AXButton", "AXLink", "AXMenuItem", "AXMenuButton"}),
    "AXLink": frozenset({"AXLink", "AXButton"}),
    "AXTextField": frozenset({"AXTextField", "AXSearchField"}),
    "AXSearchField": frozenset({"AXSearchField", "AXTextField"}),
    "AXTextArea": frozenset({"AXTextArea"}),
    "AXSecureTextField": frozenset({"AXSecureTextField"}),
    "AXCheckBox": frozenset({"AXCheckBox"}),
    "AXRadioButton": frozenset({"AXRadioButton"}),
    "AXComboBox": frozenset({"AXComboBox", "AXPopUpButton"}),
    "AXPopUpButton": frozenset({"AXPopUpButton", "AXComboBox"}),
    "AXTab": frozenset({"AXTab"}),
    "AXMenuItem": frozenset({"AXMenuItem", "AXMenuButton", "AXButton"}),
}


def _norm_label(text: str) -> str:
    return " ".join((text or "").casefold().split())


def _frame_center(frame: ElementFrame | None) -> tuple[float, float] | None:
    if frame is None:
        return None
    if frame.width <= 0 or frame.height <= 0:
        return None
    if any(math.isnan(v) for v in (frame.x, frame.y, frame.width, frame.height)):
        return None
    return frame.x + frame.width / 2.0, frame.y + frame.height / 2.0


def _frame_valid(frame: ElementFrame | None) -> bool:
    return _frame_center(frame) is not None


def _frame_area(frame: ElementFrame | None) -> float:
    if frame is None:
        return 0.0
    return max(0.0, float(frame.width)) * max(0.0, float(frame.height))


def _frame_contains(outer: ElementFrame | None, inner: ElementFrame | None) -> bool:
    if outer is None or inner is None:
        return False
    return (
        inner.x >= outer.x - 1
        and inner.y >= outer.y - 1
        and inner.x + inner.width <= outer.x + outer.width + 1
        and inner.y + inner.height <= outer.y + outer.height + 1
    )


def _safe_ui_fragment(text: str, *, limit: int = 48) -> str:
    """UI labels are untrusted state — never treat as instructions."""
    cleaned = " ".join((text or "").split())
    cleaned = cleaned.replace("\n", " ").replace("\r", " ")
    if len(cleaned) > limit:
        cleaned = cleaned[:limit] + "…"
    return cleaned


def _candidate_id(op: str, element_id: str | None = None, *parts: str) -> str:
    """Opaque id — never embeds typed text or secrets."""
    material = "|".join((op, element_id or "", *parts))
    digest = hashlib.blake2b(material.encode("utf-8"), digest_size=8).hexdigest()
    return f"cand_{digest}"


def _text_fingerprint(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=6).hexdigest()


def _frame_iou(a: ElementFrame | None, b: ElementFrame | None) -> float:
    if a is None or b is None:
        return 0.0
    ax2, ay2 = a.x + a.width, a.y + a.height
    bx2, by2 = b.x + b.width, b.y + b.height
    ix1, iy1 = max(a.x, b.x), max(a.y, b.y)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    union = _frame_area(a) + _frame_area(b) - inter
    if union <= 0:
        return 0.0
    return inter / union


def _frames_substantially_overlap(
    a: ElementFrame | None, b: ElementFrame | None
) -> bool:
    if a is None or b is None:
        return False
    if _frame_contains(a, b) or _frame_contains(b, a):
        return True
    return _frame_iou(a, b) >= _FRAME_OVERLAP_IOU


def looks_like_secret_task(task: str) -> bool:
    text = task or ""
    if _SECRET_ASSIGN_RE.search(text) or _SECRET_BLOB_RE.search(text):
        return True
    # Avoid false positives on topical phrases like "password manager comparison"
    # unless they also look like credential entry / assignment.
    if re.search(
        r"(?i)\bpassword\s+manager\b|\bpassword\s+comparison\b|\bcompare\s+passwords\b",
        text,
    ):
        return False
    return bool(_SECRET_TASK_RE.search(text))


def classify_jev_input_privacy(
    goal: str = "",
    subgoal: str = "",
) -> PrivacyGateResult:
    """Decide whether goal/subgoal may be sent to TypeSafe.

    Returns a privacy-safe reason that never echoes secret values.
    """
    for label, text in (("goal", goal or ""), ("subgoal", subgoal or "")):
        raw = text.strip()
        if not raw:
            continue
        if _SECRET_ASSIGN_RE.search(raw) or _SECRET_BLOB_RE.search(raw):
            category = "credential_assignment"
            if re.search(r"(?i)\botp|one[\s-]?time|verification\s*code", raw):
                category = "otp"
            elif re.search(r"(?i)api[\s_-]?key|access[\s_-]?token|bearer|sk-", raw):
                category = "api_key"
            elif re.search(r"(?i)private\s*key|seed\s*phrase|recovery|mnemonic", raw):
                category = "private_key"
            elif re.search(r"(?i)cvv|cvc|credit\s*card|card\s*number", raw):
                category = "payment"
            elif re.search(r"(?i)password|passwd|passcode|\bpin\b", raw):
                category = "password"
            return PrivacyGateResult(
                allowed=False,
                reason=f"task contains sensitive data ({category}); bypassing Jev",
                category=category,
            )
        if looks_like_secret_task(raw):
            # Topical "password manager" already filtered inside looks_like_secret_task.
            category = "sensitive_task"
            if re.search(r"(?i)\botp|one[\s-]?time|verification\s*code", raw):
                category = "otp"
            elif re.search(r"(?i)api[\s_-]?key|token|sk-", raw):
                category = "api_key"
            elif re.search(r"(?i)private\s*key|seed\s*phrase|recovery", raw):
                category = "private_key"
            elif re.search(r"(?i)cvv|cvc|credit\s*card", raw):
                category = "payment"
            elif re.search(r"(?i)password|passwd|passcode|\bpin\b", raw):
                category = "password"
            return PrivacyGateResult(
                allowed=False,
                reason=f"task contains sensitive data ({category}); bypassing Jev",
                category=category,
            )
    return PrivacyGateResult(allowed=True, reason="ok", category="")


def extract_task_text(task: str) -> str | None:
    """Conservatively extract text that is explicitly present in the user task.

    Returns None when extraction is ambiguous or the task looks credential-related.
    Never invents passwords, OTPs, payment details, or other secrets.
    """
    raw = (task or "").strip()
    if not raw:
        return None
    if looks_like_secret_task(raw):
        return None

    quotes = [
        m.group(1).strip() for m in _QUOTED_RE.finditer(raw) if m.group(1).strip()
    ]
    quotes = [q for q in quotes if not looks_like_secret_task(q)]
    if len(quotes) == 1:
        return quotes[0]
    if len(quotes) > 1:
        # Multiple distinct quotes → ambiguous.
        uniq = {_norm_label(q) for q in quotes}
        if len(uniq) > 1:
            return None
        return quotes[0]

    urls = [m.group(0).rstrip(".,);]") for m in _URL_RE.finditer(raw)]
    if len(urls) == 1:
        return urls[0]
    if len(urls) > 1:
        return None

    explicit = _EXPLICIT_RE.search(raw)
    if explicit:
        value = explicit.group(1).strip(" .,;:")
        # Cut trailing instructional clauses.
        value = re.split(
            r"\b(?:and|then|after|before|on the|in the|with the)\b", value, maxsplit=1
        )[0]
        value = value.strip(" .,;:")
        if 1 < len(value) <= 120 and not looks_like_secret_task(value):
            # Reject bare stopwords / too generic.
            if value.casefold() not in {
                "it",
                "this",
                "that",
                "there",
                "here",
                "please",
            }:
                return value
    return None


def action_requires_confirmation(
    *,
    op: str,
    element: UIElement | None = None,
    task: str = "",
    text: str = "",
) -> bool:
    """Local safety policy — Jev does not decide this."""
    if element is not None and element.sensitive:
        return True
    if op == OP_TYPE and (looks_like_secret_task(task) or looks_like_secret_task(text)):
        return True
    haystacks = [
        task or "",
        text or "",
        "" if element is None else element.label,
        "" if element is None else element.description,
        "" if element is None else element.role,
        "" if element is None else element.safe_value(),
    ]
    for blob in haystacks:
        if _CONFIRM_RE.search(blob or ""):
            return True
    if op in {OP_DONE} and _CONFIRM_RE.search(task or ""):
        return True
    return False


def _element_rank_key(el: UIElement) -> tuple:
    clickable = 0 if el.role in _CLICK_ROLES else 1
    typed = 0 if el.role in _TYPE_ROLES else 1
    has_action = 0 if el.supported_actions else 1
    focused = 0 if el.focused else 1
    return (
        focused,
        clickable,
        typed,
        has_action,
        el.role,
        _norm_label(el.label),
        el.id,
    )


def dedupe_elements(
    elements: Sequence[UIElement],
    *,
    handles: Mapping[str, Any] | None = None,
) -> list[UIElement]:
    """Drop true duplicates; keep spatially distinct same-label controls.

    Collapses only when IDs match, native handles match, frames substantially
    overlap / nest with matching semantics, or equivalent repeated AX nodes.
    Same-label controls with distinct frames are retained.
    """
    kept: list[UIElement] = []
    for el in sorted(elements, key=_element_rank_key):
        if not el.enabled:
            continue
        dup = False
        for i, other in enumerate(kept):
            if el.id and other.id and el.id == other.id:
                dup = True
                break
            if handles is not None:
                h1 = handles.get(el.id)
                h2 = handles.get(other.id)
                if h1 is not None and h2 is not None and h1 is h2:
                    prefer_el = (
                        bool(el.supported_actions) and not other.supported_actions
                    )
                    if prefer_el or (
                        _frame_area(el.frame) < _frame_area(other.frame)
                        and bool(el.supported_actions) == bool(other.supported_actions)
                    ):
                        kept[i] = el
                    dup = True
                    break
            same_semantics = el.role == other.role and _norm_label(
                el.label
            ) == _norm_label(other.label)
            if not same_semantics:
                # Click-role family with identical labels still needs overlap.
                if not (
                    el.role in _CLICK_ROLES
                    and other.role in _CLICK_ROLES
                    and _norm_label(el.label)
                    and _norm_label(el.label) == _norm_label(other.label)
                ):
                    continue
                same_semantics = True
            if not _frames_substantially_overlap(el.frame, other.frame):
                # Spatially distinct — keep both.
                continue
            prefer_el = (
                (bool(el.supported_actions) and not other.supported_actions)
                or (
                    _frame_area(el.frame) < _frame_area(other.frame)
                    and bool(el.supported_actions) == bool(other.supported_actions)
                )
                or (_frame_area(el.frame) > 0 and _frame_area(other.frame) == 0)
            )
            if prefer_el:
                kept[i] = el
            dup = True
            break
        if not dup:
            kept.append(el)
    return kept


def _region_hint(frame: ElementFrame | None) -> str:
    center = _frame_center(frame)
    if center is None:
        return "unknown-region"
    x, y = center
    # Coarse regions only — not raw coordinates in candidate IDs.
    horiz = "left" if x < 400 else ("right" if x > 900 else "center")
    vert = "top" if y < 300 else ("bottom" if y > 700 else "mid")
    return f"{vert}-{horiz}"


def _describe_element(
    op: str,
    el: UIElement,
    *,
    index: int | None = None,
    peer_count: int = 1,
) -> str:
    center = _frame_center(el.frame)
    loc = f" at ({center[0]:.0f},{center[1]:.0f})" if center else ""
    value = el.safe_value()
    value_bit = f" value={_safe_ui_fragment(value)!r}" if value else ""
    label = _safe_ui_fragment(el.label) or "(unlabeled)"
    disambig = ""
    if peer_count > 1:
        region = _region_hint(el.frame)
        idx = f" #{index}" if index is not None else ""
        disambig = f" [{region}{idx} of {peer_count}]"
    return (
        f"{op} on untrusted UI state role={el.role} "
        f"label={label!r}{value_bit}{disambig}{loc}"
    )


def _make_action(
    *,
    op: str,
    kind: ActionKind,
    element: UIElement | None = None,
    arguments: Mapping[str, Any] | None = None,
    task: str = "",
    id_parts: Sequence[str] = (),
) -> GroundedAction:
    args = dict(arguments or {})
    args["op"] = op
    text = str(args.get("text") or "")
    requires = action_requires_confirmation(
        op=op, element=element, task=task, text=text
    )
    sensitive = bool(element.sensitive) if element is not None else False
    if op == OP_TYPE:
        sensitive = sensitive or looks_like_secret_task(text)
        # Fingerprint text for id uniqueness without embedding secrets.
        id_parts = tuple(id_parts) + (_text_fingerprint(text),)
    action_id = _candidate_id(op, None if element is None else element.id, *id_parts)
    if element is None:
        description = {
            OP_ENTER: "Press Enter",
            OP_ESCAPE: "Press Escape",
            OP_TAB: "Press Tab",
            OP_SCROLL_DOWN: "Scroll down",
            OP_SCROLL_UP: "Scroll up",
            OP_WAIT: "Wait briefly",
            OP_DONE: "Mark task done (requires verification)",
            OP_ESCALATE: "Escalate to the vision computer-use agent",
        }.get(op, op)
    else:
        description = _describe_element(op, element)
    return GroundedAction(
        action_id=action_id,
        kind=kind,
        element_id=None if element is None else element.id,
        description=description,
        arguments=args,
        requires_confirmation=requires,
        sensitive=sensitive,
    )


def _disambiguate_action_descriptions(
    actions: Sequence[GroundedAction],
    elements_by_id: Mapping[str, UIElement],
) -> list[GroundedAction]:
    """Give same-label peers distinguishable safe descriptions (not IDs)."""
    groups: dict[tuple[str, str, str], list[int]] = {}
    for i, action in enumerate(actions):
        el_id = action.element_id or ""
        el = elements_by_id.get(el_id)
        if el is None:
            continue
        key = (
            str(action.arguments.get("op") or ""),
            el.role,
            _norm_label(el.label),
        )
        groups.setdefault(key, []).append(i)

    out = list(actions)
    for indices in groups.values():
        if len(indices) < 2:
            continue
        # Stable order by element id then action id.
        ordered = sorted(
            indices,
            key=lambda i: (
                out[i].element_id or "",
                out[i].action_id,
            ),
        )
        peer_count = len(ordered)
        for rank, i in enumerate(ordered, start=1):
            action = out[i]
            el = elements_by_id.get(action.element_id or "")
            if el is None:
                continue
            op = str(action.arguments.get("op") or "")
            desc = _describe_element(op, el, index=rank, peer_count=peer_count)
            out[i] = GroundedAction(
                action_id=action.action_id,
                kind=action.kind,
                element_id=action.element_id,
                description=desc,
                arguments=action.arguments,
                requires_confirmation=action.requires_confirmation,
                sensitive=action.sensitive,
            )
    return out


def prune_candidates_for_choice(
    candidates: Sequence[GroundedAction],
    *,
    limit: int | None = None,
) -> list[GroundedAction]:
    """Deterministically prune to the Choice hard ceiling; keep escalate/wait/done."""
    hard = min(
        JEV_CHOICE_MAX_OPTIONS,
        JEV_MAX_CANDIDATES_HARD_CEILING,
        limit if limit is not None else JEV_MAX_CANDIDATES_HARD_CEILING,
    )
    hard = max(1, int(hard))
    items = list(candidates)
    if len(items) <= hard:
        return items

    reserved_ops = {OP_ESCALATE, OP_DONE, OP_WAIT}
    reserved = [a for a in items if str(a.arguments.get("op") or "") in reserved_ops]
    # Prefer one of each reserved op, escalate last.
    by_op: dict[str, GroundedAction] = {}
    for a in reserved:
        op = str(a.arguments.get("op") or "")
        by_op[op] = a
    reserved_final: list[GroundedAction] = []
    for op in (OP_WAIT, OP_DONE, OP_ESCALATE):
        if op in by_op:
            reserved_final.append(by_op[op])
    primaries = [
        a for a in items if str(a.arguments.get("op") or "") not in reserved_ops
    ]
    if hard == 1:
        return [by_op.get(OP_ESCALATE) or items[0]]
    if hard == 2:
        done = by_op.get(OP_DONE)
        esc = by_op.get(OP_ESCALATE) or items[0]
        return [done, esc] if done is not None else primaries[:1] + [esc]

    room = max(0, hard - len(reserved_final))
    chosen = primaries[:room] + reserved_final
    # Unique ids, escalate guaranteed.
    seen: set[str] = set()
    unique: list[GroundedAction] = []
    for a in chosen:
        if a.action_id in seen:
            continue
        seen.add(a.action_id)
        unique.append(a)
    if not any(str(a.arguments.get("op") or "") == OP_ESCALATE for a in unique):
        esc = by_op.get(OP_ESCALATE)
        if esc is not None:
            unique = unique[: max(0, hard - 1)] + [esc]
    return unique[:hard]


def enumerate_grounded_actions(
    snapshot: UISnapshot,
    task: str,
    recent_actions: (
        Sequence[GroundedAction] | Sequence[Mapping[str, Any]] | None
    ) = None,
    config: JevConfig | None = None,
) -> list[GroundedAction]:
    """Build complete executable candidates from a structured AX snapshot.

    Screen text never invents new action types. Reserved wait/done/escalate
    slots are always present (escalate at minimum when the budget is tiny).
    """
    cfg = config or load_jev_config({})
    task = task or ""
    recent_keys = set()
    for item in recent_actions or ():
        if isinstance(item, GroundedAction):
            recent_keys.add(
                (
                    item.kind.value,
                    item.element_id or "",
                    str(item.arguments.get("op") or ""),
                )
            )
        elif isinstance(item, Mapping):
            recent_keys.add(
                (
                    str(item.get("kind") or ""),
                    str(item.get("element_id") or ""),
                    str((item.get("arguments") or {}).get("op") or ""),
                )
            )

    elements = dedupe_elements(
        [el for el in snapshot.elements if el.enabled],
        handles={
            eid: snapshot.get_handle(eid)
            for eid in (e.id for e in snapshot.elements if e.id)
        },
    )
    elements_by_id = {el.id: el for el in elements}
    typed_text = extract_task_text(task)

    primaries: list[GroundedAction] = []

    for el in elements:
        if el.role in _CLICK_ROLES or "AXPress" in el.supported_actions:
            if el.role == "AXSecureTextField":
                continue
            # Prefer native press or a valid frame.
            if "AXPress" in el.supported_actions or _frame_valid(el.frame):
                primaries.append(
                    _make_action(
                        op=OP_CLICK,
                        kind=ActionKind.CLICK,
                        element=el,
                        arguments=(
                            {"ax_action": "AXPress"}
                            if "AXPress" in el.supported_actions
                            else {}
                        ),
                        task=task,
                    )
                )
        if el.role in _FOCUS_ROLES and not el.sensitive:
            primaries.append(
                _make_action(
                    op=OP_FOCUS,
                    kind=ActionKind.FOCUS,
                    element=el,
                    task=task,
                )
            )
        if (
            typed_text
            and el.role in _TYPE_ROLES
            and not el.sensitive
            and el.role != "AXSecureTextField"
        ):
            primaries.append(
                _make_action(
                    op=OP_TYPE,
                    kind=ActionKind.TYPE,
                    element=el,
                    arguments={"text": typed_text},
                    task=task,
                )
            )

    # Global keyboard / scroll candidates (not derived from screen-invented ops).
    primaries.append(
        _make_action(
            op=OP_ENTER,
            kind=ActionKind.KEYPRESS,
            arguments={"keys": ["enter"]},
            task=task,
        )
    )
    primaries.append(
        _make_action(
            op=OP_ESCAPE,
            kind=ActionKind.KEYPRESS,
            arguments={"keys": ["escape"]},
            task=task,
        )
    )
    primaries.append(
        _make_action(
            op=OP_TAB, kind=ActionKind.KEYPRESS, arguments={"keys": ["tab"]}, task=task
        )
    )
    primaries.append(
        _make_action(
            op=OP_SCROLL_DOWN,
            kind=ActionKind.SCROLL,
            arguments={"scroll_y": 400, "scroll_x": 0},
            task=task,
        )
    )
    primaries.append(
        _make_action(
            op=OP_SCROLL_UP,
            kind=ActionKind.SCROLL,
            arguments={"scroll_y": -400, "scroll_x": 0},
            task=task,
        )
    )

    def _sort_key(action: GroundedAction) -> tuple:
        recent = (
            1
            if (
                action.kind.value,
                action.element_id or "",
                str(action.arguments.get("op") or ""),
            )
            in recent_keys
            else 0
        )
        op = str(action.arguments.get("op") or "")
        op_rank = {
            OP_CLICK: 0,
            OP_TYPE: 1,
            OP_FOCUS: 2,
            OP_ENTER: 3,
            OP_TAB: 4,
            OP_SCROLL_DOWN: 5,
            OP_SCROLL_UP: 6,
            OP_ESCAPE: 7,
        }.get(op, 20)
        return (recent, op_rank, action.element_id or "", action.action_id)

    primaries.sort(key=_sort_key)

    # De-dupe identical action ids (can happen if generation is repeated).
    seen_ids: set[str] = set()
    unique_primaries: list[GroundedAction] = []
    for action in primaries:
        if action.action_id in seen_ids:
            continue
        seen_ids.add(action.action_id)
        unique_primaries.append(action)

    wait = _make_action(
        op=OP_WAIT, kind=ActionKind.WAIT, arguments={"ms": 500}, task=task
    )
    done = _make_action(op=OP_DONE, kind=ActionKind.COMPLETE, task=task)
    escalate = _make_action(op=OP_ESCALATE, kind=ActionKind.ESCALATE, task=task)

    budget = max(
        1,
        min(
            int(cfg.max_candidates),
            JEV_MAX_CANDIDATES_HARD_CEILING,
            JEV_CHOICE_MAX_OPTIONS,
        ),
    )
    reserved = [wait, done, escalate]
    # Always keep escalate; keep wait/done when budget allows.
    if budget == 1:
        return [escalate]
    if budget == 2:
        return [done, escalate]
    primary_budget = max(0, budget - len(reserved))
    chosen = unique_primaries[:primary_budget] + reserved
    # Guarantee escalate is present even if somehow dropped.
    if not any(a.arguments.get("op") == OP_ESCALATE for a in chosen):
        chosen = chosen[: max(0, budget - 1)] + [escalate]
    if len(chosen) > budget:
        chosen = chosen[:budget]
    chosen = _disambiguate_action_descriptions(chosen, elements_by_id)
    return prune_candidates_for_choice(chosen, limit=budget)


def candidates_by_id(
    candidates: Sequence[GroundedAction],
) -> dict[str, GroundedAction]:
    return {c.action_id: c for c in candidates}


def validate_grounded_action(
    action: GroundedAction,
    observed_snapshot: UISnapshot,
    current_snapshot: UISnapshot,
) -> ValidationResult:
    """Verify an element-targeted action is still fresh against a new snapshot."""
    op = str(action.arguments.get("op") or "")
    if op in {
        OP_WAIT,
        OP_DONE,
        OP_ESCALATE,
        OP_ENTER,
        OP_ESCAPE,
        OP_TAB,
        OP_SCROLL_DOWN,
        OP_SCROLL_UP,
    }:
        if current_snapshot.error and op not in {OP_ESCALATE, OP_WAIT, OP_DONE}:
            return ValidationResult(
                ok=False, reason=f"ui unavailable: {current_snapshot.error}"
            )
        return ValidationResult(ok=True, reason="non-element action")

    if not action.element_id:
        return ValidationResult(ok=False, reason="missing element_id")

    if (
        observed_snapshot.process_id is not None
        and current_snapshot.process_id is not None
    ):
        if observed_snapshot.process_id != current_snapshot.process_id:
            return ValidationResult(ok=False, reason="process id changed")
    if observed_snapshot.app_name and current_snapshot.app_name:
        if _norm_label(observed_snapshot.app_name) != _norm_label(
            current_snapshot.app_name
        ):
            return ValidationResult(ok=False, reason="application changed")
    if observed_snapshot.window_title and current_snapshot.window_title:
        # Compatible window: allow suffix/prefix drift but not total replacement.
        obs = _norm_label(observed_snapshot.window_title)
        cur = _norm_label(current_snapshot.window_title)
        if obs not in cur and cur not in obs and obs != cur:
            return ValidationResult(ok=False, reason="window title changed materially")

    observed = next(
        (e for e in observed_snapshot.elements if e.id == action.element_id), None
    )
    current = next(
        (e for e in current_snapshot.elements if e.id == action.element_id), None
    )
    if current is None:
        # Try soft match by role+label from observed.
        if observed is not None:
            current = next(
                (
                    e
                    for e in current_snapshot.elements
                    if e.role == observed.role
                    and _norm_label(e.label) == _norm_label(observed.label)
                    and e.enabled
                ),
                None,
            )
        if current is None:
            return ValidationResult(ok=False, reason="element missing")

    if not current.enabled:
        return ValidationResult(ok=False, reason="element disabled", element=current)

    if observed is not None:
        compat = _ROLE_COMPAT.get(observed.role, frozenset({observed.role}))
        if current.role not in compat:
            return ValidationResult(ok=False, reason="role changed", element=current)
        if observed.sensitive != current.sensitive:
            return ValidationResult(
                ok=False, reason="sensitive status changed", element=current
            )
        if _norm_label(observed.label) and _norm_label(observed.label) != _norm_label(
            current.label
        ):
            return ValidationResult(ok=False, reason="label changed", element=current)
        obs_val = observed.safe_value()
        cur_val = current.safe_value()
        if obs_val and cur_val and _norm_label(obs_val) != _norm_label(cur_val):
            # Value drift is material for non-type actions; type may change value.
            if op != OP_TYPE:
                return ValidationResult(
                    ok=False, reason="value changed", element=current
                )

    if op == OP_CLICK and not (
        "AXPress" in current.supported_actions or _frame_valid(current.frame)
    ):
        return ValidationResult(
            ok=False, reason="no valid frame or AXPress", element=current
        )

    if (
        op in {OP_CLICK, OP_FOCUS, OP_TYPE}
        and current.frame is not None
        and not _frame_valid(current.frame)
    ):
        return ValidationResult(ok=False, reason="invalid frame", element=current)

    if (
        current_snapshot.handle_count > 0
        and current_snapshot.get_handle(current.id) is None
    ):
        return ValidationResult(
            ok=False, reason="native handle missing", element=current
        )

    return ValidationResult(
        ok=True,
        reason="fresh",
        current_frame=current.frame,
        element=current,
    )


def evaluate_decision_gate(
    decision: JevDecision,
    candidates: Sequence[GroundedAction] | Mapping[str, GroundedAction],
    config: JevConfig,
    *,
    validation: ValidationResult | None = None,
    confirmed: bool = False,
    steps_used: int = 0,
    goal: str = "",
) -> DecisionGateResult:
    """Pure confidence / safety gate. Completion yields requires_verification."""
    by_id = (
        dict(candidates)
        if isinstance(candidates, Mapping)
        else candidates_by_id(list(candidates))
    )

    if decision.error:
        return DecisionGateResult(
            allowed=False,
            reason=f"malformed decision: {decision.error}",
            verdict=JevGateVerdict.FALLBACK,
        )
    if not decision.selected_candidate_id:
        return DecisionGateResult(
            allowed=False,
            reason="missing selected candidate id",
            verdict=JevGateVerdict.FALLBACK,
        )
    if steps_used >= config.max_steps:
        return DecisionGateResult(
            allowed=False,
            reason="step budget exceeded",
            verdict=JevGateVerdict.FALLBACK,
        )
    if decision.stuck_probability >= config.stuck_threshold:
        return DecisionGateResult(
            allowed=False,
            reason="stuck probability too high",
            verdict=JevGateVerdict.FALLBACK,
        )

    action = by_id.get(decision.selected_candidate_id)
    if action is None:
        return DecisionGateResult(
            allowed=False,
            reason="unknown candidate id",
            verdict=JevGateVerdict.REJECT,
        )

    # ax-pilot AnswerHandler.guardAction — code-owned destructive block.
    from jev.text_candidates import goal_names_destructive, label_looks_destructive

    if decision.is_destructive_probability >= 0.5 and not goal_names_destructive(goal):
        return DecisionGateResult(
            allowed=False,
            reason="is_destructive Noul blocked (goal does not name the operation)",
            action=action,
            verdict=JevGateVerdict.REJECT,
        )
    if label_looks_destructive(action.description) and not goal_names_destructive(goal):
        return DecisionGateResult(
            allowed=False,
            reason="selected action looks destructive and goal does not name it",
            action=action,
            requires_confirmation=True,
            verdict=JevGateVerdict.NEEDS_CONFIRMATION,
        )

    if decision.confidence < config.min_confidence:
        return DecisionGateResult(
            allowed=False,
            reason="confidence below minimum",
            action=action,
            verdict=JevGateVerdict.FALLBACK,
        )
    margin = decision.margin
    if margin <= 0 and decision.selected_probability and decision.second_probability:
        margin = decision.selected_probability - decision.second_probability
    if margin < config.min_margin:
        return DecisionGateResult(
            allowed=False,
            reason="winning margin too narrow",
            action=action,
            verdict=JevGateVerdict.FALLBACK,
        )

    if validation is not None and not validation.ok:
        return DecisionGateResult(
            allowed=False,
            reason=f"stale element: {validation.reason}",
            action=action,
            verdict=JevGateVerdict.FALLBACK,
        )

    if action.requires_confirmation and not confirmed:
        return DecisionGateResult(
            allowed=False,
            reason="action requires confirmation",
            requires_confirmation=True,
            action=action,
            verdict=JevGateVerdict.NEEDS_CONFIRMATION,
        )

    op = str(action.arguments.get("op") or "")
    if op == OP_DONE or action.kind is ActionKind.COMPLETE:
        if decision.complete_probability >= config.complete_threshold:
            return DecisionGateResult(
                allowed=False,
                reason="completion requires verification",
                requires_verification=True,
                action=action,
                verdict=JevGateVerdict.FALLBACK,
            )
        return DecisionGateResult(
            allowed=False,
            reason="complete probability below threshold",
            action=action,
            verdict=JevGateVerdict.FALLBACK,
        )

    if op == OP_ESCALATE or action.kind is ActionKind.ESCALATE:
        return DecisionGateResult(
            allowed=False,
            reason="escalate to vision agent",
            action=action,
            verdict=JevGateVerdict.FALLBACK,
        )

    return DecisionGateResult(
        allowed=True,
        reason="ok",
        action=action,
        verdict=JevGateVerdict.ALLOW,
    )


@dataclass(frozen=True)
class ExecutionPlan:
    """How a grounded action would be performed (not executed until requested)."""

    method: str
    action: GroundedAction
    screen_x: float | None = None
    screen_y: float | None = None
    ax_action: str | None = None
    keys: tuple[str, ...] = ()
    text: str | None = None
    notes: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "action_id": self.action.action_id,
            "screen_x": self.screen_x,
            "screen_y": self.screen_y,
            "ax_action": self.ax_action,
            "keys": list(self.keys),
            "text": None if self.action.sensitive else self.text,
            "notes": self.notes,
        }


def resolve_safe_scroll_point(
    snapshot: UISnapshot,
    *,
    element: UIElement | None = None,
    monitors: Sequence[Mapping[str, Any]] | None = None,
    pointer: tuple[float, float] | None = None,
    margin: float = _SCROLL_CORNER_MARGIN,
) -> tuple[float, float] | None:
    """Resolve a scroll pointer target that never lands on a display corner.

    Preference order:
      1. Verified element / focused control with a valid frame
      2. Focused window approximate center (focused element or app content)
      3. Current pointer if it lies in a monitor's safe interior
      4. Main display safe interior center
    """
    margin = max(8.0, float(margin))

    def _mons() -> list[dict[str, Any]]:
        if monitors is not None:
            return [dict(m) for m in monitors]
        try:
            from actions import list_monitors

            return list(list_monitors() or [])
        except Exception:
            return []

    mon_list = _mons()

    def _is_corner(x: float, y: float) -> bool:
        if not mon_list:
            # Single unknown display: treat near-origin as unsafe.
            return x <= margin and y <= margin
        for m in mon_list:
            mx = float(m.get("x", 0))
            my = float(m.get("y", 0))
            mw = float(m.get("width", 0))
            mh = float(m.get("height", 0))
            if mw <= 0 or mh <= 0:
                continue
            corners = (
                (mx, my),
                (mx + mw - 1, my),
                (mx, my + mh - 1),
                (mx + mw - 1, my + mh - 1),
            )
            for cx, cy in corners:
                if abs(x - cx) <= margin and abs(y - cy) <= margin:
                    return True
        return False

    def _in_safe_interior(x: float, y: float) -> bool:
        if _is_corner(x, y):
            return False
        if not mon_list:
            return x > margin and y > margin
        for m in mon_list:
            mx = float(m.get("x", 0))
            my = float(m.get("y", 0))
            mw = float(m.get("width", 0))
            mh = float(m.get("height", 0))
            if mw <= 2 * margin or mh <= 2 * margin:
                continue
            if (
                mx + margin <= x <= mx + mw - margin
                and my + margin <= y <= my + mh - margin
            ):
                return True
        return False

    def _accept(pt: tuple[float, float] | None) -> tuple[float, float] | None:
        if pt is None:
            return None
        x, y = float(pt[0]), float(pt[1])
        if not math.isfinite(x) or not math.isfinite(y):
            return None
        if not _in_safe_interior(x, y):
            return None
        return (x, y)

    # 1. Explicit / focused element with valid frame.
    candidates: list[UIElement] = []
    if element is not None:
        candidates.append(element)
    focused = next((e for e in snapshot.elements if e.focused and e.enabled), None)
    if focused is not None:
        candidates.append(focused)
    for el in candidates:
        pt = _accept(_frame_center(el.frame))
        if pt is not None:
            return pt

    # 2. Approximate window interior: largest enabled content-like frame.
    content = [
        e
        for e in snapshot.elements
        if e.enabled and _frame_valid(e.frame) and not e.sensitive
    ]
    if content:
        content.sort(key=lambda e: _frame_area(e.frame), reverse=True)
        pt = _accept(_frame_center(content[0].frame))
        if pt is not None:
            return pt

    # 3. Current pointer if safe.
    if pointer is not None:
        pt = _accept((float(pointer[0]), float(pointer[1])))
        if pt is not None:
            return pt
    else:
        try:
            import pyautogui

            pos = pyautogui.position()
            pt = _accept((float(pos[0]), float(pos[1])))
            if pt is not None:
                return pt
        except Exception:
            pass

    # 4. Main display safe interior center.
    main = None
    for m in mon_list:
        if m.get("main"):
            main = m
            break
    if main is None and mon_list:
        main = mon_list[0]
    if main is not None:
        mx = float(main.get("x", 0))
        my = float(main.get("y", 0))
        mw = float(main.get("width", 0))
        mh = float(main.get("height", 0))
        pt = _accept((mx + mw / 2.0, my + mh / 2.0))
        if pt is not None:
            return pt

    return None


def plan_execution(
    action: GroundedAction,
    snapshot: UISnapshot,
    *,
    validation: ValidationResult | None = None,
    monitors: Sequence[Mapping[str, Any]] | None = None,
    pointer: tuple[float, float] | None = None,
) -> ExecutionPlan:
    """Resolve current frame / AX preference. Does not move the mouse."""
    op = str(action.arguments.get("op") or "")
    element = None if validation is None else validation.element
    if element is None and action.element_id:
        element = next(
            (e for e in snapshot.elements if e.id == action.element_id), None
        )

    frame = None if validation is None else validation.current_frame
    if frame is None and element is not None:
        frame = element.frame
    center = _frame_center(frame)

    if op == OP_CLICK and element is not None:
        ax_name = None
        if "AXPress" in element.supported_actions:
            ax_name = "AXPress"
        elif str(action.arguments.get("ax_action") or "") in element.supported_actions:
            ax_name = str(action.arguments.get("ax_action"))
        if ax_name:
            return ExecutionPlan(
                method="ax_press",
                action=action,
                ax_action=ax_name,
                screen_x=None if center is None else center[0],
                screen_y=None if center is None else center[1],
                notes="prefer native AXPress; frame recorded for fallback only",
            )
        if center is None:
            return ExecutionPlan(method="unavailable", action=action, notes="no frame")
        return ExecutionPlan(
            method="coordinate_click",
            action=action,
            screen_x=center[0],
            screen_y=center[1],
            notes="current frame center (Cocoa points)",
        )

    if op == OP_FOCUS and element is not None:
        if (
            "AXRaise" in element.supported_actions
            or "AXPress" in element.supported_actions
        ):
            return ExecutionPlan(
                method="ax_press",
                action=action,
                ax_action=(
                    "AXPress" if "AXPress" in element.supported_actions else "AXRaise"
                ),
            )
        if center is not None:
            return ExecutionPlan(
                method="coordinate_click",
                action=action,
                screen_x=center[0],
                screen_y=center[1],
            )
        return ExecutionPlan(method="unavailable", action=action, notes="cannot focus")

    if op == OP_TYPE:
        text = str(action.arguments.get("text") or "")
        return ExecutionPlan(method="type_text", action=action, text=text)

    if op in {OP_ENTER, OP_ESCAPE, OP_TAB}:
        keys = tuple(str(k) for k in (action.arguments.get("keys") or []))
        return ExecutionPlan(method="keypress", action=action, keys=keys)

    if op in {OP_SCROLL_DOWN, OP_SCROLL_UP}:
        sx = int(action.arguments.get("scroll_x") or 0)
        sy = int(action.arguments.get("scroll_y") or 0)
        if sx == 0 and sy == 0:
            return ExecutionPlan(
                method="unavailable",
                action=action,
                notes="zero-distance scroll",
            )
        point = resolve_safe_scroll_point(
            snapshot,
            element=element,
            monitors=monitors,
            pointer=pointer,
        )
        if point is None:
            return ExecutionPlan(
                method="unavailable",
                action=action,
                notes="no safe scroll point",
            )
        return ExecutionPlan(
            method="scroll",
            action=action,
            screen_x=point[0],
            screen_y=point[1],
            notes="safe scroll point (never corner)",
        )

    if op == OP_WAIT:
        return ExecutionPlan(method="wait", action=action)

    if op in {OP_DONE, OP_ESCALATE}:
        return ExecutionPlan(method="policy", action=action, notes=op)

    return ExecutionPlan(
        method="unavailable", action=action, notes=f"unsupported op {op}"
    )


def execute_grounded_action(
    action: GroundedAction,
    snapshot: UISnapshot,
    *,
    desktop: Any | None = None,
    validation: ValidationResult | None = None,
    ax_perform: Callable[[Any, str], bool] | None = None,
    dry_run: bool = True,
    should_stop: Callable[[], bool] | None = None,
    coords_are_screen: bool = False,
) -> dict[str, Any]:
    """Execute adapter — defaults to dry_run so tests never move the desktop.

    When ``dry_run`` is False, prefers native AX actions, then
    ``DesktopController`` APIs. ``coords_are_screen`` marks AX frame centers
    as Cocoa desktop points (``absolute``) so remapping skips screenshot space.
    """
    plan = plan_execution(action, snapshot, validation=validation)
    result = {"ok": False, "dry_run": dry_run, "plan": plan.to_public_dict()}
    if dry_run:
        result["ok"] = plan.method != "unavailable"
        result["reason"] = "dry_run"
        return result
    if plan.method == "unavailable":
        result["reason"] = plan.notes or "unavailable"
        return result

    def _annotate(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not coords_are_screen:
            return batch
        out: list[dict[str, Any]] = []
        for item in batch:
            if (
                item.get("type") in {"click", "double_click", "move", "scroll"}
                and "x" in item
            ):
                tagged = dict(item)
                tagged["absolute"] = True
                out.append(tagged)
            else:
                out.append(item)
        return out

    if plan.method == "ax_press":
        handle = None
        element_id = action.element_id
        if validation is not None and validation.element is not None:
            element_id = validation.element.id
        if element_id:
            handle = snapshot.get_handle(element_id)
        if handle is not None and ax_perform is not None and plan.ax_action:
            ok = bool(ax_perform(handle, plan.ax_action))
            result["ok"] = ok
            result["reason"] = "ax_press" if ok else "ax_press_failed"
            if ok:
                return result
        # Fall through to coordinates when AX fails.
        if desktop is None or plan.screen_x is None or plan.screen_y is None:
            result["reason"] = "ax_press_failed_no_fallback"
            return result
        desktop.run_actions(
            _annotate([{"type": "click", "x": plan.screen_x, "y": plan.screen_y}]),
            should_stop=should_stop,
        )
        result["ok"] = True
        result["reason"] = "coordinate_fallback"
        return result

    if desktop is None:
        result["reason"] = "desktop controller required"
        return result

    if plan.method == "coordinate_click":
        desktop.run_actions(
            _annotate([{"type": "click", "x": plan.screen_x, "y": plan.screen_y}]),
            should_stop=should_stop,
        )
        result["ok"] = True
        result["reason"] = "coordinate_click"
        return result

    if plan.method == "type_text":
        # Focus first when we have a frame.
        actions: list[dict[str, Any]] = []
        if plan.screen_x is not None and plan.screen_y is not None:
            actions.append({"type": "click", "x": plan.screen_x, "y": plan.screen_y})
        elif validation is not None and validation.current_frame is not None:
            c = _frame_center(validation.current_frame)
            if c:
                actions.append({"type": "click", "x": c[0], "y": c[1]})
        actions.append({"type": "type", "text": plan.text or ""})
        desktop.run_actions(_annotate(actions), should_stop=should_stop)
        result["ok"] = True
        result["reason"] = "type_text"
        return result

    if plan.method == "keypress":
        desktop.run_actions(
            [{"type": "keypress", "keys": list(plan.keys)}],
            should_stop=should_stop,
        )
        result["ok"] = True
        result["reason"] = "keypress"
        return result

    if plan.method == "scroll":
        if plan.screen_x is None or plan.screen_y is None:
            result["reason"] = "no safe scroll point"
            return result
        sx = int(action.arguments.get("scroll_x") or 0)
        sy = int(action.arguments.get("scroll_y") or 0)
        if sx == 0 and sy == 0:
            result["reason"] = "zero-distance scroll"
            return result
        desktop.run_actions(
            _annotate(
                [
                    {
                        "type": "scroll",
                        "x": plan.screen_x,
                        "y": plan.screen_y,
                        "scroll_x": sx,
                        "scroll_y": sy,
                    }
                ]
            ),
            should_stop=should_stop,
        )
        result["ok"] = True
        result["reason"] = "scroll"
        return result

    if plan.method == "wait":
        desktop.run_actions(
            [{"type": "wait", "ms": int(action.arguments.get("ms") or 500)}],
            should_stop=should_stop,
        )
        result["ok"] = True
        result["reason"] = "wait"
        return result

    result["reason"] = f"unhandled method {plan.method}"
    return result
