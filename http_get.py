"""Public HTTPS fetch for orchestrator / sidekick (no browser, no CU)."""

from __future__ import annotations

import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MAX_CHARS = 8_000
TIMEOUT_SEC = 12.0
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = " ".join((data or "").split())
        if text:
            self._chunks.append(text)

    def text(self) -> str:
        return " ".join(self._chunks)


def _host_allowed(host: str) -> bool:
    h = (host or "").strip().lower().rstrip(".")
    if not h or h == "localhost" or h.endswith(".local"):
        return False
    try:
        ip = ipaddress.ip_address(h)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(h, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return True
    for info in infos:
        addr = str(info[4][0])
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    return True


def fetch_https(
    url: str,
    *,
    max_chars: int = MAX_CHARS,
    strip_html: bool = True,
    user_agent: str | None = None,
) -> str:
    raw = (url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.netloc:
        return "Error: only https URLs are allowed."
    host = parsed.hostname or ""
    if not _host_allowed(host):
        return "Error: that host is not allowed."
    ua = (user_agent or _DEFAULT_USER_AGENT).strip() or _DEFAULT_USER_AGENT
    req = Request(
        raw,
        headers={
            "User-Agent": ua,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urlopen(req, timeout=TIMEOUT_SEC) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            body = resp.read(max_chars * 4)
    except Exception as e:
        return f"Error: fetch failed ({e})"
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:
        text = body.decode("latin-1", errors="replace")
    is_html = (
        "html" in ctype
        or text.lstrip()[:15].lower().startswith("<!doctype html")
        or text.lstrip()[:6].lower().startswith("<html")
    )
    if strip_html and is_html:
        parser = _TextExtractor()
        try:
            parser.feed(text)
            parser.close()
            text = parser.text()
        except Exception:
            text = re.sub(r"<[^>]+>", " ", text)
            text = " ".join(text.split())
    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "\n… [truncated]"
    return text or "(empty response)"


def run_http_get(args: dict) -> str:
    url = str(args.get("url") or "").strip()
    if not url:
        return "Error: url is required."
    return fetch_https(url)
