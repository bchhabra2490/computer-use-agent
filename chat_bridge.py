"""Localhost HTTP API for the Electron chat desktop app.

Bound to 127.0.0.1 only. Auth: Bearer token in ``.runtime/chat.token``.
The Electron UI talks here for SQLite history and orchestrator IPC
(``enqueue_utterance`` / ``consume_chat_inbox``).

Started by the tray when chat is enabled, or: ``python chat_bridge.py``.
"""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from envfile import load_dotenv

load_dotenv()

from app_status import (  # noqa: E402
    RUNTIME_DIR,
    consume_chat_inbox,
    enqueue_utterance,
    pid_alive,
    read_status,
    set_chat_bridge_pid,
)
from chat_store import (  # noqa: E402
    PREF_SCREENSHOT_ON,
    get_store,
    title_from_text,
)

HOST = "127.0.0.1"
PORT = int(os.environ.get("CHAT_BRIDGE_PORT", "8743"))
TOKEN_PATH = RUNTIME_DIR / "chat.token"
TOKEN_LEN = 24
PID_KEY = "chat_bridge_pid"
_OFF = {"0", "false", "no", "off"}
ROOT = Path(__file__).resolve().parent
_SECRET_KEY_RE = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|authorization|credential)",
    re.I,
)


def _mcp_config_path() -> Path:
    return Path(os.environ.get("MCP_CONFIG") or ROOT / "mcp.json")


def _read_mcp_raw() -> dict[str, Any]:
    path = _mcp_config_path()
    if not path.is_file():
        return {"mcpServers": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"mcpServers": {}}
    if not isinstance(data, dict):
        return {"mcpServers": {}}
    if "mcpServers" not in data or not isinstance(data.get("mcpServers"), dict):
        data["mcpServers"] = {}
    return data


def _write_mcp_raw(data: dict[str, Any]) -> Path:
    path = _mcp_config_path()
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def _redact_map(data: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(data, dict):
        return out
    for key, val in data.items():
        k = str(key)
        if _SECRET_KEY_RE.search(k):
            out[k] = "***"
        else:
            s = str(val)
            out[k] = "***" if len(s) > 24 and s.lower().startswith("bearer ") else s
    return out


def list_mcp_connections() -> list[dict[str, Any]]:
    """Connections as stored in mcp.json (secrets redacted for the UI)."""
    raw = _read_mcp_raw().get("mcpServers") or {}
    rows: list[dict[str, Any]] = []
    if not isinstance(raw, dict):
        return rows
    for name, spec in raw.items():
        if not isinstance(spec, dict):
            continue
        command = spec.get("command")
        url = spec.get("url") or spec.get("serverUrl")
        transport = str(spec.get("type") or spec.get("transport") or "").strip().lower()
        if not transport:
            transport = "stdio" if command else "http"
        if transport in {"streamable-http", "streamable_http"}:
            transport = "http"
        disabled = spec.get("disabled") is True or spec.get("enabled") is False
        rows.append(
            {
                "name": str(name),
                "transport": transport,
                "url": str(url) if url else None,
                "command": str(command) if command else None,
                "args": [str(a) for a in (spec.get("args") or [])]
                if isinstance(spec.get("args"), list)
                else [],
                "auth": str(spec.get("auth") or "").strip().lower() or None,
                "headers": _redact_map(spec.get("headers")),
                "env": _redact_map(spec.get("env")),
                "enabled": not disabled,
            }
        )
    rows.sort(key=lambda r: r["name"])
    return rows


def upsert_mcp_connection(body: dict[str, Any]) -> dict[str, Any]:
    """Add or replace a server entry in mcp.json."""
    from mcp_auth import sanitize_server_name

    name = sanitize_server_name(str(body.get("name") or ""))
    kind = str(body.get("kind") or body.get("transport") or "").strip().lower()
    url = str(body.get("url") or "").strip()
    command = str(body.get("command") or "").strip()
    auth = str(body.get("auth") or "").strip().lower()
    if auth in {"oauth2", "browser", "login"}:
        auth = "oauth"
    elif auth in {"bearer", "pat"}:
        auth = "token"
    elif auth in {"", "none", "off"}:
        auth = ""

    if kind in {"stdio", "command", "local"}:
        kind = "stdio"
    elif kind in {"http", "url", "sse", "remote"}:
        kind = "http" if kind != "sse" else "sse"
    elif url:
        kind = "http"
    elif command:
        kind = "stdio"
    else:
        raise ValueError("Provide a URL (remote) or command (local stdio)")

    entry: dict[str, Any] = {}
    if kind == "stdio":
        if not command:
            raise ValueError("command is required for local MCP servers")
        entry["command"] = command
        args_raw = body.get("args")
        if isinstance(args_raw, list):
            entry["args"] = [str(a) for a in args_raw if str(a).strip()]
        elif isinstance(args_raw, str) and args_raw.strip():
            # Prefer newline-separated; fall back to shlex-like split on spaces.
            lines = [ln.strip() for ln in args_raw.splitlines() if ln.strip()]
            entry["args"] = lines if len(lines) > 1 else args_raw.strip().split()
        env = body.get("env")
        if isinstance(env, dict) and env:
            entry["env"] = {str(k): str(v) for k, v in env.items()}
        elif isinstance(env, str) and env.strip():
            parsed = json.loads(env)
            if not isinstance(parsed, dict):
                raise ValueError("env must be a JSON object")
            entry["env"] = {str(k): str(v) for k, v in parsed.items()}
    else:
        if not url:
            raise ValueError("url is required for remote MCP servers")
        entry["url"] = url
        if kind == "sse":
            entry["transport"] = "sse"
        if auth:
            entry["auth"] = auth
        headers: dict[str, str] = {}
        raw_headers = body.get("headers")
        if isinstance(raw_headers, dict):
            headers.update({str(k): str(v) for k, v in raw_headers.items()})
        elif isinstance(raw_headers, str) and raw_headers.strip():
            parsed = json.loads(raw_headers)
            if not isinstance(parsed, dict):
                raise ValueError("headers must be a JSON object")
            headers.update({str(k): str(v) for k, v in parsed.items()})
        token = str(body.get("token") or body.get("bearer") or "").strip()
        if token:
            if not token.lower().startswith("bearer "):
                token = f"Bearer {token}"
            headers["Authorization"] = token
            if not auth:
                entry["auth"] = "token"
        if headers:
            entry["headers"] = headers

    data = _read_mcp_raw()
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        servers = {}
        data["mcpServers"] = servers
    existing = servers.get(name) if isinstance(servers.get(name), dict) else {}
    # Preserve unknown keys; replace known connection fields.
    merged = dict(existing)
    for drop in ("command", "args", "env", "url", "serverUrl", "headers", "auth", "transport", "type"):
        if drop not in entry:
            merged.pop(drop, None)
    merged.update(entry)
    merged.pop("disabled", None)
    servers[name] = merged
    path = _write_mcp_raw(data)
    return {"name": name, "path": str(path), "server": merged}


def delete_mcp_connection(name: str) -> None:
    from mcp_auth import sanitize_server_name

    slug = sanitize_server_name(name)
    data = _read_mcp_raw()
    servers = data.get("mcpServers")
    if not isinstance(servers, dict) or slug not in servers:
        raise KeyError(f"unknown MCP server {slug!r}")
    del servers[slug]
    _write_mcp_raw(data)


def chat_bridge_enabled() -> bool:
    """Bridge runs when chat is on, or CHAT_BRIDGE=1 forces it."""
    if os.environ.get("CHAT_BRIDGE", "").strip().lower() not in {"", *_OFF}:
        return True
    return bool(read_status().get("chat_overlay_enabled"))


def _new_token() -> str:
    return secrets.token_urlsafe(TOKEN_LEN)[:TOKEN_LEN]


def load_or_create_token() -> str:
    env = (os.environ.get("CHAT_BRIDGE_TOKEN") or "").strip()
    if env:
        return env
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if TOKEN_PATH.is_file():
        raw = TOKEN_PATH.read_text(encoding="utf-8").strip()
        if len(raw) >= 16:
            return raw
    token = _new_token()
    TOKEN_PATH.write_text(token + "\n", encoding="utf-8")
    try:
        TOKEN_PATH.chmod(0o600)
    except OSError:
        pass
    return token


def command_for_orchestrator(text: str, *, look_at_screen: bool) -> str:
    body = (text or "").strip()
    if look_at_screen:
        if body:
            return f"Look at the current screen. {body}"
        return "Look at the current screen and tell me what you see."
    return body


def _capture_desktop_png() -> bytes:
    from actions import DesktopController
    from log_overlay import pause_overlay_for_capture

    with pause_overlay_for_capture():
        return DesktopController().capture_screenshot()


def _json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0 or length > 8_000_000:
        return {}
    raw = handler.rfile.read(length)
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _chat_row(c) -> dict[str, Any]:
    return {
        "id": c.id,
        "title": c.title,
        "model_id": c.model_id,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


def _msg_row(m, store) -> dict[str, Any]:
    shot_b64 = None
    if m.screenshot_relpath:
        png = store.read_screenshot(m.screenshot_relpath)
        if png:
            shot_b64 = base64.b64encode(png).decode("ascii")
    return {
        "id": m.id,
        "chat_id": m.chat_id,
        "role": m.role,
        "content": m.content,
        "screenshot_relpath": m.screenshot_relpath,
        "screenshot_b64": shot_b64,
        "created_at": m.created_at,
        "seq": m.seq,
    }


class ChatBridgeHandler(BaseHTTPRequestHandler):
    token: str = ""

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        print(f"[chat-bridge] " + fmt % args, flush=True)

    def _auth_ok(self) -> bool:
        auth = self.headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            got = auth[7:].strip()
            return bool(got) and secrets.compare_digest(got, self.token)
        qs = parse_qs(urlparse(self.path).query)
        got = (qs.get("token") or [""])[0]
        return bool(got) and secrets.compare_digest(got, self.token)

    def _send(self, code: int, payload: Any, *, content_type: str = "application/json") -> None:
        body = (
            payload
            if isinstance(payload, (bytes, bytearray))
            else json.dumps(payload).encode("utf-8")
        )
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, b"")

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/v1/health":
            self._send(200, {"ok": True, "service": "cua-chat-bridge"})
            return
        if not self._auth_ok():
            self._send(401, {"ok": False, "error": "unauthorized"})
            return
        store = get_store()
        if path == "/v1/status":
            snap = read_status()
            self._send(
                200,
                {
                    "ok": True,
                    "orchestrator_alive": pid_alive(snap.get("orchestrator_pid")),
                    "chat_enabled": bool(snap.get("chat_overlay_enabled")),
                    "overlay_hidden": bool(snap.get("overlay_hidden")),
                    "screenshot_on": store.get_pref(PREF_SCREENSHOT_ON, "0") == "1",
                    "face_preset": snap.get("face_preset"),
                    "inbox": consume_chat_inbox(),
                },
            )
            return
        if path == "/v1/chats":
            self._send(200, {"ok": True, "chats": [_chat_row(c) for c in store.list_chats()]})
            return
        if path == "/v1/mcp":
            self._send(
                200,
                {
                    "ok": True,
                    "path": str(_mcp_config_path()),
                    "connections": list_mcp_connections(),
                },
            )
            return
        if path == "/v1/avatars":
            try:
                from AppKit import NSApplication  # type: ignore

                NSApplication.sharedApplication()
                from face_overlay import chat_avatar_pngs

                avatars = chat_avatar_pngs(size=128)
                self._send(
                    200,
                    {
                        "ok": True,
                        "assistant_id": avatars["assistant_id"],
                        "user_id": avatars["user_id"],
                        "assistant_b64": base64.b64encode(avatars["assistant_png"]).decode(
                            "ascii"
                        ),
                        "user_b64": base64.b64encode(avatars["user_png"]).decode("ascii"),
                    },
                )
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
            return
        if path.startswith("/v1/chats/") and path.endswith("/messages"):
            chat_id = path[len("/v1/chats/") : -len("/messages")]
            msgs = store.list_messages(chat_id)
            self._send(200, {"ok": True, "messages": [_msg_row(m, store) for m in msgs]})
            return
        if path.startswith("/v1/screenshots/"):
            rel = path[len("/v1/screenshots/") :]
            png = store.read_screenshot(rel)
            if not png:
                self._send(404, {"ok": False, "error": "not found"})
                return
            self._send(200, png, content_type="image/png")
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if not self._auth_ok():
            self._send(401, {"ok": False, "error": "unauthorized"})
            return
        body = _json_body(self)
        store = get_store()
        if path == "/v1/chats":
            chat = store.create_chat(
                title=str(body.get("title") or "New chat"),
                model_id=str(body.get("model_id") or "orchestrator"),
            )
            self._send(200, {"ok": True, "chat": _chat_row(chat)})
            return
        if path == "/v1/prefs/screenshot":
            on = bool(body.get("on"))
            store.set_pref(PREF_SCREENSHOT_ON, "1" if on else "0")
            self._send(200, {"ok": True, "screenshot_on": on})
            return
        if path == "/v1/mcp":
            try:
                result = upsert_mcp_connection(body)
            except ValueError as e:
                self._send(400, {"ok": False, "error": str(e)})
                return
            except json.JSONDecodeError as e:
                self._send(400, {"ok": False, "error": f"invalid JSON: {e}"})
                return
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
                return
            self._send(
                200,
                {
                    "ok": True,
                    "connection": next(
                        (c for c in list_mcp_connections() if c["name"] == result["name"]),
                        {"name": result["name"]},
                    ),
                    "note": "Restart the orchestrator to load new MCP servers.",
                },
            )
            return
        if path == "/v1/send":
            chat_id = str(body.get("chat_id") or "").strip()
            text = str(body.get("text") or "")
            look = bool(body.get("look_at_screen"))
            if not chat_id:
                self._send(400, {"ok": False, "error": "chat_id required"})
                return
            if not text.strip() and not look:
                self._send(400, {"ok": False, "error": "text or look_at_screen required"})
                return
            relpath = None
            if look:
                try:
                    png = _capture_desktop_png()
                    relpath = store.save_screenshot(chat_id, png)
                except Exception as e:
                    self._send(500, {"ok": False, "error": f"screenshot failed: {e}"})
                    return
            user_text = text.strip() or "(screenshot)"
            store.add_message(chat_id, "user", user_text, screenshot_relpath=relpath)
            chat = store.get_chat(chat_id)
            if chat and chat.title == "New chat":
                store.touch_chat(chat_id, title=title_from_text(user_text), model_id="orchestrator")
            else:
                store.touch_chat(chat_id, model_id="orchestrator")
            cmd = command_for_orchestrator(text, look_at_screen=look)
            enqueue_utterance(cmd, source="chat")
            orch_ok = pid_alive(read_status().get("orchestrator_pid"))
            self._send(
                200,
                {
                    "ok": True,
                    "orchestrator_alive": orch_ok,
                    "warning": None
                    if orch_ok
                    else "Orchestrator is not running. Start: python orchestrator.py --auto",
                },
            )
            return
        if path == "/v1/assistant":
            # Optional: UI can push a line; normally inbox poll handles this.
            chat_id = str(body.get("chat_id") or "").strip()
            text = str(body.get("text") or "").strip()
            if not chat_id or not text:
                self._send(400, {"ok": False, "error": "chat_id and text required"})
                return
            store.add_message(chat_id, "assistant", text)
            self._send(200, {"ok": True})
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_DELETE(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if not self._auth_ok():
            self._send(401, {"ok": False, "error": "unauthorized"})
            return
        if path.startswith("/v1/chats/"):
            chat_id = path[len("/v1/chats/") :]
            get_store().delete_chat(chat_id)
            self._send(200, {"ok": True})
            return
        if path.startswith("/v1/mcp/"):
            name = path[len("/v1/mcp/") :]
            try:
                delete_mcp_connection(name)
            except KeyError as e:
                self._send(404, {"ok": False, "error": str(e)})
                return
            except ValueError as e:
                self._send(400, {"ok": False, "error": str(e)})
                return
            self._send(200, {"ok": True})
            return
        self._send(404, {"ok": False, "error": "not found"})


def serve_forever(*, host: str = HOST, port: int = PORT) -> None:
    token = load_or_create_token()
    ChatBridgeHandler.token = token
    server = ThreadingHTTPServer((host, port), ChatBridgeHandler)
    print(f"[chat-bridge] http://{host}:{port}", flush=True)
    print(f"[chat-bridge] token at {TOKEN_PATH}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[chat-bridge] stopped.", flush=True)


def ensure_chat_bridge() -> subprocess.Popen | None:
    """Start the bridge subprocess if not already running."""
    data = read_status()
    pid = data.get(PID_KEY)
    if pid_alive(pid):
        return None
    cmd = [sys.executable, str(Path(__file__).resolve())]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(Path(__file__).resolve().parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        print(f"[chat-bridge] failed to start: {e}", file=sys.stderr)
        return None
    set_chat_bridge_pid(proc.pid)
    for _ in range(40):
        try:
            import urllib.request

            urllib.request.urlopen(f"http://{HOST}:{PORT}/v1/health", timeout=0.2)
            break
        except Exception:
            time.sleep(0.05)
    print(f"[chat-bridge] started (pid={proc.pid}) port={PORT}", flush=True)
    return proc


def stop_chat_bridge(*, wait: float = 1.5) -> None:
    data = read_status()
    pid = data.get(PID_KEY)
    if not pid_alive(pid):
        set_chat_bridge_pid(None)
        return
    try:
        os.kill(int(pid), 15)
    except Exception:
        pass
    deadline = time.time() + wait
    while time.time() < deadline and pid_alive(pid):
        time.sleep(0.05)
    if pid_alive(pid):
        try:
            os.kill(int(pid), 9)
        except Exception:
            pass
    set_chat_bridge_pid(None)


def main(argv: list[str] | None = None) -> int:
    serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
