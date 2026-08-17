"""Browser OAuth login for remote MCP servers (Linear, GitHub, …).

``cua mcp login linear`` opens the app in a browser, stores tokens under
``.runtime/mcp-auth/``, and enables the server in ``mcp.json``. The orchestrator
reuses those tokens — it does not open a browser on its own.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
AUTH_DIR = Path(os.environ.get("MCP_AUTH_DIR") or ROOT / ".runtime" / "mcp-auth")
MCP_CONFIG_PATH = Path(os.environ.get("MCP_CONFIG") or ROOT / "mcp.json")
CALLBACK_HOST = "127.0.0.1"
CALLBACK_PORTS = range(8765, 8781)
LOGIN_TIMEOUT = float(os.environ.get("MCP_LOGIN_TIMEOUT", "300"))

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

KNOWN_MCP_APPS: dict[str, dict[str, str]] = {
    "linear": {
        "url": "https://mcp.linear.app/mcp",
        "label": "Linear",
        "login": "oauth",
    },
    "github": {
        "url": "https://api.githubcopilot.com/mcp/",
        "label": "GitHub",
        "login": "github_cli",
    },
    "notion": {
        "url": "https://mcp.notion.com/mcp",
        "label": "Notion",
        "login": "oauth",
    },
}

GH_SCOPES = ("repo", "read:org", "read:user", "user:email")


def sanitize_server_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    if not slug or not _SLUG.match(slug):
        raise ValueError(f"Invalid MCP server name: {name!r}")
    return slug


@dataclass(frozen=True)
class McpApp:
    name: str
    url: str
    label: str


def resolve_app(name: str, url: str | None = None) -> McpApp:
    slug = sanitize_server_name(name)
    known = KNOWN_MCP_APPS.get(slug)
    resolved_url = (url or "").strip() or (known or {}).get("url") or ""
    if not resolved_url:
        raise ValueError(
            f"Unknown app {name!r}. Pass --url, or use one of: "
            + ", ".join(sorted(KNOWN_MCP_APPS))
        )
    label = (known or {}).get("label") or slug
    return McpApp(name=slug, url=resolved_url, label=label)


class FileTokenStorage:
    """JSON token + client-info store (chmod 600)."""

    def __init__(self, name: str, directory: Path | None = None) -> None:
        self.name = sanitize_server_name(name)
        self.path = (directory or AUTH_DIR) / f"{self.name}.json"

    def has_tokens(self) -> bool:
        tokens = self._load().get("tokens") or {}
        return bool(tokens.get("access_token"))

    def kind(self) -> str:
        return str(self._load().get("kind") or "oauth")

    def access_token(self) -> str | None:
        tokens = self._load().get("tokens") or {}
        token = tokens.get("access_token")
        return str(token) if token else None

    def set_bearer_token(self, token: str) -> None:
        data = self._load()
        data["kind"] = "token"
        data["tokens"] = {"access_token": token.strip(), "token_type": "Bearer"}
        self._save(data)

    def clear(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    async def get_tokens(self):
        from mcp.shared.auth import OAuthToken

        raw = self._load().get("tokens")
        if not raw:
            return None
        return OAuthToken.model_validate(raw)

    async def set_tokens(self, tokens) -> None:
        data = self._load()
        data["tokens"] = tokens.model_dump(mode="json")
        self._save(data)

    async def get_client_info(self):
        from mcp.shared.auth import OAuthClientInformationFull

        raw = self._load().get("client_info")
        if not raw:
            return None
        return OAuthClientInformationFull.model_validate(raw)

    async def set_client_info(self, client_info) -> None:
        data = self._load()
        data["client_info"] = client_info.model_dump(mode="json")
        self._save(data)


class CallbackServer:
    """Local HTTP listener for the OAuth redirect."""

    def __init__(self, host: str = CALLBACK_HOST) -> None:
        self.host = host
        self.port = 0
        self._httpd: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._event: asyncio.Event | None = None
        self._code: str | None = None
        self._state: str | None = None
        self._error: str | None = None

    @property
    def redirect_uri(self) -> str:
        return f"http://{self.host}:{self.port}/callback"

    def start(self, loop: asyncio.AbstractEventLoop) -> str:
        self._loop = loop
        self._event = asyncio.Event()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path not in {"/callback", "/", "/oauth/callback"}:
                    self.send_response(204)
                    self.end_headers()
                    return
                qs = parse_qs(parsed.query)
                owner._code = (qs.get("code") or [None])[0]
                owner._state = (qs.get("state") or [None])[0]
                err = (qs.get("error") or [None])[0]
                desc = (qs.get("error_description") or [None])[0]
                if err:
                    owner._error = desc or err
                body = (
                    b"<html><body style='font-family:sans-serif;padding:2rem'>"
                    b"<h2>CUA is connected.</h2>"
                    b"<p>You can close this tab and return to the terminal.</p>"
                    b"</body></html>"
                )
                if owner._error:
                    body = (
                        b"<html><body style='font-family:sans-serif;padding:2rem'>"
                        b"<h2>Login was not completed.</h2>"
                        b"<p>Return to the terminal and try again.</p>"
                        b"</body></html>"
                    )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                if owner._loop is not None and owner._event is not None:
                    owner._loop.call_soon_threadsafe(owner._event.set)

            def log_message(self, *_args: Any) -> None:
                return

        last_error: OSError | None = None
        for port in CALLBACK_PORTS:
            try:
                httpd = HTTPServer((self.host, port), Handler)
                break
            except OSError as e:
                last_error = e
                httpd = None
        if httpd is None:
            raise RuntimeError(f"Could not bind OAuth callback port: {last_error}")
        self._httpd = httpd
        self.port = int(httpd.server_address[1])
        self._thread = threading.Thread(
            target=httpd.serve_forever,
            name="mcp-oauth-callback",
            daemon=True,
        )
        self._thread.start()
        return self.redirect_uri

    async def wait(self) -> tuple[str, str | None]:
        if self._event is None:
            raise RuntimeError("Callback server was not started")
        await asyncio.wait_for(self._event.wait(), timeout=LOGIN_TIMEOUT)
        if self._error:
            raise RuntimeError(f"Login failed: {self._error}")
        if not self._code:
            raise RuntimeError("Login did not return an authorization code")
        return self._code, self._state

    def stop(self) -> None:
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
            except Exception:
                pass
            try:
                self._httpd.server_close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2)


def upsert_oauth_server(
    name: str,
    url: str,
    *,
    path: Path | None = None,
    auth: str = "oauth",
) -> Path:
    """Enable ``auth: oauth`` for this server in mcp.json (create if missing)."""
    cfg = path or MCP_CONFIG_PATH
    data: dict[str, Any] = {}
    if cfg.is_file():
        try:
            loaded = json.loads(cfg.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except json.JSONDecodeError:
            data = {}
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
        data["mcpServers"] = servers
    slug = sanitize_server_name(name)
    existing = servers.get(slug) if isinstance(servers.get(slug), dict) else {}
    existing.pop("disabled", None)
    existing["url"] = url
    existing["auth"] = auth if auth in {"oauth", "token"} else "oauth"
    headers = existing.get("headers")
    if isinstance(headers, dict):
        headers = {
            k: v
            for k, v in headers.items()
            if str(k).lower() != "authorization"
        }
        if headers:
            existing["headers"] = headers
        else:
            existing.pop("headers", None)
    servers[slug] = existing
    cfg.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return cfg


def logged_in_names(*, directory: Path | None = None) -> list[str]:
    root = directory or AUTH_DIR
    if not root.is_dir():
        return []
    names = []
    for path in sorted(root.glob("*.json")):
        storage = FileTokenStorage(path.stem, directory=root)
        if storage.has_tokens():
            names.append(path.stem)
    return names


def build_oauth_provider(
    app: McpApp,
    *,
    storage: FileTokenStorage,
    redirect_uri: str,
    redirect_handler,
    callback_handler,
):
    from mcp.client.auth import OAuthClientProvider
    from mcp.shared.auth import OAuthClientMetadata
    from pydantic import AnyUrl

    metadata = OAuthClientMetadata(
        client_name="CUA",
        redirect_uris=[AnyUrl(redirect_uri)],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
    )
    return OAuthClientProvider(
        server_url=app.url,
        client_metadata=metadata,
        storage=storage,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
        timeout=LOGIN_TIMEOUT,
    )


def unwrap_error(exc: BaseException) -> BaseException:
    current: BaseException = exc
    while isinstance(current, BaseExceptionGroup) and current.exceptions:
        current = current.exceptions[0]
    cause = current.__cause__ or getattr(current, "__context__", None)
    if cause is not None and current.args and "TaskGroup" in str(current):
        return unwrap_error(cause)
    return current


def is_dcr_failure(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return "registration failed" in text or "oauthregistrationerror" in text


import httpx


class BearerTokenAuth(httpx.Auth):
    """httpx Auth that sends a stored access token (GitHub PAT / gh token)."""

    requires_request_body = False
    requires_response_body = False

    def __init__(self, token: str) -> None:
        self._token = token

    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request

    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request

    async def async_auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request


def _gh_bin() -> str | None:
    return shutil.which("gh")


def _gh_token() -> str | None:
    gh = _gh_bin()
    if not gh:
        return None
    result = subprocess.run(
        [gh, "auth", "token"],
        capture_output=True,
        text=True,
        check=False,
    )
    token = (result.stdout or "").strip()
    return token or None


def _gh_login_browser() -> None:
    gh = _gh_bin()
    if not gh:
        raise RuntimeError(
            "GitHub MCP does not support automatic OAuth (no dynamic client "
            "registration).\nInstall GitHub CLI, then retry:\n"
            "  brew install gh\n"
            "  cua mcp login github\n"
            "Or paste a token:\n"
            "  cua mcp login github --token ghp_..."
        )
    print("[mcp] opening GitHub in your browser (gh auth login)…", flush=True)
    cmd = [gh, "auth", "login", "-h", "github.com", "-p", "https", "-w"]
    for scope in GH_SCOPES:
        cmd.extend(["-s", scope])
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise RuntimeError("gh auth login did not complete.")


def login_with_bearer(app: McpApp, *, token: str | None = None) -> str:
    access = (token or "").strip()
    if not access:
        if app.name == "github":
            access = _gh_token() or ""
            if not access:
                _gh_login_browser()
                access = _gh_token() or ""
        if not access:
            raise RuntimeError(
                f"No token for {app.label}. Pass --token, or for GitHub install gh."
            )
    storage = FileTokenStorage(app.name)
    storage.set_bearer_token(access)
    cfg = upsert_oauth_server(app.name, app.url, auth="token")
    return (
        f"Logged in to {app.label}. Enabled in {cfg.name}. "
        "Restart the orchestrator to use it."
    )


def oauth_httpx_auth(spec: Any):
    """httpx Auth for a connected HTTP MCP server, or None."""
    url = getattr(spec, "url", None)
    name = getattr(spec, "name", "")
    headers = getattr(spec, "headers", None) or {}
    if not url:
        return None
    if any(str(k).lower() == "authorization" for k in headers):
        return None
    storage = FileTokenStorage(name)
    if not storage.has_tokens():
        return None
    token = storage.access_token()
    if storage.kind() == "token" and token:
        return BearerTokenAuth(token)

    async def _no_browser(_authorize_url: str) -> None:
        raise RuntimeError(
            f"MCP {name} session expired. Run: cua mcp login {name}"
        )

    async def _no_callback() -> tuple[str, str | None]:
        raise RuntimeError(
            f"MCP {name} session expired. Run: cua mcp login {name}"
        )

    app = McpApp(name=name, url=str(url), label=name)
    return build_oauth_provider(
        app,
        storage=storage,
        redirect_uri="http://127.0.0.1:8765/callback",
        redirect_handler=_no_browser,
        callback_handler=_no_callback,
    )


async def login_oauth(app: McpApp) -> str:
    callback = CallbackServer()
    redirect_uri = callback.start(asyncio.get_running_loop())
    storage = FileTokenStorage(app.name)

    async def redirect_handler(authorize_url: str) -> None:
        print(f"[mcp] log in to {app.label} in your browser…", flush=True)
        print(authorize_url, flush=True)
        opened = webbrowser.open(authorize_url)
        if not opened:
            print("[mcp] could not open a browser; paste the URL above.", flush=True)

    try:
        auth = build_oauth_provider(
            app,
            storage=storage,
            redirect_uri=redirect_uri,
            redirect_handler=redirect_handler,
            callback_handler=callback.wait,
        )
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(app.url, auth=auth) as (read, write, _sid):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                n_tools = len(listed.tools or [])
        cfg = upsert_oauth_server(app.name, app.url, auth="oauth")
        return (
            f"Logged in to {app.label} ({n_tools} tools). "
            f"Enabled in {cfg.name}. Restart the orchestrator to use it."
        )
    finally:
        callback.stop()


async def login_app(
    name: str,
    *,
    url: str | None = None,
    token: str | None = None,
) -> str:
    app = resolve_app(name, url)
    mode = (KNOWN_MCP_APPS.get(app.name) or {}).get("login") or "oauth"
    if token or mode == "github_cli":
        return login_with_bearer(app, token=token)
    try:
        return await login_oauth(app)
    except BaseException as e:
        err = unwrap_error(e)
        if is_dcr_failure(err) and app.name == "github":
            print(
                "[mcp] GitHub does not support automatic OAuth registration; "
                "using GitHub CLI instead…",
                flush=True,
            )
            return login_with_bearer(app, token=token)
        if is_dcr_failure(err):
            raise RuntimeError(
                f"{app.label} does not support automatic OAuth registration. "
                f"Pass a token: cua mcp login {app.name} --token …"
            ) from err
        raise RuntimeError(str(err)) from err


def logout_app(name: str) -> str:
    slug = sanitize_server_name(name)
    FileTokenStorage(slug).clear()
    return f"Logged out of {slug}. Tokens removed."


def format_apps_help() -> str:
    lines = ["Known apps (cua mcp login <name>):"]
    for key, meta in KNOWN_MCP_APPS.items():
        how = "GitHub CLI browser login" if meta.get("login") == "github_cli" else "OAuth in browser"
        lines.append(f"  {key:12} {meta['label']:10} {how}")
    lines.append("Or: cua mcp login my-app --url https://mcp.example.com/mcp")
    lines.append("GitHub: cua mcp login github   (uses `gh auth login`)")
    return "\n".join(lines)


def format_status() -> str:
    names = logged_in_names()
    if not names:
        return "No MCP apps logged in. Try: cua mcp login linear"
    return "Logged in: " + ", ".join(names)


def cmd_mcp_login(
    name: str | None,
    *,
    url: str | None = None,
    token: str | None = None,
) -> int:
    if not name:
        print(format_apps_help())
        return 0
    try:
        message = asyncio.run(login_app(name, url=url, token=token))
    except ValueError as e:
        print(f"[mcp] {e}")
        print(format_apps_help())
        return 2
    except Exception as e:
        err = unwrap_error(e)
        print(f"[mcp] login failed: {err}")
        return 1
    print(f"[mcp] {message}")
    return 0


def cmd_mcp_logout(name: str) -> int:
    try:
        print(f"[mcp] {logout_app(name)}")
    except ValueError as e:
        print(f"[mcp] {e}")
        return 2
    return 0


def cmd_mcp_status() -> int:
    print(format_status())
    return 0
