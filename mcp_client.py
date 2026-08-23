"""MCP client for the voice orchestrator and computer-use agent.

Load servers from ``mcp.json`` (Claude/Cursor shape) or ``MCP_SERVERS``.
Neither orchestrator.py nor agent.py speaks JSON-RPC — they call
``mcp_call`` / ``start_mcp`` / ``format_mcp_catalog``.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
MCP_CONFIG_PATH = Path(os.environ.get("MCP_CONFIG") or ROOT / "mcp.json")

MCP_ORCHESTRATOR = os.environ.get("MCP_ORCHESTRATOR", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
MCP_AGENT = os.environ.get("MCP_AGENT", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
MCP_READ_ONLY = os.environ.get("MCP_READ_ONLY", "0").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
MCP_MAX_OUTPUT = int(os.environ.get("MCP_MAX_OUTPUT", "24000"))
MCP_CONNECT_TIMEOUT = float(os.environ.get("MCP_CONNECT_TIMEOUT", "25"))
MCP_CALL_TIMEOUT = float(os.environ.get("MCP_CALL_TIMEOUT", "60"))


def _is_fatal(exc: BaseException) -> bool:
    return isinstance(exc, (KeyboardInterrupt, SystemExit, asyncio.CancelledError))


def _mcp_error_text(exc: BaseException) -> str:
    try:
        from mcp_auth import unwrap_error

        err = unwrap_error(exc)
    except Exception:
        err = exc
    text = str(err).strip() or type(err).__name__
    return text.replace("\n", " ")[:300]

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_WRITE_NAME = re.compile(
    r"(^|_)(create|update|delete|remove|post|send|patch|put|archive|"
    r"buy|write|insert|drop|cancel|merge|approve|ship|launch|edit|"
    r"set|add|remove)(_|$)|^(create|update|delete|post|send|write)",
    re.I,
)
_SECRET_KEY = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|authorization|credential)",
    re.I,
)


@dataclass
class ServerSpec:
    name: str
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    transport: str = "stdio"  # stdio | http | sse
    auth: str = ""  # oauth | ""
    enabled: bool = True


@dataclass
class McpTool:
    server: str
    name: str
    description: str
    read_only: bool
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class _LiveServer:
    spec: ServerSpec
    session: Any
    tools: list[McpTool] = field(default_factory=list)
    error: str | None = None
    stop: Any = None  # asyncio.Event
    task: Any = None  # asyncio.Task


def expand_env_value(value: str, environ: dict[str, str] | None = None) -> str:
    env = environ if environ is not None else os.environ

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        default = match.group(2)
        if key in env:
            return env[key]
        if default is not None:
            return default
        return ""

    return _ENV_RE.sub(repl, value)


def _expand_map(data: dict[str, Any], environ: dict[str, str] | None = None) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, val in (data or {}).items():
        out[str(key)] = expand_env_value(str(val), environ)
    return out


def _parse_servers(data: Any, environ: dict[str, str] | None = None) -> dict[str, ServerSpec]:
    if not isinstance(data, dict):
        return {}
    raw = data.get("mcpServers")
    if raw is None:
        raw = data.get("servers")
    if raw is None:
        # Bare { "github": { "command": ... } }
        if any(isinstance(v, dict) and ("command" in v or "url" in v) for v in data.values()):
            raw = data
        else:
            return {}
    if not isinstance(raw, dict):
        return {}

    specs: dict[str, ServerSpec] = {}
    for name, spec in raw.items():
        if not isinstance(spec, dict):
            continue
        if spec.get("disabled") is True or spec.get("enabled") is False:
            continue
        command = spec.get("command")
        url = spec.get("url") or spec.get("serverUrl")
        args = spec.get("args") or []
        if not isinstance(args, list):
            args = [str(args)]
        transport = str(spec.get("type") or spec.get("transport") or "").strip().lower()
        if not transport:
            if command:
                transport = "stdio"
            elif url and (str(url).rstrip("/").endswith("/sse") or "/sse" in str(url)):
                transport = "sse"
            else:
                transport = "http"
        if transport in {"streamable-http", "streamable_http", "http"}:
            transport = "http"
        auth = str(spec.get("auth") or spec.get("authentication") or "").strip().lower()
        if auth in {"oauth2", "browser", "login"}:
            auth = "oauth"
        elif auth in {"bearer", "pat", "token"}:
            auth = "token"
        specs[str(name)] = ServerSpec(
            name=str(name),
            command=str(command) if command else None,
            args=[str(a) for a in args],
            env=_expand_map(spec.get("env") or {}, environ),
            url=expand_env_value(str(url), environ) if url else None,
            headers=_expand_map(spec.get("headers") or {}, environ),
            transport=transport,
            auth=auth,
            enabled=True,
        )
    return specs


def load_mcp_config(
    path: Path | None = None,
    *,
    environ: dict[str, str] | None = None,
) -> dict[str, ServerSpec]:
    env = environ if environ is not None else os.environ
    cfg_path = path
    if cfg_path is None:
        cfg_path = Path(env.get("MCP_CONFIG") or MCP_CONFIG_PATH)

    servers: dict[str, ServerSpec] = {}
    if cfg_path.is_file():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"[mcp] invalid JSON in {cfg_path}: {e}", flush=True)
            data = {}
        servers.update(_parse_servers(data, env))

    extra = (env.get("MCP_SERVERS") or "").strip()
    if extra:
        try:
            servers.update(_parse_servers(json.loads(extra), env))
        except json.JSONDecodeError as e:
            print(f"[mcp] MCP_SERVERS is not valid JSON: {e}", flush=True)

    enable = (env.get("MCP_ENABLE") or "").strip()
    if enable:
        wanted = {s.strip() for s in enable.split(",") if s.strip()}
        servers = {k: v for k, v in servers.items() if k in wanted}
    return servers


def tool_is_read_only(name: str, annotations: Any | None = None) -> bool:
    hint = None
    if annotations is not None:
        hint = getattr(annotations, "readOnlyHint", None)
        if hint is None and isinstance(annotations, dict):
            hint = annotations.get("readOnlyHint")
    if hint is True:
        return True
    if hint is False:
        return False
    return not bool(_WRITE_NAME.search(name or ""))


def redact_for_log(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if _SECRET_KEY.search(str(k)):
                out[k] = "***"
            else:
                out[k] = redact_for_log(v)
        return out
    if isinstance(value, list):
        return [redact_for_log(v) for v in value]
    return value


def parse_mcp_arguments(raw: Any) -> dict[str, Any]:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _format_call_result(result: Any) -> str:
    is_error = bool(getattr(result, "isError", False))
    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        btype = getattr(block, "type", None)
        if btype == "text" or hasattr(block, "text"):
            text = getattr(block, "text", None)
            if text:
                parts.append(str(text))
        elif btype == "image":
            parts.append("[image content omitted]")
        else:
            parts.append(str(block))
    structured = getattr(result, "structuredContent", None)
    if structured is not None and not parts:
        try:
            parts.append(json.dumps(structured, ensure_ascii=False, default=str))
        except TypeError:
            parts.append(str(structured))
    body = "\n".join(parts).strip() or "(empty MCP result)"
    if is_error and not body.lower().startswith("error"):
        body = f"Error: {body}"
    if len(body) > MCP_MAX_OUTPUT:
        body = body[:MCP_MAX_OUTPUT] + "\n… [truncated]"
    return body


MCP_CALL_TOOL = {
    "type": "function",
    "name": "mcp_call",
    "description": (
        "Call a tool on a connected MCP server (GitHub, Linear, web search, "
        "docs, analytics, …). Prefer this over start_task, the computer tool, "
        "or run_terminal scraping when a catalogued MCP tool can complete the "
        "request. Pass arguments as a JSON object string (use {} if none)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "server": {
                "type": "string",
                "description": "MCP server name from the catalog (e.g. github).",
            },
            "tool": {
                "type": "string",
                "description": "Tool name on that server (e.g. list_issues).",
            },
            "arguments": {
                "type": "string",
                "description": (
                    'JSON object of tool arguments, e.g. {"query":"checkout"}. '
                    "Use {} if the tool takes no arguments."
                ),
            },
        },
        "required": ["server", "tool", "arguments"],
        "additionalProperties": False,
    },
    "strict": True,
}


class McpManager:
    """Long-lived MCP sessions on a background asyncio loop."""

    def __init__(self, specs: dict[str, ServerSpec] | None = None) -> None:
        self._specs = specs if specs is not None else load_mcp_config()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._servers: dict[str, _LiveServer] = {}
        self._lock = threading.Lock()
        self._started = False
        self._pending_futs: list[concurrent.futures.Future] = []

    @property
    def connected(self) -> bool:
        return any(s.session is not None and not s.error for s in self._servers.values())

    def tools(self) -> list[McpTool]:
        out: list[McpTool] = []
        for live in self._servers.values():
            if live.session is None:
                continue
            out.extend(live.tools)
        return out

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            if not self._specs:
                print("[mcp] no servers in mcp.json / MCP_SERVERS", flush=True)
                self._started = True
                return
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="mcp-loop",
                daemon=True,
            )
            self._thread.start()
            try:
                self._submit(
                    self._connect_all(),
                    timeout=MCP_CONNECT_TIMEOUT + 15,
                )
            except concurrent.futures.TimeoutError:
                print(
                    "[mcp] connect still running in background "
                    f"(>{MCP_CONNECT_TIMEOUT + 15:.0f}s); other servers may already be up",
                    flush=True,
                )
            except BaseException as e:
                if _is_fatal(e):
                    raise
                print(f"[mcp] connect failed: {_mcp_error_text(e)}", flush=True)
            self._started = True

    def stop(self) -> None:
        with self._lock:
            if not self._started:
                return
            if self._loop is not None:
                try:
                    self._submit(self._disconnect_all(), timeout=8)
                except BaseException as e:
                    if _is_fatal(e):
                        raise
                    print(f"[mcp] shutdown error: {_mcp_error_text(e)}", flush=True)
                try:
                    self._loop.call_soon_threadsafe(self._loop.stop)
                except BaseException as e:
                    if _is_fatal(e):
                        raise
                    print(f"[mcp] loop stop error: {_mcp_error_text(e)}", flush=True)
            if self._thread is not None:
                self._thread.join(timeout=5)
            self._loop = None
            self._thread = None
            self._servers.clear()
            self._started = False

    def ensure_connected(self, server: str) -> str | None:
        """Connect (or reconnect) a configured server. Returns an error string or None."""
        name = (server or "").strip()
        if not name:
            return "Error: mcp_call requires server."
        if name not in self._specs:
            # Config may have been edited after start — reload once.
            try:
                self._specs = load_mcp_config()
            except Exception:
                pass
        spec = self._specs.get(name)
        if spec is None:
            known = ", ".join(sorted(self._specs)) or "(none)"
            return f"Error: unknown MCP server {name!r}. Configured: {known}"
        live = self._servers.get(name)
        if live is not None and live.session is not None and not live.error:
            return None
        if not self._started or self._loop is None:
            return f"Error: MCP is not started; cannot connect {name!r}."
        print(f"[mcp] connecting {name}…", flush=True)
        try:
            self._submit(self._connect_one(spec), timeout=MCP_CONNECT_TIMEOUT + 5)
        except concurrent.futures.TimeoutError:
            return (
                f"Error: MCP server {name!r} timed out connecting "
                f"(is it running? {spec.url or spec.command or name})."
            )
        except BaseException as e:
            if _is_fatal(e):
                raise
            return f"Error: MCP server {name!r} connect failed: {_mcp_error_text(e)}"
        live = self._servers.get(name)
        if live is None or live.session is None:
            detail = (live.error if live else None) or "not connected"
            hint = ""
            if spec.url and "localhost" in spec.url:
                hint = f" Start the local server, then retry ({spec.url})."
            return f"Error: MCP server {name!r} is not connected ({detail}).{hint}"
        return None

    def call(self, server: str, tool: str, arguments: dict[str, Any] | None = None) -> str:
        name = (server or "").strip()
        tool_name = (tool or "").strip()
        if not name or not tool_name:
            return "Error: mcp_call requires server and tool."
        connect_err = self.ensure_connected(name)
        if connect_err:
            return connect_err
        live = self._servers.get(name)
        if live is None or live.session is None:
            available = ", ".join(
                sorted(n for n, s in self._servers.items() if s.session is not None)
            ) or "(none)"
            return f"Error: MCP server {name!r} is not connected. Available: {available}"
        meta = next((t for t in live.tools if t.name == tool_name), None)
        if meta is None:
            names = ", ".join(t.name for t in live.tools) or "(none)"
            return f"Error: tool {tool_name!r} not on server {name!r}. Tools: {names}"
        if MCP_READ_ONLY and not meta.read_only:
            return (
                f"Error: {name}/{tool_name} looks like a write and MCP_READ_ONLY=1. "
                "Set MCP_READ_ONLY=0 to allow it."
            )
        args = arguments or {}
        print(
            f"[mcp] {name}.{tool_name} {json.dumps(redact_for_log(args), default=str)[:200]}",
            flush=True,
        )
        try:
            return self._submit(
                self._call_async(live, tool_name, args),
                timeout=MCP_CALL_TIMEOUT,
            )
        except BaseException as e:
            if _is_fatal(e):
                raise
            return f"Error calling {name}/{tool_name}: {_mcp_error_text(e)}"

    def catalog_text(self) -> str:
        if not self._specs and not self._servers:
            return "No MCP servers connected. Copy mcp.json.example to mcp.json and add a " "server, then restart."
        lines: list[str] = []
        for name, spec in self._specs.items():
            live = self._servers.get(name)
            if live is None:
                where = spec.url or spec.command or name
                lines.append(
                    f"- {name}: not connected yet (will retry on mcp_call; {where})"
                )
                continue
            if live.error or live.session is None:
                err = live.error or "not connected"
                where = spec.url or spec.command or name
                lines.append(f"- {name}: failed ({err}); retry on mcp_call — {where}")
                continue
            shown = live.tools
            if MCP_READ_ONLY:
                shown = [t for t in shown if t.read_only]
            if not shown:
                lines.append(f"- {name}: connected, no tools available")
                continue
            bits = []
            for t in shown[:24]:
                desc = (t.description or "").replace("\n", " ").strip()
                if len(desc) > 72:
                    desc = desc[:69] + "…"
                bits.append(f"{t.name}" + (f" — {desc}" if desc else ""))
            extra = f" (+{len(shown) - 24} more)" if len(shown) > 24 else ""
            lines.append(f"- {name}: " + "; ".join(bits) + extra)
        if not lines:
            return "No MCP servers connected."
        hint = (
            "Connected MCP servers. Prefer mcp_call over start_task / computer / "
            "run_terminal when one of these tools can complete the request."
        )
        if MCP_READ_ONLY:
            hint += " Write/delete tools are blocked (MCP_READ_ONLY=1)."
        return hint + "\n" + "\n".join(lines)

    def _run_loop(self) -> None:
        assert self._loop is not None

        def _handler(_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
            err = context.get("exception")
            if isinstance(err, BaseException):
                print(f"[mcp] loop: {_mcp_error_text(err)}", flush=True)
                return
            msg = str(context.get("message") or "unknown error")
            print(f"[mcp] loop: {msg}", flush=True)

        self._loop.set_exception_handler(_handler)
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _submit(self, coro, *, timeout: float):
        if self._loop is None:
            raise RuntimeError("MCP loop is not running")
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            # Keep the Future so the asyncio Task is not garbage-collected
            # ("Task was destroyed but it is pending").
            self._pending_futs.append(fut)
            raise

    async def _connect_all(self) -> None:
        results = await asyncio.gather(
            *(self._connect_one(spec) for spec in self._specs.values()),
            return_exceptions=True,
        )
        for spec, result in zip(self._specs.values(), results):
            if not isinstance(result, BaseException):
                continue
            if _is_fatal(result):
                raise result
            msg = _mcp_error_text(result)
            print(f"[mcp] {spec.name}: {msg}", flush=True)
            live = self._servers.get(spec.name)
            if live is None or live.session is None:
                self._servers[spec.name] = _LiveServer(spec=spec, session=None, error=msg)

    async def _connect_one(self, spec: ServerSpec) -> None:
        from contextlib import AsyncExitStack

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        prev = self._servers.get(spec.name)
        if prev is not None and prev.stop is not None:
            try:
                prev.stop.set()
            except Exception:
                pass

        ready = asyncio.Event()
        stop = asyncio.Event()
        box: dict[str, Any] = {}

        async def lifetime() -> None:
            stack = AsyncExitStack()
            await stack.__aenter__()
            try:
                if spec.transport == "stdio":
                    if not spec.command:
                        raise ValueError("stdio server needs command")
                    env = dict(os.environ)
                    env.update(spec.env)
                    params = StdioServerParameters(
                        command=spec.command,
                        args=spec.args,
                        env=env,
                    )
                    read, write = await stack.enter_async_context(stdio_client(params))
                elif spec.transport == "sse":
                    if not spec.url:
                        raise ValueError("sse server needs url")
                    from mcp.client.sse import sse_client

                    oauth = self._oauth_auth(spec)
                    read, write = await stack.enter_async_context(
                        sse_client(
                            spec.url,
                            headers=spec.headers or None,
                            auth=oauth,
                        )
                    )
                else:
                    if not spec.url:
                        raise ValueError("http server needs url")
                    from mcp.client.streamable_http import streamablehttp_client

                    oauth = self._oauth_auth(spec)
                    read, write, _sid = await stack.enter_async_context(
                        streamablehttp_client(
                            spec.url,
                            headers=spec.headers or None,
                            auth=oauth,
                        )
                    )
                session = await stack.enter_async_context(ClientSession(read, write))
                await asyncio.wait_for(session.initialize(), timeout=MCP_CONNECT_TIMEOUT)
                tools = await self._list_tools(session, spec.name)
                live = _LiveServer(
                    spec=spec,
                    session=session,
                    tools=tools,
                    stop=stop,
                )
                box["live"] = live
                self._servers[spec.name] = live
                print(
                    f"[mcp] connected {spec.name} ({len(tools)} tool(s), {spec.transport})",
                    flush=True,
                )
                ready.set()
                await stop.wait()
            except asyncio.CancelledError:
                ready.set()
                raise
            except BaseException as e:
                box["error"] = e
                ready.set()
                if _is_fatal(e):
                    raise
            finally:
                try:
                    await stack.aclose()
                except asyncio.CancelledError:
                    raise
                except BaseException as e:
                    print(f"[mcp] {spec.name} close: {_mcp_error_text(e)}", flush=True)

        task = asyncio.create_task(lifetime(), name=f"mcp-{spec.name}")
        try:
            await asyncio.wait_for(ready.wait(), timeout=MCP_CONNECT_TIMEOUT)
        except asyncio.TimeoutError:
            task.cancel()
            msg = f"timed out after {MCP_CONNECT_TIMEOUT:.0f}s"
            print(f"[mcp] {spec.name}: {msg}", flush=True)
            self._servers[spec.name] = _LiveServer(spec=spec, session=None, error=msg)
            return
        if "error" in box:
            err = box["error"]
            if isinstance(err, BaseException) and _is_fatal(err):
                raise err
            msg = (
                _mcp_error_text(err)
                if isinstance(err, BaseException)
                else str(err)
            )
            print(f"[mcp] {spec.name}: {msg}", flush=True)
            self._servers[spec.name] = _LiveServer(spec=spec, session=None, error=msg)
            return
        live = box.get("live")
        if live is not None:
            live.task = task

    def _oauth_auth(self, spec: ServerSpec):
        from mcp_auth import FileTokenStorage, oauth_httpx_auth

        if spec.auth in {"oauth", "token"}:
            if not FileTokenStorage(spec.name).has_tokens() and not any(
                str(k).lower() == "authorization" for k in (spec.headers or {})
            ):
                raise RuntimeError(
                    f"{spec.name} is not logged in. Run: cua mcp login {spec.name}"
                )
        return oauth_httpx_auth(spec)

    async def _list_tools(self, session: Any, server: str) -> list[McpTool]:
        collected: list[McpTool] = []
        cursor = None
        while True:
            page = await session.list_tools(cursor=cursor)
            for tool in page.tools or []:
                schema = getattr(tool, "inputSchema", None) or {}
                if not isinstance(schema, dict):
                    schema = {}
                collected.append(
                    McpTool(
                        server=server,
                        name=str(tool.name),
                        description=str(tool.description or ""),
                        read_only=tool_is_read_only(tool.name, getattr(tool, "annotations", None)),
                        input_schema=schema,
                    )
                )
            cursor = getattr(page, "nextCursor", None)
            if not cursor:
                break
        return collected

    async def _call_async(self, live: _LiveServer, tool: str, arguments: dict[str, Any]) -> str:
        result = await live.session.call_tool(tool, arguments)
        return _format_call_result(result)

    async def _disconnect_all(self) -> None:
        tasks = []
        for live in list(self._servers.values()):
            if live.stop is not None:
                live.stop.set()
            if live.task is not None:
                tasks.append(live.task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._servers.clear()


_manager: McpManager | None = None
_manager_lock = threading.Lock()


def get_manager() -> McpManager | None:
    return _manager


def start_mcp(*, specs: dict[str, ServerSpec] | None = None) -> McpManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = McpManager(specs)
            try:
                _manager.start()
            except BaseException as e:
                if _is_fatal(e):
                    _manager = None
                    raise
                print(f"[mcp] start failed: {_mcp_error_text(e)}", flush=True)
        return _manager


def stop_mcp() -> None:
    global _manager
    with _manager_lock:
        if _manager is not None:
            try:
                _manager.stop()
            except BaseException as e:
                if _is_fatal(e):
                    raise
                print(f"[mcp] stop failed: {_mcp_error_text(e)}", flush=True)
            _manager = None


def mcp_openai_tools(*, for_agent: bool = False) -> list[dict]:
    if for_agent and not MCP_AGENT:
        return []
    if not for_agent and not MCP_ORCHESTRATOR:
        return []
    mgr = _manager
    if mgr is None or not mgr.connected:
        return []
    return [MCP_CALL_TOOL]


def format_mcp_catalog() -> str:
    mgr = _manager
    if mgr is None:
        return ""
    return mgr.catalog_text()


def run_mcp_tool(name: str, args: dict[str, Any]) -> str:
    if name != "mcp_call":
        return f"Unsupported MCP tool: {name}"
    mgr = _manager
    if mgr is None:
        return "Error: MCP is not started."
    arguments = parse_mcp_arguments(args.get("arguments"))
    return mgr.call(str(args.get("server") or ""), str(args.get("tool") or ""), arguments)
