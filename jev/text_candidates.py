"""Code-owned text spans from the user goal (inspired by jev-ax-pilot).

Jev only *selects* among these candidates — it never generates free-form text.
Arithmetic is evaluated in Python and exposed as ``facts``.
"""

from __future__ import annotations

import ast
import operator
import re
from collections.abc import Sequence

_KNOWN_APPS = frozenset(
    {
        "notes",
        "system settings",
        "calculator",
        "safari",
        "textedit",
        "finder",
        "mail",
        "messages",
        "reminders",
        "calendar",
        "music",
        "photos",
        "preview",
        "terminal",
        "maps",
        "contacts",
        "stickies",
        "google chrome",
        "firefox",
        "cursor",
    }
)

_QUOTED_RE = re.compile(r"[\"“']([^\"”']+)[\"”']")
_URL_RE = re.compile(
    r"\b((?:https?://)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/\S*)?)",
    re.I,
)
_ARITH_RE = re.compile(
    r"(\d+(?:\.\d+)?(?:\s*[-+*/x×÷]\s*\d+(?:\.\d+)?)+)"
)
_VERB_PATTERNS = (
    r"\b(?:titled|named|called)\s+(.+?)(?=\s+(?:in|into|using|with|and then|then)\b|,|$)",
    r"\b(?:type|enter|write|paste|search for)\s+(.+?)(?=\s+(?:in|into|using|with|and then|then)\b|,|$)",
    r"\b(?:go to|navigate to|visit)\s+(.+?)(?=\s+(?:in|into|using|with|and then|then)\b|,|$)",
)

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
}


def _trim(text: str) -> str:
    return text.strip(" .,;:!?\"“”'")


def _safe_eval_arith(expr: str) -> float | None:
    normalized = (
        expr.replace("x", "*")
        .replace("×", "*")
        .replace("÷", "/")
        .replace(" ", "")
    )
    if not re.fullmatch(r"[0-9.+\-*/()]+", normalized):
        return None
    if not re.search(r"[+\-*/]", normalized):
        return None
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError:
        return None

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return float(_OPS[type(node.op)](_eval(node.operand)))
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return float(_OPS[type(node.op)](_eval(node.left), _eval(node.right)))
        raise ValueError("unsupported")

    try:
        return _eval(tree)
    except Exception:
        return None


def extract_text_candidates(goal: str, *, limit: int = 6) -> list[str]:
    """Ordered, de-duplicated verbatim spans from the goal (most specific first)."""
    raw = (goal or "").strip()
    if not raw:
        return []
    found: list[str] = []

    def add(span: str) -> None:
        cleaned = _trim(span)
        if len(cleaned) < 1:
            return
        if cleaned.casefold() in _KNOWN_APPS:
            return
        if any(cleaned.casefold() == f.casefold() for f in found):
            return
        found.append(cleaned)

    for match in _QUOTED_RE.finditer(raw):
        add(match.group(1))
    for pattern in _VERB_PATTERNS:
        for match in re.finditer(pattern, raw, flags=re.I):
            add(match.group(1))
    for match in _URL_RE.finditer(raw):
        add(match.group(1).rstrip(".,);]"))
    for match in _ARITH_RE.finditer(raw):
        add(match.group(1))
    return found[: max(1, int(limit))]


def arithmetic_facts(candidates: Sequence[str]) -> dict[str, str]:
    """Map ``\"48*12 equals\"`` → ``\"576\"`` for state facts (code-owned math)."""
    facts: dict[str, str] = {}
    for candidate in candidates:
        value = _safe_eval_arith(candidate)
        if value is None:
            continue
        if value == round(value) and abs(value) < 1e15:
            text = str(int(round(value)))
        else:
            text = str(value)
        facts[f"{candidate} equals"] = text
    return facts


# Words that flag destructive UI (ax-pilot TreeFlattener) — goal must name them
# before such an action is allowed.
DESTRUCTIVE_WORDS: frozenset[str] = frozenset(
    {
        "delete",
        "empty trash",
        "erase",
        "send",
        "pay",
        "purchase",
        "buy",
        "remove",
        "discard",
        "trash",
        "uninstall",
        "format",
        "reset",
        "sign out",
        "log out",
        "shut down",
        "restart",
        "checkout",
        "place order",
    }
)


def goal_names_destructive(goal: str) -> bool:
    lowered = (goal or "").casefold()
    return any(word in lowered for word in DESTRUCTIVE_WORDS)


def label_looks_destructive(label: str) -> bool:
    lowered = (label or "").casefold()
    return any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in DESTRUCTIVE_WORDS)
