"""Voice/chat utterance filters (garbage STT, on-screen questions)."""

from __future__ import annotations

import re

_REPEAT_RE = re.compile(r"\b(\w+)(?:\s+\1){3,}\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[A-Za-z']+")
_FILLER = frozenset(
    {
        "a",
        "ah",
        "and",
        "like",
        "the",
        "uh",
        "um",
        "you",
        "know",
        "it",
        "it's",
        "its",
        "not",
        "in",
        "the",
        "room",
    }
)
_SCREEN_RE = re.compile(
    r"\b("
    r"what(?:'s| is|s) (?:this|that|on (?:my |the )?screen)|"
    r"what(?:'s| is) on (?:my |the )?(?:screen|display|monitor)|"
    r"read (?:this|that|the screen|the page|what's on screen)|"
    r"look at (?:this|the screen|my screen|what's on)|"
    r"which (?:window|tab|app)(?: is| are)?|"
    r"can you see|"
    r"describe (?:this|the screen|what you see)|"
    r"what's (?:on )?my (?:screen|display)"
    r")\b",
    re.IGNORECASE,
)


_TAB_RE = re.compile(
    r"\b("
    r"tabs?|browser|chrome|safari|firefox|edge|brave|arc|"
    r"url|link|web ?page|open pages?|"
    r"youtube|gmail|google docs?"
    r")\b|https?://",
    re.IGNORECASE,
)


def is_garbage_utterance(text: str) -> bool:
    """True when STT is filler/repetition and should not start a billed LLM turn."""
    body = " ".join((text or "").split()).strip()
    if len(body) < 2:
        return True
    if _REPEAT_RE.search(body):
        return True
    words = _WORD_RE.findall(body.lower())
    if len(words) >= 6:
        unique = set(words)
        if len(unique) / len(words) < 0.35:
            return True
        filler_n = sum(1 for w in words if w in _FILLER)
        if filler_n / len(words) > 0.7:
            return True
    return False


def needs_screen_pixels(text: str) -> bool:
    """True when the user is asking about what is visible on the Mac."""
    body = (text or "").strip()
    if not body:
        return False
    return bool(_SCREEN_RE.search(body))


def needs_browser_tabs(text: str) -> bool:
    """True when listing Chrome/Safari tabs is likely useful for this request."""
    body = (text or "").strip()
    if not body:
        return False
    if needs_screen_pixels(body):
        return True
    return bool(_TAB_RE.search(body))
