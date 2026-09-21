from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import llm_trace
import tools_registry as tr
from task_log import TaskLog


def _reset_trace_state() -> None:
    llm_trace._TRACE_ID.set(None)
    llm_trace._PARENT_ID.set(None)
    llm_trace._CALL_PARENT.clear()
    llm_trace._LOGGED_HINT = False
    llm_trace._PHOENIX_READY = False
    llm_trace._PHOENIX_TRACER = None
    llm_trace._PHOENIX_SPAN_ERROR_LOGGED = False
    llm_trace._PHOENIX_SPANS.clear()
    llm_trace._PHOENIX_ROOT_CTX.clear()


def _enable(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_TRACE", "1")
    monkeypatch.setenv("PHOENIX", "0")
    monkeypatch.setattr(llm_trace, "TRACE_DIR", tmp_path)
    _reset_trace_state()


def test_sanitize_strips_images_and_secrets():
    text = (
        'token sk-abcdefghijklmnopqrstuvwxyz password=hunter2 '
        "data:image/png;base64,AAAA"
    )
    out = llm_trace.redact_text(text)
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in out
    assert "hunter2" not in out
    assert "AAAA" not in out
    assert "[redacted]" in out
    assert "image omitted" in out


def test_sanitize_nested_image_url():
    payload = {
        "content": [
            {"type": "input_image", "image_url": "data:image/png;base64," + ("x" * 40)}
        ]
    }
    out = llm_trace.sanitize(payload)
    assert "xxxx" not in json.dumps(out)
    assert "image omitted" in out["content"][0]["image_url"]


def test_traced_call_writes_prompt_response_and_tool_calls(tmp_path, monkeypatch):
    _enable(tmp_path, monkeypatch)
    response = SimpleNamespace(
        id="resp_1",
        status="completed",
        usage=SimpleNamespace(input_tokens=11, output_tokens=3),
        output=[
            SimpleNamespace(
                type="message",
                content=[SimpleNamespace(type="output_text", text="Hi there")],
            ),
            SimpleNamespace(
                type="function_call",
                name="read_memory",
                call_id="call_1",
                arguments='{"kind":"personal"}',
            ),
        ],
    )
    with llm_trace.traced_call(
        lane="main",
        request={
            "model": "gpt-5-mini",
            "instructions": "You are Jarvis. api_key=sk-abcdefghijklmnopqrstuvwxyz",
            "input": "What's on my calendar?",
            "tools": [{"name": "read_memory", "description": "Read a memory file"}],
        },
    ) as rec:
        rec["response"] = response

    files = list(tmp_path.glob("*.jsonl"))
    assert files, f"no jsonl in {tmp_path}"
    rows = llm_trace.read_jsonl(path=files[0], limit=20)
    llm_rows = [r for r in rows if r.get("kind") == "llm"]
    assert len(llm_rows) == 1
    row = llm_rows[0]
    assert row["request"]["model"] == "gpt-5-mini"
    assert row["request"]["tools"][0]["name"] == "read_memory"
    assert "memory file" in row["request"]["tools"][0]["description"]
    assert "What's on my calendar?" in row["request"]["input"]
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in json.dumps(row)
    assert row["response"]["text"] == "Hi there"
    assert row["response"]["tool_calls"][0]["name"] == "read_memory"
    assert row["response"]["usage"]["input_tokens"] == 11
    assert llm_trace._CALL_PARENT["call_1"] == row["span_id"]


def test_traced_tool_writes_args_and_output(tmp_path, monkeypatch):
    _enable(tmp_path, monkeypatch)
    llm_trace.adopt_trace("trace-test")
    with llm_trace.traced_tool(
        "ask_user",
        args={"question": "Which calendar?"},
        call_id="c2",
        lane="main",
    ) as rec:
        rec.output = "Google Calendar"

    files = list(tmp_path.glob("*.jsonl"))
    assert files
    rows = llm_trace.read_jsonl(path=files[0])
    tool_rows = [r for r in rows if r.get("kind") == "tool"]
    assert len(tool_rows) == 1
    assert tool_rows[0]["args"]["question"] == "Which calendar?"
    assert tool_rows[0]["output"] == "Google Calendar"
    assert tool_rows[0]["name"] == "ask_user"


def test_run_tool_records_registry_span(tmp_path, monkeypatch):
    _enable(tmp_path, monkeypatch)
    with patch(
        "displays.format_monitor_occupancy",
        return_value="Running apps:\n  - Notes",
    ):
        out = tr.run_tool("list_open_apps", {"unused": True}, call_id="c3", brain="orchestrator")
    assert "Notes" in out.output
    files = list(tmp_path.glob("*.jsonl"))
    assert files
    rows = llm_trace.read_jsonl(path=files[0])
    tool_rows = [r for r in rows if r.get("kind") == "tool"]
    assert any(r["name"] == "list_open_apps" and "Notes" in str(r["output"]) for r in tool_rows)


def test_disabled_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_TRACE", "0")
    monkeypatch.setattr(llm_trace, "TRACE_DIR", tmp_path)
    _reset_trace_state()
    with llm_trace.traced_call(lane="main", request={"model": "x", "input": "hi"}) as rec:
        rec["response"] = SimpleNamespace(id="1", status="ok", output=[], usage=None)
    assert list(tmp_path.glob("*.jsonl")) == []


def test_records_for_trace_filters_and_snapshots(tmp_path, monkeypatch):
    _enable(tmp_path, monkeypatch)
    llm_trace.start_run(lane="agent", name="agent", trace_id="tid-judge", task="weather")
    with llm_trace.traced_call(
        lane="agent",
        request={
            "model": "gpt-5-mini",
            "instructions": "You are the computer agent. Use Open-Meteo for weather.",
            "input": "What's the weather in Hyderabad?",
            "tools": [
                {
                    "name": "read_skill",
                    "description": "Read a skill file",
                },
                {"name": "open_url"},
            ],
        },
    ) as rec:
        rec["response"] = SimpleNamespace(
            id="resp_w",
            status="completed",
            usage=None,
            output=[
                SimpleNamespace(
                    type="function_call",
                    name="open-google-maps",
                    call_id="c-maps",
                    arguments='{"q":"Hyderabad"}',
                )
            ],
        )
    with llm_trace.traced_tool(
        "open-google-maps",
        args={"q": "Hyderabad"},
        call_id="c-maps",
        lane="agent",
    ) as rec:
        rec.output = "opened maps"

    rows = llm_trace.records_for_trace("tid-judge")
    kinds = [r.get("kind") for r in rows]
    assert "llm" in kinds
    assert "tool" in kinds
    dest = tmp_path / "snap.jsonl"
    assert llm_trace.snapshot_trace("tid-judge", dest) >= 2
    copied = llm_trace._read_jsonl_dicts(dest)
    assert any(r.get("kind") == "llm" for r in copied)


def test_task_log_finish_snapshots_llm_trace(tmp_path, monkeypatch):
    _enable(tmp_path, monkeypatch)
    monkeypatch.setenv("POST_RUN_JUDGE", "0")
    llm_trace.start_run(lane="agent", name="agent", trace_id="tl-snap", task="Open Notes")
    with llm_trace.traced_call(
        lane="agent",
        request={
            "model": "gpt-5-mini",
            "instructions": "Open Notes using the desktop.",
            "input": "Open Notes",
            "tools": [{"name": "open_app", "description": "Open an application"}],
        },
    ) as rec:
        rec["response"] = SimpleNamespace(
            id="resp_n",
            status="completed",
            usage=None,
            output=[
                SimpleNamespace(
                    type="function_call",
                    name="open_app",
                    call_id="c-app",
                    arguments='{"name":"Notes"}',
                )
            ],
        )
    log = TaskLog("Open Notes", logs_dir=tmp_path / "runs", latency_trace_id="tl-snap")
    log.finish("completed")
    meta = json.loads(log.meta_path.read_text(encoding="utf-8"))
    assert meta["latency_trace_id"] == "tl-snap"
    snap = log.dir / "llm_trace.jsonl"
    assert snap.is_file()
    rows = llm_trace._read_jsonl_dicts(snap)
    assert any(r.get("kind") == "llm" for r in rows)
    assert any("open_app" in json.dumps(r.get("request") or {}) for r in rows)


def test_phoenix_disabled_does_not_register(monkeypatch):
    monkeypatch.setenv("PHOENIX", "0")
    llm_trace._PHOENIX_READY = False
    llm_trace._PHOENIX_TRACER = None
    assert llm_trace._phoenix_tracer() is None


def test_phoenix_collector_endpoint_appends_traces_path(monkeypatch):
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "http://127.0.0.1:6006")
    assert llm_trace.phoenix_collector_endpoint() == "http://127.0.0.1:6006/v1/traces"
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "http://127.0.0.1:6006/v1/traces/")
    assert llm_trace.phoenix_collector_endpoint() == "http://127.0.0.1:6006/v1/traces"


def test_phoenix_tracer_exports_via_otlp_http(monkeypatch):
    from opentelemetry.sdk.trace.export import SpanExportResult

    seen: dict = {}

    class FakeExporter:
        def __init__(self, endpoint=None, **kwargs):
            seen["endpoint"] = endpoint

        def export(self, spans):
            seen["spans"] = list(spans)
            return SpanExportResult.SUCCESS

        def shutdown(self, timeout_millis=0):
            return True

        def force_flush(self, timeout_millis=0):
            return True

    monkeypatch.setenv("PHOENIX", "1")
    monkeypatch.setenv("PHOENIX_PROJECT", "cua")
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "http://127.0.0.1:6006")
    llm_trace._PHOENIX_READY = False
    llm_trace._PHOENIX_TRACER = None
    monkeypatch.setattr(
        "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter",
        FakeExporter,
    )
    tracer = llm_trace._phoenix_tracer()
    assert tracer is not None
    assert seen["endpoint"] == "http://127.0.0.1:6006/v1/traces"
    llm_trace._phoenix_start(
        "span1",
        name="responses.create",
        kind="LLM",
        parent_id=None,
        trace_id="tid",
        attrs={"llm.model_name": "gpt-test"},
    )
    llm_trace._phoenix_end("span1", status="ok")
    assert seen.get("spans")
    assert seen["spans"][0].name == "responses.create"
