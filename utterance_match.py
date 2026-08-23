"""Shared utterance matching helpers (URL extract, phrase match, norms)."""

from __future__ import annotations

import re

_HARD_TASK = re.compile(
    r"\b(easyeda|kicad|fusion|solidworks|schematic|pcb|gerber|"
    r"checkout|place an order|wire|routing|cad)\b",
    re.I,
)
_URL_RE = re.compile(
    r"(https?://[^\s]+|(?:www\.)[a-z0-9.-]+\.[a-z]{2,}(?:/[^\s]*)?|"
    r"[a-z0-9.-]+\.[a-z]{2,}(?:/[^\s]*)?)",
    re.I,
)
_STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "to",
        "for",
        "in",
        "on",
        "of",
        "at",
        "please",
        "my",
        "me",
        "it",
        "that",
        "this",
        "with",
        "from",
        "into",
        "then",
        "now",
        "just",
        "can",
        "you",
    }
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s.:/-]", " ", (text or "").lower())).strip()


def content_words(text: str, extra_remove: tuple[str, ...] = ()) -> list[str]:
    lowered = (text or "").lower().replace("google chrome", "chrome")
    words = re.findall(r"[a-z0-9]+", lowered)
    skip = _STOP | {w.lower() for w in extra_remove}
    return [w for w in words if w not in skip and len(w) > 2]


def _extract_urls(text: str) -> list[str]:
    found = [m.group(0).rstrip(".,);") for m in _URL_RE.finditer(text or "")]
    return [u for u in found if "." in u and not re.fullmatch(r"v?\d+(\.\d+)+", u)]


def _phrase_in(utterance: str, phrase: str) -> bool:
    u = _norm(utterance)
    p = _norm(phrase)
    if not p:
        return False
    # Whole-phrase match — avoid "play" matching inside "plays" / "playlist".
    if re.search(rf"(?<!\w){re.escape(p)}(?!\w)", u):
        return True
    words = [w for w in p.split() if len(w) > 2]
    if not words:
        return False
    bag = set(u.split())
    return all(w in bag for w in words)


def match_phrases_for(task: str, param_values: list[str]) -> list[str]:
    stripped = _norm(task)
    for value in param_values:
        stripped = stripped.replace(_norm(value), " ")
    stripped = re.sub(r"\s+", " ", stripped).strip()
    words = content_words(stripped)
    seen: set[str] = set()
    out: list[str] = []
    for w in words:
        if w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out


def frontmost_app_name() -> str | None:
    try:
        from accessibility import frontmost_app_name as _name

        return _name()
    except Exception:
        return None
