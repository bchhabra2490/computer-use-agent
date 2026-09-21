"""LLM-as-judge for fixture tests and post-run log review.

Two callers share one rubric:

- Tests: ``score_artifact`` on a dict or ``tests/fixtures/judge/*.json``.
- Post-run: ``schedule_post_run_judge`` after ``TaskLog.finish`` (background).

Neither path changes the live agent/orchestrator loop. The coach in
``evaluator.coach_agent`` stays separate.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from llm_client import make_llm_client, parse_json_dict, response_output_text

ROOT = Path(__file__).resolve().parent
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "judge"

_OFF = {"0", "false", "no", "off"}

JUDGE_MODEL = (
    os.environ.get("JUDGE_MODEL") or os.environ.get("EVAL_MODEL") or "gpt-5-mini"
).strip() or "gpt-5-mini"


def _judge_max_chars() -> int:
    try:
        return max(4_000, int(os.environ.get("JUDGE_MAX_CHARS", "80000") or "80000"))
    except ValueError:
        return 80_000


_JUDGE_PROMPT = """You are a quality judge for a desktop voice / computer-use assistant.

The artifact includes every LLM call (instructions, input, the tool catalog
offered on that call, the model reply, and tool calls) plus each tool's
arguments and returned output. Secrets and images are already redacted.
Score from that evidence. Do not invent steps, tools, or prompts that are
not listed. Flag invented tool names (a call whose name was not in that
turn's catalog), wrong routing (maps vs weather, recipe vs skill), loops,
ignored skills, and unused tool results.

Reply JSON only (no markdown fences):
{
  "pass": true or false,
  "scores": {
    "goal": 0,
    "routing": 0,
    "tools": 0,
    "looping": 0,
    "safety": 0
  },
  "findings": ["short fact from the log"],
  "improvements": ["what to do better next time"]
}

Integers 0-5. pass is false when routing or tools are wrong, the agent looped,
or the goal clearly failed. Empty findings/improvements are allowed.
"""


@dataclass
class JudgeVerdict:
    """Structured judge result. ``ok`` is False when scoring itself failed."""

    pass_: bool = False
    scores: dict[str, int] = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    ok: bool = True
    error: str = ""
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["pass"] = payload.pop("pass_")
        return payload


def post_run_enabled() -> bool:
    return os.environ.get("POST_RUN_JUDGE", "1").strip().lower() not in _OFF


def load_fixture(name: str) -> dict[str, Any]:
    path = Path(name)
    if not path.is_file():
        path = FIXTURE_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl_dicts(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _load_llm_trace(log_dir: Path, meta: dict[str, Any]) -> list[dict[str, Any]]:
    snap = log_dir / "llm_trace.jsonl"
    if snap.is_file():
        return _read_jsonl_dicts(snap)
    tid = str(meta.get("latency_trace_id") or "").strip()
    if not tid:
        return []
    try:
        from llm_trace import records_for_trace
    except Exception:
        return []
    try:
        return records_for_trace(tid, started_at=str(meta.get("started_at") or "") or None)
    except Exception:
        return []


def load_run_dir(log_dir: Path) -> dict[str, Any]:
    """Build a judge artifact from a TaskLog directory plus LLM/tool traces."""
    log_dir = Path(log_dir)
    meta: dict[str, Any] = {}
    meta_path = log_dir / "task.json"
    if meta_path.is_file():
        try:
            loaded = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                meta = loaded
        except (OSError, json.JSONDecodeError):
            meta = {}
    steps = _read_jsonl_dicts(log_dir / "steps.jsonl")
    traces = _load_llm_trace(log_dir, meta)
    return {
        "task": str(meta.get("task") or ""),
        "status": str(meta.get("status") or ""),
        "note": str(meta.get("note") or ""),
        "log_dir": str(log_dir),
        "latency_trace_id": str(meta.get("latency_trace_id") or ""),
        "steps": steps,
        "llm_trace": traces,
    }


def parse_verdict(payload: Any, *, model: str = "") -> JudgeVerdict:
    if not isinstance(payload, dict):
        return JudgeVerdict(ok=False, error="judge returned no JSON object", model=model)
    scores_raw = payload.get("scores") if isinstance(payload.get("scores"), dict) else {}
    scores: dict[str, int] = {}
    for key in ("goal", "routing", "tools", "looping", "safety"):
        try:
            scores[key] = max(0, min(5, int(scores_raw.get(key, 0))))
        except (TypeError, ValueError):
            scores[key] = 0
    findings = [
        str(item).strip()
        for item in (payload.get("findings") or [])
        if str(item).strip()
    ]
    improvements = [
        str(item).strip()
        for item in (payload.get("improvements") or [])
        if str(item).strip()
    ]
    passed = payload.get("pass")
    if passed is None:
        passed = payload.get("pass_")
    return JudgeVerdict(
        pass_=bool(passed),
        scores=scores,
        findings=findings,
        improvements=improvements,
        ok=True,
        model=model or JUDGE_MODEL,
    )


def _clip_text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, default=str)
    else:
        text = str(value)
    if limit <= 0 or len(text) <= limit:
        return text
    keep = max(0, limit - 18)
    return text[:keep] + "\n… (truncated)"


def _tool_catalog_lines(tools: Any) -> list[str]:
    if not isinstance(tools, list) or not tools:
        return ["(none)"]
    lines: list[str] = []
    for item in tools:
        if isinstance(item, str):
            lines.append(f"- {item}")
            continue
        if not isinstance(item, dict):
            lines.append(f"- {item}")
            continue
        name = str(item.get("name") or item.get("type") or "tool")
        desc = str(item.get("description") or "").strip()
        if desc:
            lines.append(f"- {name}: {desc}")
        else:
            lines.append(f"- {name}")
    return lines


def _format_llm_trace(records: list[dict[str, Any]]) -> list[str]:
    if not records:
        return ["LLM and tool trace: (none — TaskLog steps only)"]
    lines = ["LLM and tool trace:"]
    llm_n = 0
    tool_n = 0
    for rec in records:
        if not isinstance(rec, dict):
            continue
        kind = str(rec.get("kind") or "")
        if kind == "run":
            lines.append(
                f"\n--- run {rec.get('phase') or ''} {rec.get('name') or ''} "
                f"lane={rec.get('lane') or ''} ---"
            )
            continue
        if kind == "llm":
            llm_n += 1
            req = rec.get("request") if isinstance(rec.get("request"), dict) else {}
            resp = rec.get("response") if isinstance(rec.get("response"), dict) else {}
            lines.append(
                f"\n--- LLM #{llm_n} lane={rec.get('lane') or ''} "
                f"model={req.get('model') or ''} status={rec.get('status') or ''} ---"
            )
            prev = req.get("previous_response_id")
            if prev:
                lines.append(f"previous_response_id: {prev}")
            lines.append("Tools offered:")
            lines.extend(_tool_catalog_lines(req.get("tools")))
            instructions = _clip_text(req.get("instructions"), 16_000)
            if instructions:
                lines.append("Instructions:")
                lines.append(instructions)
            payload = _clip_text(req.get("input"), 24_000)
            if payload:
                lines.append("Input:")
                lines.append(payload)
            text = _clip_text(resp.get("text"), 8_000)
            if text:
                lines.append("Response text:")
                lines.append(text)
            calls = resp.get("tool_calls") or []
            if isinstance(calls, list) and calls:
                lines.append("Tool calls:")
                for call in calls:
                    if not isinstance(call, dict):
                        continue
                    name = str(call.get("name") or "tool")
                    args = _clip_text(call.get("arguments"), 4_000)
                    lines.append(f"- {name}({args})")
            err = rec.get("error")
            if err:
                lines.append(f"Error: {err}")
            continue
        if kind == "tool":
            tool_n += 1
            status = rec.get("status") or "ok"
            lines.append(
                f"\n--- Tool #{tool_n} {rec.get('name') or 'tool'} status={status} ---"
            )
            args = _clip_text(rec.get("args"), 4_000)
            if args:
                lines.append("Args:")
                lines.append(args)
            output = _clip_text(rec.get("output"), 8_000)
            if output:
                lines.append("Output:")
                lines.append(output)
            err = rec.get("error")
            if err:
                lines.append(f"Error: {err}")
    return lines


def _format_steps(steps: Any, *, include_data: bool) -> list[str]:
    lines = ["TaskLog steps:"]
    if not isinstance(steps, list) or not steps:
        lines.append("(none)")
        return lines
    for index, row in enumerate(steps, start=1):
        if not isinstance(row, dict):
            continue
        kind = str(row.get("kind") or row.get("name") or "unknown")
        summary = str(row.get("summary") or "")
        extra = ""
        if include_data and row.get("data") is not None:
            extra = f" | {_clip_text(row.get('data'), 2_000)}"
        lines.append(f"{index}. [{kind}] {summary}{extra}")
    return lines


def _format_artifact(artifact: dict[str, Any], *, max_chars: int | None = None) -> str:
    task = str(artifact.get("task") or "").strip() or "(none)"
    status = str(artifact.get("status") or "").strip() or "(unknown)"
    note = str(artifact.get("note") or "").strip()
    traces = artifact.get("llm_trace") or []
    has_trace = isinstance(traces, list) and bool(traces)
    lines = [f"Task: {task}", f"Status: {status}"]
    if note:
        lines.append(f"Note: {note}")
    if has_trace:
        lines.extend(_format_llm_trace(traces))
        lines.append("")
        lines.extend(_format_steps(artifact.get("steps") or [], include_data=False))
    else:
        lines.extend(_format_llm_trace([]))
        lines.append("")
        lines.extend(_format_steps(artifact.get("steps") or [], include_data=True))
    text = "\n".join(lines)
    cap = _judge_max_chars() if max_chars is None else max_chars
    if len(text) > cap:
        text = text[:cap] + "\n… (truncated)"
    return text


def score_artifact(
    artifact: dict[str, Any],
    *,
    client: Any | None = None,
    model: str | None = None,
) -> JudgeVerdict:
    """Score a fixture or in-memory run. Used by tests and post-run."""
    model_id = (model or JUDGE_MODEL).strip() or JUDGE_MODEL
    llm = client if client is not None else make_llm_client(model=model_id)
    prompt = _JUDGE_PROMPT + "\n\nRun artifact:\n" + _format_artifact(artifact)
    try:
        response = llm.responses.create(model=model_id, input=prompt)
        raw = response_output_text(response)
        payload = parse_json_dict(raw)
        verdict = parse_verdict(payload, model=model_id)
        if payload is None and verdict.ok:
            return JudgeVerdict(ok=False, error="judge returned no JSON object", model=model_id)
        return verdict
    except Exception as e:
        return JudgeVerdict(ok=False, error=str(e), model=model_id)


def score_run_dir(
    log_dir: Path | str,
    *,
    client: Any | None = None,
    model: str | None = None,
) -> JudgeVerdict:
    """Score a finished TaskLog directory and write ``judge.json``."""
    path = Path(log_dir)
    artifact = load_run_dir(path)
    verdict = score_artifact(artifact, client=client, model=model)
    out = path / "judge.json"
    try:
        out.write_text(json.dumps(verdict.to_dict(), indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        if verdict.ok:
            verdict = JudgeVerdict(ok=False, error=str(e), model=verdict.model)
    return verdict


def schedule_post_run_judge(
    log_dir: Path | str,
    *,
    task: str = "",
    status: str = "",
) -> None:
    """Start a daemon scorer. Never raises into the agent worker."""
    del task, status
    if not post_run_enabled():
        return
    path = Path(log_dir)

    def _target() -> None:
        try:
            verdict = score_run_dir(path)
            if not verdict.ok:
                print(f"[judge] post-run failed: {verdict.error}", flush=True)
                return
            print(f"[judge] post-run pass={verdict.pass_} → {path / 'judge.json'}", flush=True)
        except Exception as e:
            print(f"[judge] post-run failed: {e}", flush=True)

    threading.Thread(target=_target, name="post-run-judge", daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: python -m judge <task-log-dir>", flush=True)
        return 2
    verdict = score_run_dir(args[0])
    print(json.dumps(verdict.to_dict(), indent=2))
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
