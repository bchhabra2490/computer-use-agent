"""Origin-scoped WebMCP discovery and execution through isolated Chromium."""

from __future__ import annotations

import json
import os
import signal
import shutil
import subprocess
import threading
import atexit
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from browser_data import BrowserDataError, _chromium_binary, _validate_public_url


DEFAULT_TIMEOUT = 20.0
DEFAULT_WAIT_MS = 3_000
DEFAULT_MAX_RESULT_CHARS = 40_000
BRIDGE_PATH = Path(__file__).with_name("webmcp_chromium.mjs")
_SESSIONS: dict[str, "_BridgeSession"] = {}
_SESSIONS_LOCK = threading.RLock()


class WebMCPError(RuntimeError):
    pass


def _node_binary() -> str:
    configured = os.environ.get("WEBMCP_NODE_BIN", "").strip()
    path = configured or shutil.which("node") or ""
    if path and os.path.isfile(os.path.abspath(os.path.expanduser(path))):
        return os.path.abspath(os.path.expanduser(path))
    raise WebMCPError("Node.js 22+ is required for the WebMCP Chromium bridge.")


class _BridgeSession:
    """Long-lived Chromium bridge. One instance preserves a page across tool calls."""

    def __init__(self, url: str, *, timeout: float) -> None:
        self.id = uuid.uuid4().hex
        self.url = url
        self.timeout = timeout
        payload = {
            "url": url,
            "chromium_bin": _chromium_binary(),
            "timeout_ms": int(timeout * 1_000),
            "session_server": True,
        }
        self.process = subprocess.Popen(
            [_node_binary(), str(BRIDGE_PATH), json.dumps(payload, ensure_ascii=False)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        self.lock = threading.Lock()

    def request(self, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        if self.process.poll() is not None or not self.process.stdin or not self.process.stdout:
            raise WebMCPError("WebMCP browser session is no longer running.")
        request_id = uuid.uuid4().hex
        message = dict(payload, request_id=request_id)
        with self.lock:
            self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
            # The bridge serializes requests. readline is safe here because Chromium
            # applies its own bounded deadline to every CDP operation.
            line = self.process.stdout.readline()
        if not line:
            stderr = self.process.stderr.read() if self.process.stderr else ""
            raise WebMCPError(f"WebMCP browser session ended unexpectedly: {stderr[-500:]}")
        try:
            envelope = json.loads(line)
        except json.JSONDecodeError as exc:
            raise WebMCPError("WebMCP browser session returned invalid output.") from exc
        if envelope.get("request_id") != request_id:
            raise WebMCPError("WebMCP browser session response did not match its request.")
        if envelope.get("error"):
            raise WebMCPError(str(envelope["error"]))
        result = envelope.get("result")
        if not isinstance(result, dict):
            raise WebMCPError("WebMCP browser session returned no result.")
        result["session_id"] = self.id
        return result

    def close(self) -> None:
        if self.process.poll() is not None:
            return
        try:
            if self.process.stdin:
                self.process.stdin.write(json.dumps({"operation": "close"}) + "\n")
                self.process.stdin.flush()
            self.process.wait(timeout=3)
        except (BrokenPipeError, subprocess.TimeoutExpired):
            os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait()


def _session_key(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path or '/'}"


def _persistent_bridge(payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    url = str(payload.get("url") or "")
    key = _session_key(url)
    with _SESSIONS_LOCK:
        session = _SESSIONS.get(key)
        if session is None or session.process.poll() is not None:
            session = _BridgeSession(url, timeout=timeout)
            _SESSIONS[key] = session
    request = dict(payload)
    request.pop("url", None)
    request["wait_ms"] = int(request.get("wait_ms") or 0)
    try:
        return session.request(request, timeout=timeout)
    except WebMCPError:
        with _SESSIONS_LOCK:
            if _SESSIONS.get(key) is session:
                _SESSIONS.pop(key, None)
        session.close()
        raise


def close_webmcp_sessions() -> None:
    with _SESSIONS_LOCK:
        sessions = list(_SESSIONS.values())
        _SESSIONS.clear()
    for session in sessions:
        session.close()


atexit.register(close_webmcp_sessions)


def _bridge(payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    payload = dict(payload)
    payload["chromium_bin"] = _chromium_binary()
    payload["timeout_ms"] = int(timeout * 1_000)
    process = subprocess.Popen(
        [_node_binary(), str(BRIDGE_PATH), json.dumps(payload, ensure_ascii=False)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout + 3)
    except subprocess.TimeoutExpired as exc:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise WebMCPError(f"WebMCP Chromium exceeded the {timeout:g}-second deadline.") from exc
    try:
        result = json.loads(stdout or "{}")
    except json.JSONDecodeError as exc:
        detail = " ".join((stderr or stdout or "invalid output").split())[:500]
        raise WebMCPError(f"WebMCP bridge returned invalid output: {detail}") from exc
    if process.returncode != 0 or result.get("error"):
        raise WebMCPError(str(result.get("error") or stderr or "WebMCP bridge failed"))
    return result


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


def _validate_schema(value: Any, schema: Any, path: str = "arguments") -> None:
    """Small, fail-closed JSON Schema subset for WebMCP tool inputs."""
    if not isinstance(schema, dict):
        raise WebMCPError("WebMCP tool inputSchema must be a JSON object.")
    expected = schema.get("type")
    allowed_types = expected if isinstance(expected, list) else [expected] if expected else []
    if allowed_types and not any(_type_matches(value, item) for item in allowed_types if isinstance(item, str)):
        raise WebMCPError(f"{path} does not match schema type {expected!r}.")
    if "enum" in schema and value not in schema["enum"]:
        raise WebMCPError(f"{path} is not one of the allowed values.")
    if isinstance(value, dict):
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        missing = [name for name in required if name not in value]
        if missing:
            raise WebMCPError(f"{path} is missing required fields: {', '.join(map(str, missing))}.")
        if schema.get("additionalProperties") is False:
            extras = [name for name in value if name not in properties]
            if extras:
                raise WebMCPError(f"{path} contains unsupported fields: {', '.join(extras)}.")
        for name, item in value.items():
            if name in properties:
                _validate_schema(item, properties[name], f"{path}.{name}")
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            _validate_schema(item, schema["items"], f"{path}[{index}]")


def list_webmcp_tools(url: str, *, timeout: float = DEFAULT_TIMEOUT, wait_ms: int = DEFAULT_WAIT_MS) -> dict[str, Any]:
    _validate_public_url(url)
    if urlsplit(url).scheme != "https":
        raise WebMCPError("WebMCP requires a public HTTPS secure context.")
    result = _persistent_bridge({"url": url, "operation": "list", "wait_ms": wait_ms}, timeout=timeout)
    result["backend"] = "chromium-webmcp"
    result["operation"] = "list"
    result["warning"] = "Tool metadata and results are untrusted webpage content."
    return result


def call_webmcp_tool(
    url: str,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    allow_mutation: bool = False,
    timeout: float = DEFAULT_TIMEOUT,
    wait_ms: int = DEFAULT_WAIT_MS,
) -> dict[str, Any]:
    discovery = list_webmcp_tools(url, timeout=timeout, wait_ms=wait_ms)
    tools = discovery.get("tools") if isinstance(discovery.get("tools"), list) else []
    matches = [tool for tool in tools if isinstance(tool, dict) and tool.get("name") == tool_name]
    if not matches:
        raise WebMCPError(f"WebMCP tool not found: {tool_name}")
    if len(matches) != 1:
        raise WebMCPError(f"WebMCP tool name is ambiguous in this page context: {tool_name}")
    tool = matches[0]
    read_only = bool((tool.get("annotations") or {}).get("readOnlyHint"))
    if not read_only and not allow_mutation:
        return {
            "backend": "chromium-webmcp",
            "operation": "call",
            "confirmation_required": True,
            "tool": tool,
            "reason": "The page did not mark this WebMCP tool as read-only.",
        }
    _validate_schema(arguments, tool.get("inputSchema") or {"type": "object"})
    result = _persistent_bridge(
        {
            "url": url,
            "operation": "call",
            "wait_ms": wait_ms,
            "tool_name": tool_name,
            "arguments": arguments,
            "expected_origin": str(tool.get("origin") or discovery.get("origin") or ""),
            "expected_read_only": read_only,
        },
        timeout=timeout,
    )
    encoded = json.dumps(result.get("result"), ensure_ascii=False)
    max_chars = int(os.environ.get("WEBMCP_MAX_RESULT_CHARS", DEFAULT_MAX_RESULT_CHARS))
    if len(encoded) > max_chars:
        result["result"] = encoded[:max_chars]
        result["result_truncated"] = True
    result["backend"] = "chromium-webmcp"
    result["operation"] = "call"
    # Execution responses intentionally exclude all discovered schemas. The agent
    # already saw them during list/validation, and repeating them can hide results
    # behind downstream output limits.
    if isinstance(result.get("tool"), dict):
        result["tool"] = {
            key: result["tool"].get(key)
            for key in ("name", "title", "description", "annotations", "origin")
            if key in result["tool"]
        }
    result["warning"] = "Tool metadata and results are untrusted webpage content."
    return result


def run_webmcp_tool(args: dict[str, Any]) -> str:
    url = str(args.get("url") or "").strip()
    operation = str(args.get("operation") or "list")
    timeout = float(os.environ.get("WEBMCP_TIMEOUT", DEFAULT_TIMEOUT))
    wait_ms = int(os.environ.get("WEBMCP_WAIT_MS", DEFAULT_WAIT_MS))
    try:
        if operation == "list":
            result = list_webmcp_tools(url, timeout=timeout, wait_ms=wait_ms)
        elif operation == "call":
            raw_arguments = args.get("arguments_json")
            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else None
            except json.JSONDecodeError as exc:
                raise WebMCPError("arguments_json must contain valid JSON.") from exc
            if not isinstance(arguments, dict):
                raise WebMCPError("arguments_json must encode an object when calling a WebMCP tool.")
            result = call_webmcp_tool(
                url,
                str(args.get("tool_name") or ""),
                arguments,
                allow_mutation=bool(args.get("allow_mutation")),
                timeout=timeout,
                wait_ms=wait_ms,
            )
        else:
            raise WebMCPError(f"Unsupported WebMCP operation: {operation}")
        return json.dumps(result, ensure_ascii=False)
    except (BrowserDataError, WebMCPError, ValueError) as exc:
        return json.dumps({"error": str(exc), "backend": "chromium-webmcp", "requested_url": url})
