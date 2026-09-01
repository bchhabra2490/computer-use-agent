"""Safe, structured webpage retrieval for browser and research lanes."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_BYTES = 2_000_000
DEFAULT_MAX_CHARS = 80_000
DEFAULT_LIGHTPANDA_WAIT_MS = 3_000
DEFAULT_CHROMIUM_WAIT_MS = 5_000
ALLOWED_CONTENT_TYPES = ("text/html", "text/plain", "application/json", "application/xhtml+xml")


class BrowserDataError(RuntimeError):
    pass


def _validate_public_url(url: str, *, resolve_dns: bool = True) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise BrowserDataError("Only http and https URLs are supported.")
    if not parts.hostname or parts.username or parts.password:
        raise BrowserDataError("URL must have a hostname and cannot contain credentials.")
    host = parts.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise BrowserDataError("Local and private network addresses are blocked.")
    addresses: set[str] = set()
    try:
        addresses.add(str(ipaddress.ip_address(host)))
    except ValueError:
        if resolve_dns:
            try:
                addresses.update(item[4][0] for item in socket.getaddrinfo(host, parts.port or 443))
            except socket.gaierror as exc:
                raise BrowserDataError(f"Could not resolve hostname: {host}") from exc
    for value in addresses:
        address = ipaddress.ip_address(value)
        if not address.is_global:
            raise BrowserDataError("Local, private, reserved, and link-local addresses are blocked.")


def _validate_http_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise BrowserDataError("Only absolute http and https URLs are supported.")
    if parts.username or parts.password:
        raise BrowserDataError("URL cannot contain credentials.")


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        absolute = urljoin(req.full_url, newurl)
        _validate_public_url(absolute)
        return super().redirect_request(req, fp, code, msg, headers, absolute)


@dataclass
class PageLink:
    text: str
    url: str


@dataclass
class PageResult:
    requested_url: str
    final_url: str
    title: str = ""
    status: int = 0
    content_type: str = ""
    markdown: str = ""
    links: list[PageLink] = field(default_factory=list)
    backend: str = "http"
    elapsed_ms: int = 0
    truncated: bool = False
    fallback_required: str | None = None
    warnings: list[str] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)


class _MarkdownParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "template", "svg"}
    BLOCK = {"p", "div", "section", "article", "main", "header", "footer", "table", "tr", "blockquote"}

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self._in_title = False
        self._skip_depth = 0
        self._parts: list[str] = []
        self._link_href: str | None = None
        self._link_text: list[str] = []
        self.links: list[PageLink] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.SKIP:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        values = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._parts.append("\n" + "#" * int(tag[1]) + " ")
        elif tag == "li":
            self._parts.append("\n- ")
        elif tag == "br":
            self._parts.append("\n")
        elif tag in self.BLOCK:
            self._parts.append("\n")
        elif tag == "a" and values.get("href"):
            self._link_href = urljoin(self.base_url, values["href"] or "")
            self._link_text = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
        elif tag == "a" and self._link_href:
            label = " ".join("".join(self._link_text).split())
            if label:
                self.links.append(PageLink(label, self._link_href))
            self._link_href = None
            self._link_text = []
        elif tag in self.BLOCK or tag.startswith("h") or tag == "li":
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data
            return
        text = " ".join(data.split())
        if text:
            self._parts.append(text + " ")
            if self._link_href:
                self._link_text.append(text)

    def markdown(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self._parts).splitlines()]
        return "\n".join(line for line in lines if line).strip()


def _decode(data: bytes, content_type: str) -> str:
    charset = "utf-8"
    for item in content_type.split(";")[1:]:
        if item.strip().lower().startswith("charset="):
            charset = item.split("=", 1)[1].strip().strip('"')
    try:
        return data.decode(charset, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


def fetch_page(
    url: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    allow_private: bool = False,
) -> PageResult:
    """Fetch a static public page and return normalized content and evidence."""
    if allow_private:
        _validate_http_url(url)
    else:
        _validate_public_url(url)
    started = time.monotonic()
    opener = build_opener(HTTPRedirectHandler() if allow_private else _SafeRedirectHandler())
    request = Request(url, headers={"User-Agent": "ComputerUseAgent/1.0 (+browser-data)"})
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = response.geturl()
            if not allow_private:
                _validate_public_url(final_url)
            status = int(getattr(response, "status", 200))
            content_type = response.headers.get("Content-Type", "").lower()
            media_type = content_type.split(";", 1)[0].strip()
            if media_type not in ALLOWED_CONTENT_TYPES:
                raise BrowserDataError(f"Unsupported content type: {media_type or 'unknown'}")
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > max_bytes:
                raise BrowserDataError(f"Response exceeds the {max_bytes}-byte limit.")
            data = response.read(max_bytes + 1)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise BrowserDataError(f"Page fetch failed: {exc}") from exc
    truncated_bytes = len(data) > max_bytes
    data = data[:max_bytes]
    text = _decode(data, content_type)
    title = ""
    links: list[PageLink] = []
    if media_type in {"text/html", "application/xhtml+xml"}:
        parser = _MarkdownParser(final_url)
        parser.feed(text)
        markdown = parser.markdown()
        title = " ".join(parser.title.split())
        links = parser.links[:500]
    elif media_type == "application/json":
        try:
            markdown = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            markdown = text.strip()
    else:
        markdown = text.strip()
    truncated_chars = len(markdown) > max_chars
    markdown = markdown[:max_chars]
    fallback = None
    warnings: list[str] = []
    lowered = data.lower()
    app_shell_markers = (
        b'id="root"',
        b"id='root'",
        b'id="app"',
        b"id='app'",
        b'id="__next"',
        b"data-reactroot",
        b"ng-version=",
    )
    likely_js_shell = b"<script" in lowered and (
        len(markdown) < 200
        or (len(markdown) < 2_000 and any(marker in lowered for marker in app_shell_markers))
    )
    if media_type in {"text/html", "application/xhtml+xml"} and likely_js_shell:
        fallback = "lightpanda"
        warnings.append("Very little static text was found; this page likely requires JavaScript rendering.")
    return PageResult(
        requested_url=url,
        final_url=final_url,
        title=title,
        status=status,
        content_type=media_type,
        markdown=markdown,
        links=links,
        elapsed_ms=round((time.monotonic() - started) * 1000),
        truncated=truncated_bytes or truncated_chars,
        fallback_required=fallback,
        warnings=warnings,
        attempts=[{"backend": "http", "elapsed_ms": round((time.monotonic() - started) * 1000), "ok": True}],
    )


def _lightpanda_binary() -> str:
    configured = os.environ.get("LIGHTPANDA_BIN", "").strip()
    if configured:
        path = os.path.abspath(os.path.expanduser(configured))
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
        raise BrowserDataError(f"Configured Lightpanda binary is not executable: {path}")
    path = shutil.which("lightpanda")
    if not path:
        raise BrowserDataError(
            "Lightpanda is not installed. Install it with "
            "'brew install lightpanda-io/browser/lightpanda' or set LIGHTPANDA_BIN."
        )
    return path


def _lightpanda_json(stdout: str) -> tuple[str, str, int]:
    """Accept current and older JSON field names without coupling to one nightly."""
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise BrowserDataError("Lightpanda returned invalid JSON output.") from exc
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        payload = payload["results"][0] if payload["results"] else {}
    if not isinstance(payload, dict):
        raise BrowserDataError("Lightpanda returned an unexpected result shape.")
    error = payload.get("error")
    if not error and payload.get("success") is False:
        error = payload.get("message")
    if error:
        raise BrowserDataError(f"Lightpanda fetch failed: {error}")
    markdown = ""
    # Current nightlies use ``dump`` for the selected format name and
    # ``content`` for its output. Older builds used ``markdown`` or ``body``.
    for key in ("content", "markdown", "body"):
        if isinstance(payload.get(key), str):
            markdown = payload[key]
            break
    if not markdown and isinstance(payload.get("dump"), str) and payload.get("dump") != "markdown":
        markdown = payload["dump"]
    if not markdown:
        raise BrowserDataError("Lightpanda completed without rendered Markdown.")
    final_url = str(payload.get("url") or payload.get("final_url") or payload.get("finalUrl") or "")
    status = int(
        payload.get("http_status")
        or payload.get("status")
        or payload.get("status_code")
        or payload.get("statusCode")
        or 200
    )
    return markdown.strip(), final_url, status


def _links_from_markdown(markdown: str, base_url: str) -> list[PageLink]:
    links: list[PageLink] = []
    seen: set[tuple[str, str]] = set()
    for match in re.finditer(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)(?:\s+[^)]*)?\)", markdown):
        text = " ".join(match.group(1).split())
        url = urljoin(base_url, match.group(2).strip("<>"))
        key = (text, url)
        if text and key not in seen:
            seen.add(key)
            links.append(PageLink(text, url))
        if len(links) >= 500:
            break
    return links


def fetch_lightpanda(
    url: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    timeout: float = DEFAULT_TIMEOUT,
    wait_ms: int = DEFAULT_LIGHTPANDA_WAIT_MS,
) -> PageResult:
    """Render one public page in an isolated Lightpanda process."""
    _validate_public_url(url)
    binary = _lightpanda_binary()
    timeout_ms = max(1_000, int(timeout * 1_000))
    wait_ms = max(0, min(int(wait_ms), timeout_ms - 250))
    command = [
        binary,
        "fetch",
        "--obey-robots",
        "--dump",
        "markdown",
        "--json",
        "--wait-ms",
        str(wait_ms),
        "--terminate-ms",
        str(timeout_ms),
        url,
    ]
    env = os.environ.copy()
    env.setdefault("LIGHTPANDA_DISABLE_TELEMETRY", "true")
    env.setdefault("LIGHTPANDA_DISABLE_CORE_DUMP", "1")
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout + 2,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise BrowserDataError(f"Lightpanda exceeded the {timeout:g}-second deadline.") from exc
    elapsed_ms = round((time.monotonic() - started) * 1000)
    if completed.returncode != 0:
        detail = " ".join((completed.stderr or completed.stdout or "unknown error").split())[:500]
        raise BrowserDataError(f"Lightpanda exited with code {completed.returncode}: {detail}")
    markdown, final_url, status = _lightpanda_json(completed.stdout)
    final_url = final_url or url
    _validate_public_url(final_url)
    truncated = len(markdown) > max_chars
    markdown = markdown[:max_chars]
    title_match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    return PageResult(
        requested_url=url,
        final_url=final_url,
        title=title_match.group(1).strip() if title_match else "",
        status=status,
        content_type="text/markdown",
        markdown=markdown,
        links=_links_from_markdown(markdown, final_url),
        backend="lightpanda",
        elapsed_ms=elapsed_ms,
        truncated=truncated,
        attempts=[{"backend": "lightpanda", "elapsed_ms": elapsed_ms, "ok": True}],
    )


def _chromium_binary() -> str:
    configured = os.environ.get("CHROMIUM_BIN", "").strip()
    candidates = [
        configured,
        shutil.which("chromium") or "",
        shutil.which("chromium-browser") or "",
        shutil.which("google-chrome") or "",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = os.path.abspath(os.path.expanduser(candidate))
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    if configured:
        raise BrowserDataError(f"Configured Chromium binary is not executable: {configured}")
    raise BrowserDataError("No Chromium or Google Chrome executable was found. Set CHROMIUM_BIN.")


def fetch_chromium(
    url: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    timeout: float = DEFAULT_TIMEOUT,
    wait_ms: int = DEFAULT_CHROMIUM_WAIT_MS,
) -> PageResult:
    """Render a public page in headless Chromium with a fresh temporary profile."""
    _validate_public_url(url)
    binary = _chromium_binary()
    timeout_ms = max(1_000, int(timeout * 1_000))
    wait_ms = max(0, min(int(wait_ms), timeout_ms - 250))
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="cua-chromium-") as profile_dir:
        command = [
            binary,
            "--headless",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-sync",
            "--no-first-run",
            "--no-default-browser-check",
            "--metrics-recording-only",
            f"--user-data-dir={profile_dir}",
            f"--timeout={wait_ms}",
            "--dump-dom",
            url,
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout + 2,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise BrowserDataError(f"Chromium exceeded the {timeout:g}-second deadline.") from exc
    elapsed_ms = round((time.monotonic() - started) * 1000)
    if completed.returncode != 0:
        detail = " ".join((completed.stderr or completed.stdout or "unknown error").split())[:500]
        raise BrowserDataError(f"Chromium exited with code {completed.returncode}: {detail}")
    html = completed.stdout.strip()
    if not html or "<html" not in html.lower():
        raise BrowserDataError("Chromium completed without a rendered HTML document.")
    parser = _MarkdownParser(url)
    parser.feed(html)
    markdown = parser.markdown()
    if not markdown:
        raise BrowserDataError("Chromium rendered the page but extracted no readable content.")
    truncated = len(markdown) > max_chars
    markdown = markdown[:max_chars]
    return PageResult(
        requested_url=url,
        final_url=url,
        title=" ".join(parser.title.split()),
        status=0,
        content_type="text/html",
        markdown=markdown,
        links=parser.links[:500],
        backend="chromium",
        elapsed_ms=elapsed_ms,
        truncated=truncated,
        warnings=["Headless CLI extraction does not expose the final HTTP status or redirect URL."],
        attempts=[{"backend": "chromium", "elapsed_ms": elapsed_ms, "ok": True}],
    )


def _apply_operation(result: PageResult, operation: str, query: str, max_chars: int) -> dict[str, Any]:
    payload = asdict(result)
    if operation == "links":
        payload.pop("markdown", None)
    elif operation == "extract" and query:
        blocks = result.markdown.splitlines()
        matches = [block for block in blocks if query in block.lower()]
        payload["markdown"] = "\n".join(matches)[:max_chars]
        payload["matched_blocks"] = len(matches)
    return payload


def run_browser_data_tool(args: dict[str, Any]) -> str:
    url = str(args.get("url") or "").strip()
    operation = str(args.get("operation") or "fetch")
    query = str(args.get("query") or "").strip().lower()
    max_chars = max(1_000, min(int(args.get("max_chars") or DEFAULT_MAX_CHARS), DEFAULT_MAX_CHARS))
    backend = str(args.get("backend") or "auto")
    try:
        timeout = float(os.environ.get("BROWSER_DATA_TIMEOUT", DEFAULT_TIMEOUT))
        chromium_wait_ms = int(os.environ.get("CHROMIUM_WAIT_MS", DEFAULT_CHROMIUM_WAIT_MS))
        if backend == "chromium":
            result = fetch_chromium(url, max_chars=max_chars, timeout=timeout, wait_ms=chromium_wait_ms)
            return json.dumps(_apply_operation(result, operation, query, max_chars), ensure_ascii=False)
        if backend == "lightpanda":
            result = fetch_lightpanda(
                url,
                max_chars=max_chars,
                timeout=timeout,
                wait_ms=int(os.environ.get("LIGHTPANDA_WAIT_MS", DEFAULT_LIGHTPANDA_WAIT_MS)),
            )
            return json.dumps(_apply_operation(result, operation, query, max_chars), ensure_ascii=False)
        result = fetch_page(url, max_chars=max_chars, timeout=timeout, max_bytes=int(os.environ.get("BROWSER_DATA_MAX_BYTES", DEFAULT_MAX_BYTES)))
        if backend == "auto" and result.fallback_required == "lightpanda":
            http_attempts = list(result.attempts)
            try:
                rendered = fetch_lightpanda(
                    url,
                    max_chars=max_chars,
                    timeout=timeout,
                    wait_ms=int(os.environ.get("LIGHTPANDA_WAIT_MS", DEFAULT_LIGHTPANDA_WAIT_MS)),
                )
                rendered.attempts = http_attempts + rendered.attempts
                if rendered.fallback_required != "chromium":
                    return json.dumps(_apply_operation(rendered, operation, query, max_chars), ensure_ascii=False)
                result = rendered
            except BrowserDataError as exc:
                result.fallback_required = "chromium"
                result.warnings.append(str(exc))
                result.attempts.append({"backend": "lightpanda", "ok": False, "error": str(exc)})
            prior_attempts = list(result.attempts)
            prior_warnings = list(result.warnings)
            try:
                rendered = fetch_chromium(
                    url,
                    max_chars=max_chars,
                    timeout=timeout,
                    wait_ms=chromium_wait_ms,
                )
                rendered.attempts = prior_attempts + rendered.attempts
                rendered.warnings = prior_warnings + rendered.warnings
                return json.dumps(_apply_operation(rendered, operation, query, max_chars), ensure_ascii=False)
            except BrowserDataError as exc:
                result.fallback_required = "desktop"
                result.warnings.append(str(exc))
                result.attempts.append({"backend": "chromium", "ok": False, "error": str(exc)})
        return json.dumps(_apply_operation(result, operation, query, max_chars), ensure_ascii=False)
    except (BrowserDataError, ValueError) as exc:
        fallback = "chromium" if backend == "lightpanda" else "desktop" if backend == "chromium" else None
        return json.dumps({"error": str(exc), "backend": backend, "requested_url": url, "fallback_required": fallback})
