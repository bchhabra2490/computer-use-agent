"""Make model/STT strings safe to encode as UTF-8."""

from __future__ import annotations


def sanitize_utf8(text: str) -> str:
    """Join UTF-16 surrogate pairs; replace leftovers so ``.encode('utf-8')`` never fails."""
    if not isinstance(text, str) or not text:
        return text if isinstance(text, str) else ""
    try:
        text.encode("utf-8")
        return text
    except UnicodeEncodeError:
        return text.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
