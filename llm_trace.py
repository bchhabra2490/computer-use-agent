"""Local LLM/tool tracing: JSONL on disk, optional Phoenix on loopback.

Observers never change execution. Prompts, replies, tool args, and tool
results are redacted (secrets, image bytes) and clipped before write.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from events import Event, EventSink, emit

ROOT = Path(__file__).resolve().parent
TRACE_DIR = Path(os.environ.get("LLM_TRACE_DIR") or ROOT / "logs" / "llm")
FIELD_CHARS = int(os.environ.get("LLM_TRACE_FIELD_CHARS", "32000") or "32000")
_LOCK = threading.RLock()
_ATTACHED: set[int] = set()
_CALL_PARENT: dict[str, str] = {}
_TRACE_ID: ContextVar[str | None] = ContextVar("llm_trace_id", default=None)
_PARENT_ID: ContextVar[str | None] = ContextVar("llm_trace_parent", default=None)
_PHOENIX_READY = False
_PHOENIX_TRACER = None
_PHOENIX_SPAN_ERROR_LOGGED = False
_LOGGED_HINT = False

_SECRET_RE = re.compile(
    r"(?i)\b(password|passwd|api[_-]?key|secret|otp|one[- ]time(?: code)?)\b\s*[:=]\s*\S+"
    r"|sk-[A-Za-z0-9]{10,}"
    r"|ghp_[A-Za-z0-9]{10,}"
    r"|github_pat_[A-Za-z0-9_]{10,}"
)
_IMAGE_RE = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/=\s]+")

_REGISTRY_TOOL_EXTRA = frozenset(
    {
        "schedule_task",
        "list_scheduled_tasks",
        "cancel_scheduled_task",
    }
)


def tracing_enabled() -> bool:
    return os.environ.get("LLM_TRACE", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def phoenix_enabled() -> bool:
    return os.environ.get("PHOENIX", "0").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
        "",
    }


def phoenix_collector_endpoint() -> str:
    raw = (os.environ.get("PHOENIX_COLLECTOR_ENDPOINT") or "http://127.0.0.1:6006").strip()
    base = raw.rstrip("/")
    if base.endswith("/v1/traces"):
        return base
    return f"{base}/v1/traces"


def phoenix_project() -> str:
    return (os.environ.get("PHOENIX_PROJECT") or "cua").strip() or "cua"


def _clip(text: str, limit: int | None = None) -> str:
    cap = FIELD_CHARS if limit is None else limit
    body = text if isinstance(text, str) else str(text)
    if cap <= 0 or len(body) <= cap:
        return body
    keep = max(0, cap - 18)
    return body[:keep] + "\n… (truncated)"


def redact_text(text: str) -> str:
    """Strip secrets and inline images from a string."""

    def _image(match: re.Match[str]) -> str:
        return f"[image omitted, {len(match.group(0))} chars]"

    body = _IMAGE_RE.sub(_image, text or "")
    return _SECRET_RE.sub("[redacted]", body)


def sanitize(value: Any, *, depth: int = 0, limit: int | None = None) -> Any:
    """JSON-safe copy with secrets/images removed and strings clipped."""
    if depth > 12:
        return "[truncated]"
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, bytes):
        return f"[bytes omitted, {len(value)} bytes]"
    if isinstance(value, str):
        return _clip(redact_text(value), limit)
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            name = str(key)
            if name in {"image_url", "screenshot_png", "screenshot"} and isinstance(item, str):
                out[name] = f"[image omitted, {len(item)} chars]"
            elif name in {"image_url", "screenshot_png"} and isinstance(item, bytes):
                out[name] = f"[bytes omitted, {len(item)} bytes]"
            else:
                out[name] = sanitize(item, depth=depth + 1, limit=limit)
        return out
    if isinstance(value, (list, tuple)):
        return [sanitize(item, depth=depth + 1, limit=limit) for item in value]
    if hasattr(value, "model_dump"):
        try:
            return sanitize(value.model_dump(), depth=depth + 1, limit=limit)
        except Exception:
            return _clip(redact_text(str(value)), limit)
    return _clip(redact_text(str(value)), limit)


def _jsonl_path() -> Path:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return TRACE_DIR / f"{day}.jsonl"


def _append_jsonl(record: dict[str, Any]) -> None:
    if not tracing_enabled():
        return
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, default=str)
    with _LOCK:
        with _jsonl_path().open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        _maybe_hint()


def _maybe_hint() -> None:
    global _LOGGED_HINT
    if _LOGGED_HINT:
        return
    _LOGGED_HINT = True
    extra = ""
    if phoenix_enabled():
        extra = f"  Phoenix UI http://127.0.0.1:6006  project={phoenix_project()}"
    else:
        extra = "  Set PHOENIX=1 and run `phoenix serve` for the UI."
    print(f"[llm_trace] {_jsonl_path()}{extra}", flush=True)


def _new_id() -> str:
    return uuid.uuid4().hex


def current_trace_id() -> str | None:
    return _TRACE_ID.get()


def adopt_trace(trace_id: str | None) -> str:
    """Bind this thread to an existing trace (agent worker) or start one."""
    tid = (trace_id or "").strip() or _TRACE_ID.get()
    if not tid:
        try:
            from latency_report import current_trace_id as latency_id

            tid = latency_id()
        except Exception:
            tid = None
    if not tid:
        tid = _new_id()
    _TRACE_ID.set(tid)
    return tid


def current_or_start() -> str:
    tid = _TRACE_ID.get()
    if tid:
        return tid
    return adopt_trace(None)


def start_run(
    *,
    lane: str = "main",
    name: str = "turn",
    trace_id: str | None = None,
    **attrs: Any,
) -> str:
    """Open a run/turn span on this thread. Returns trace_id."""
    if _PARENT_ID.get():
        end_run(lane=lane, name=name)
    tid = adopt_trace(trace_id)
    span_id = _new_id()[:16]
    _PARENT_ID.set(span_id)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": "run",
        "phase": "start",
        "name": name,
        "lane": lane,
        "trace_id": tid,
        "span_id": span_id,
        "parent_id": None,
        **{k: sanitize(v) for k, v in attrs.items()},
    }
    _append_jsonl(record)
    _phoenix_start(span_id, name=name, kind="CHAIN", parent_id=None, trace_id=tid, attrs=record)
    return tid


def end_run(*, lane: str = "main", name: str = "turn", **attrs: Any) -> None:
    tid = _TRACE_ID.get()
    span_id = _PARENT_ID.get()
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": "run",
        "phase": "end",
        "name": name,
        "lane": lane,
        "trace_id": tid,
        "span_id": span_id,
        **{k: sanitize(v) for k, v in attrs.items()},
    }
    _append_jsonl(record)
    if span_id:
        _phoenix_end(span_id, status="ok", trace_id=tid)
    _PARENT_ID.set(None)


def _request_view(kwargs: dict[str, Any]) -> dict[str, Any]:
    tools = kwargs.get("tools")
    names: list[str] = []
    if isinstance(tools, list):
        for item in tools:
            if isinstance(item, dict):
                names.append(str(item.get("name") or item.get("type") or "tool"))
            else:
                names.append(str(getattr(item, "name", None) or getattr(item, "type", None) or "tool"))
    return {
        "model": kwargs.get("model"),
        "instructions": sanitize(kwargs.get("instructions")),
        "input": sanitize(kwargs.get("input")),
        "previous_response_id": kwargs.get("previous_response_id"),
        "tools": names,
    }


def _response_view(response: Any) -> dict[str, Any]:
    if response is None:
        return {}
    texts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for item in getattr(response, "output", None) or []:
        kind = getattr(item, "type", None)
        if kind == "message":
            for part in getattr(item, "content", None) or []:
                if getattr(part, "type", None) == "output_text":
                    text = (getattr(part, "text", None) or "").strip()
                    if text:
                        texts.append(text)
        elif kind in {"function_call", "computer_call"}:
            name = getattr(item, "name", None) or (
                "computer" if kind == "computer_call" else "tool"
            )
            args = getattr(item, "arguments", None)
            if args is None and kind == "computer_call":
                actions = getattr(item, "actions", None)
                args = {"actions": sanitize(actions)}
            cid = getattr(item, "call_id", None) or ""
            tool_calls.append(
                {
                    "name": name,
                    "call_id": cid,
                    "arguments": sanitize(args),
                }
            )
    usage = getattr(response, "usage", None)
    usage_view = None
    if usage is not None:
        usage_view = {
            "input_tokens": getattr(usage, "input_tokens", None)
            or getattr(usage, "prompt_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None)
            or getattr(usage, "completion_tokens", None),
        }
    return {
        "id": getattr(response, "id", None),
        "status": getattr(response, "status", None),
        "text": sanitize("\n".join(texts)) if texts else "",
        "tool_calls": tool_calls,
        "usage": usage_view,
    }


def _emit_llm(
    *,
    lane: str,
    request: dict[str, Any],
    response: Any | None,
    error: BaseException | None,
    duration_ms: int,
    trace_id: str,
    span_id: str,
    parent_id: str | None,
) -> None:
    if not tracing_enabled():
        return
    view = _response_view(response)
    for call in view.get("tool_calls") or []:
        cid = str(call.get("call_id") or "").strip()
        if cid:
            _CALL_PARENT[cid] = span_id
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": "llm",
        "name": "responses.create",
        "lane": lane,
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_id": parent_id,
        "duration_ms": duration_ms,
        "status": "error" if error is not None else "ok",
        "error": str(error) if error is not None else None,
        "request": _request_view(request),
        "response": view,
    }
    emit(
        "llm_response",
        lane=lane if lane in {"main", "agent"} else "main",  # type: ignore[arg-type]
        run_id=trace_id,
        span_id=span_id,
        parent_id=parent_id,
        duration_ms=duration_ms,
        status=record["status"],
        model=record["request"].get("model"),
        error=record["error"],
        text=(view.get("text") or "")[:500],
        tool_calls=[c.get("name") for c in (view.get("tool_calls") or [])],
    )
    _append_jsonl(record)
    attrs = {
        "llm.model_name": record["request"].get("model") or "",
        "input.value": json.dumps(record["request"], ensure_ascii=False, default=str)[:FIELD_CHARS],
        "output.value": json.dumps(view, ensure_ascii=False, default=str)[:FIELD_CHARS],
    }
    usage = view.get("usage") or {}
    if usage.get("input_tokens") is not None:
        attrs["llm.token_count.prompt"] = usage["input_tokens"]
    if usage.get("output_tokens") is not None:
        attrs["llm.token_count.completion"] = usage["output_tokens"]
    _phoenix_complete(
        span_id,
        name="responses.create",
        kind="LLM",
        parent_id=parent_id,
        trace_id=trace_id,
        attrs=attrs,
        status="error" if error is not None else "ok",
        duration_ms=duration_ms,
    )


@contextmanager
def traced_call(*, lane: str, request: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Capture one Responses API call. Set ``rec['response']`` before exit."""
    rec: dict[str, Any] = {"response": None}
    if not tracing_enabled():
        yield rec
        return
    trace_id = current_or_start()
    span_id = _new_id()[:16]
    parent_id = _PARENT_ID.get()
    started = time.perf_counter()
    error: BaseException | None = None
    try:
        yield rec
    except BaseException as e:
        error = e
        raise
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000)
        try:
            _emit_llm(
                lane=lane,
                request=request,
                response=rec.get("response"),
                error=error,
                duration_ms=duration_ms,
                trace_id=trace_id,
                span_id=span_id,
                parent_id=parent_id,
            )
        except Exception:
            pass


def traced_responses_create(client: Any, *, lane: str, **kwargs: Any) -> Any:
    """client.responses.create with capture."""
    with traced_call(lane=lane, request=kwargs) as rec:
        rec["response"] = client.responses.create(**kwargs)
        return rec["response"]


def registry_traces_tool(name: str) -> bool:
    try:
        from tools_registry import SHARED_TOOL_NAMES
    except Exception:
        SHARED_TOOL_NAMES = frozenset()
    return name in SHARED_TOOL_NAMES or name in _REGISTRY_TOOL_EXTRA


class _ToolRec:
    __slots__ = ("output", "is_error")

    def __init__(self) -> None:
        self.output: Any = None
        self.is_error = False


@contextmanager
def traced_tool(
    name: str,
    *,
    args: Any = None,
    call_id: str = "",
    lane: str = "main",
) -> Iterator[_ToolRec]:
    rec = _ToolRec()
    if not tracing_enabled():
        yield rec
        return
    trace_id = current_or_start()
    span_id = _new_id()[:16]
    parent_id = _CALL_PARENT.get(call_id) or _PARENT_ID.get()
    started = time.perf_counter()
    safe_args = sanitize(args)
    emit(
        "tool_start",
        lane=lane if lane in {"main", "agent"} else "main",  # type: ignore[arg-type]
        run_id=trace_id,
        name=name,
        call_id=call_id,
        args=safe_args,
        span_id=span_id,
        parent_id=parent_id,
    )
    error: BaseException | None = None
    try:
        yield rec
    except BaseException as e:
        error = e
        rec.is_error = True
        if rec.output is None:
            rec.output = str(e)
        raise
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000)
        try:
            _write_tool_span(
                name=name,
                args=safe_args,
                output=rec.output,
                call_id=call_id,
                lane=lane,
                is_error=rec.is_error or error is not None,
                duration_ms=duration_ms,
                trace_id=trace_id,
                span_id=span_id,
                parent_id=parent_id,
                error=error,
                emit_events=True,
            )
        except Exception:
            pass
        if call_id:
            _CALL_PARENT.pop(call_id, None)


def _write_tool_span(
    *,
    name: str,
    args: Any,
    output: Any,
    call_id: str,
    lane: str,
    is_error: bool,
    duration_ms: int,
    trace_id: str,
    span_id: str,
    parent_id: str | None,
    error: BaseException | None,
    emit_events: bool,
) -> None:
    safe_out = sanitize(output)
    if emit_events:
        emit(
            "tool_result",
            lane=lane if lane in {"main", "agent"} else "main",  # type: ignore[arg-type]
            run_id=trace_id,
            name=name,
            call_id=call_id,
            args=args,
            output=safe_out,
            chars=len(str(safe_out or "")),
            is_error=is_error,
            duration_ms=duration_ms,
            span_id=span_id,
            parent_id=parent_id,
            error=str(error) if error is not None else None,
        )
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": "tool",
        "name": name,
        "lane": lane,
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_id": parent_id,
        "call_id": call_id,
        "duration_ms": duration_ms,
        "status": "error" if is_error else "ok",
        "args": args,
        "output": safe_out,
        "error": str(error) if error is not None else None,
    }
    _append_jsonl(record)
    _phoenix_complete(
        span_id,
        name=name,
        kind="TOOL",
        parent_id=parent_id,
        trace_id=trace_id,
        attrs={
            "tool.name": name,
            "tool.parameters": json.dumps(args, ensure_ascii=False, default=str)[:FIELD_CHARS],
            "output.value": json.dumps(safe_out, ensure_ascii=False, default=str)[:FIELD_CHARS],
        },
        status="error" if is_error else "ok",
        duration_ms=duration_ms,
    )


def record_registry_tool(
    *,
    name: str,
    args: dict[str, Any] | None,
    output: Any,
    call_id: str,
    lane: str,
    is_error: bool,
    duration_ms: int,
) -> None:
    """JSONL/Phoenix for tools that already emitted tool_start / tool_result."""
    if not tracing_enabled():
        return
    trace_id = current_or_start()
    span_id = _new_id()[:16]
    parent_id = _CALL_PARENT.get(call_id) or _PARENT_ID.get()
    _write_tool_span(
        name=name,
        args=sanitize(args),
        output=output,
        call_id=call_id,
        lane=lane,
        is_error=is_error,
        duration_ms=duration_ms,
        trace_id=trace_id,
        span_id=span_id,
        parent_id=parent_id,
        error=None,
        emit_events=False,
    )
    if call_id:
        _CALL_PARENT.pop(call_id, None)


def attach_listener(sink: EventSink) -> None:
    key = id(sink)
    if key in _ATTACHED:
        return
    _ATTACHED.add(key)
    sink.on(_on_event)


def _on_event(event: Event) -> None:
    """Keep EventSink as the bus; JSONL for llm/tool is written at capture sites.

    turn_start / agent_start still flow through events; run spans are opened
    explicitly via start_run so the worker thread owns contextvars.
    """
    del event


def _phoenix_tracer():
    """OTLP HTTP exporter — do not import phoenix / phoenix.otel.

    phoenix 20's package ``__init__`` loads pydantic-ai MCP, which needs mcp 2.x.
    This repo pins mcp 1.x, so ``from phoenix.otel import register`` always fails
    and JSONL kept working while the UI stayed empty.
    """
    global _PHOENIX_READY, _PHOENIX_TRACER
    if _PHOENIX_READY:
        return _PHOENIX_TRACER
    _PHOENIX_READY = True
    if not phoenix_enabled():
        return None
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from openinference.semconv.resource import ResourceAttributes

        endpoint = phoenix_collector_endpoint()
        project = phoenix_project()
        resource = Resource.create({ResourceAttributes.PROJECT_NAME: project})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        _PHOENIX_TRACER = provider.get_tracer("cua.llm_trace")
        print(
            f"[llm_trace] phoenix export → {endpoint}  project={project}  "
            "UI http://127.0.0.1:6006",
            flush=True,
        )
        return _PHOENIX_TRACER
    except Exception as e:
        print(f"[llm_trace] phoenix disabled ({e})", flush=True)
        _PHOENIX_TRACER = None
        return None


_PHOENIX_SPANS: dict[str, Any] = {}
_PHOENIX_ROOT_CTX: dict[str, Any] = {}


def _phoenix_start(
    span_id: str,
    *,
    name: str,
    kind: str,
    parent_id: str | None,
    trace_id: str,
    attrs: dict[str, Any],
) -> None:
    tracer = _phoenix_tracer()
    if tracer is None:
        return
    try:
        from opentelemetry import trace

        ctx = None
        parent_span = _PHOENIX_SPANS.get(parent_id or "")
        if parent_span is not None:
            ctx = trace.set_span_in_context(parent_span)
        elif trace_id in _PHOENIX_ROOT_CTX:
            ctx = _PHOENIX_ROOT_CTX[trace_id]
        span = tracer.start_span(name, context=ctx) if ctx is not None else tracer.start_span(name)
        span.set_attribute("openinference.span.kind", kind)
        span.set_attribute("cua.trace_id", trace_id)
        if parent_id:
            span.set_attribute("cua.parent_id", parent_id)
        for key, value in attrs.items():
            if value is None or key in {"ts", "kind", "phase"}:
                continue
            if isinstance(value, (str, int, float, bool)):
                span.set_attribute(key, value)
        _PHOENIX_SPANS[span_id] = span
        if kind == "CHAIN" and not parent_id:
            _PHOENIX_ROOT_CTX[trace_id] = trace.set_span_in_context(span)
    except Exception as e:
        global _PHOENIX_SPAN_ERROR_LOGGED
        if not _PHOENIX_SPAN_ERROR_LOGGED:
            _PHOENIX_SPAN_ERROR_LOGGED = True
            print(f"[llm_trace] phoenix span failed ({e})", flush=True)


def _phoenix_end(span_id: str, *, status: str, trace_id: str | None = None) -> None:
    span = _PHOENIX_SPANS.pop(span_id, None)
    if span is None:
        return
    try:
        if status == "error":
            from opentelemetry.trace import Status, StatusCode

            span.set_status(Status(StatusCode.ERROR))
        span.end()
    except Exception:
        pass
    if trace_id:
        _PHOENIX_ROOT_CTX.pop(trace_id, None)


def _phoenix_complete(
    span_id: str,
    *,
    name: str,
    kind: str,
    parent_id: str | None,
    trace_id: str,
    attrs: dict[str, Any],
    status: str,
    duration_ms: int,
) -> None:
    del duration_ms
    _phoenix_start(span_id, name=name, kind=kind, parent_id=parent_id, trace_id=trace_id, attrs=attrs)
    _phoenix_end(span_id, status=status)


def read_jsonl(*, path: Path | None = None, limit: int = 200) -> list[dict[str, Any]]:
    src = path if path is not None else _jsonl_path()
    if not src.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in src.read_text(encoding="utf-8").splitlines()[-max(1, limit) :]:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows
