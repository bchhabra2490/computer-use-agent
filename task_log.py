"""
Per-task run logging: records agent messages, tool calls, and computer actions.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGS_DIR = Path(__file__).resolve().parent / "logs"


def _slugify(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug[:max_len] or "task").rstrip("-")


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    return str(value)


class TaskLog:
    """Append-only log for a single agent run."""

    def __init__(self, task: str, logs_dir: Path | None = None):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.task = task
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.status = "running"
        self.dir = (logs_dir or LOGS_DIR) / f"{stamp}_{_slugify(task)}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.steps_path = self.dir / "steps.jsonl"
        self.meta_path = self.dir / "task.json"
        self.transcript_path = self.dir / "transcript.md"
        self._step_n = 0
        self._write_meta()
        self._write_transcript_header()
        print(f"[log] {self.dir}")

    def _write_meta(self, **extra: Any) -> None:
        payload = {
            "task": self.task,
            "started_at": self.started_at,
            "status": self.status,
            "steps": self._step_n,
            "log_dir": str(self.dir),
            **extra,
        }
        self.meta_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _write_transcript_header(self) -> None:
        self.transcript_path.write_text(
            f"# Task log\n\n**Task:** {self.task}\n\n**Started:** {self.started_at}\n\n",
            encoding="utf-8",
        )

    def record(self, kind: str, summary: str, data: Any = None) -> None:
        self._step_n += 1
        entry = {
            "n": self._step_n,
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "summary": summary,
            "data": _jsonable(data),
        }
        with self.steps_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        with self.transcript_path.open("a", encoding="utf-8") as f:
            f.write(f"## Step {self._step_n} — {kind}\n\n{summary}\n\n")
            if data is not None:
                pretty = json.dumps(_jsonable(data), indent=2, ensure_ascii=False)
                if len(pretty) > 4000:
                    pretty = pretty[:4000] + "\n… (truncated)"
                f.write(f"```json\n{pretty}\n```\n\n")

        self._write_meta()
        print(f"[log] #{self._step_n} {kind}: {summary}")
        try:
            from app_status import log as status_log
            from app_status import set_state

            # Full LLM text is already in the phone/tray ring via log_llm.
            if kind not in {"message", "mark_done"}:
                status_log(f"[{kind}] {summary[:160]}")
            if kind in {"start", "computer_actions", "run_terminal", "ask_user", "message"}:
                set_state("agent", summary[:100], task=self.task, log_dir=str(self.dir))
        except Exception:
            pass

    def finish(self, status: str, note: str = "") -> None:
        self.status = status
        ended = datetime.now(timezone.utc).isoformat()
        self._write_meta(ended_at=ended, note=note)
        with self.transcript_path.open("a", encoding="utf-8") as f:
            f.write(f"---\n\n**Status:** {status}\n")
            if note:
                f.write(f"\n{note}\n")
        print(f"[log] finished ({status}) → {self.dir}")
        try:
            from app_status import set_and_log

            set_and_log(
                "done" if status == "completed" else status,
                f"Agent finished ({status})",
                task=self.task,
                log_dir=str(self.dir),
            )
        except Exception:
            pass

    def steps_for_prompt(self, max_chars: int = 12_000, *, snippet_chars: int = 500) -> str:
        """Compact transcript for skill-proposal and memory-extract prompts."""
        if not self.steps_path.exists():
            return "(no steps recorded)"
        lines = []
        for line in self.steps_path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            lines.append(f"{entry['n']}. [{entry['kind']}] {entry['summary']}")
            data = entry.get("data")
            if data:
                snippet = json.dumps(data, ensure_ascii=False)
                if len(snippet) > snippet_chars:
                    snippet = snippet[:snippet_chars] + "…"
                lines.append(f"   {snippet}")
        text = "\n".join(lines)
        if len(text) > max_chars:
            return text[:max_chars] + "\n… (truncated)"
        return text

    def iter_entries(self) -> list[dict[str, Any]]:
        if not self.steps_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.steps_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                rows.append(entry)
        return rows

    def steps_for_eval(
        self,
        *,
        max_chars: int = 10_000,
        head: int = 12,
        tail: int = 40,
        snippet_chars: int = 280,
    ) -> str:
        """
        Compact step history for the periodic coach.

        Keeps early setup (skills/recipes) plus the latest actions so truncation
        does not drop how the run started.
        """
        # Noisy / huge kinds: keep a one-line summary, skip JSON blobs.
        skip_data = {
            "screenshot",
            "recipe_handoff_screenshot",
            "router",
            "skill_proposal",
            "skill_create",
        }
        prefer = {
            "read_skill",
            "list_skills",
            "recipe",
            "recipe_handoff",
            "trace_replay",
            "zmq_message",
            "zmq_context",
            "ask_user",
            "computer_actions",
            "run_terminal",
            "mark_done",
            "message",
            "evaluator",
        }
        entries = self.iter_entries()
        if not entries:
            return "(no steps recorded)"

        def _line(entry: dict[str, Any]) -> str:
            kind = str(entry.get("kind") or "")
            n = entry.get("n", "?")
            summary = str(entry.get("summary") or "")
            out = f"{n}. [{kind}] {summary}"
            data = entry.get("data")
            if data is None or kind in skip_data:
                return out
            if kind not in prefer and not isinstance(data, (dict, list)):
                return out
            snippet = json.dumps(data, ensure_ascii=False)
            if len(snippet) > snippet_chars:
                snippet = snippet[:snippet_chars] + "…"
            return f"{out}\n   {snippet}"

        if len(entries) <= head + tail:
            chosen = entries
        else:
            chosen = entries[:head] + entries[-tail:]
        lines = [_line(e) for e in chosen]
        if len(entries) > head + tail:
            omitted = len(entries) - head - tail
            lines.insert(head, f"… ({omitted} earlier middle steps omitted) …")
        text = "\n".join(lines)
        if len(text) > max_chars:
            # Prefer keeping the tail (recent actions).
            return "… (truncated)\n" + text[-(max_chars - 16) :]
        return text

    def eval_highlights(self) -> dict[str, Any]:
        """Structured facts the coach should see even if step text is truncated."""
        skills: list[str] = []
        recipes: list[str] = []
        user_msgs: list[str] = []
        asks: list[str] = []
        for entry in self.iter_entries():
            kind = str(entry.get("kind") or "")
            summary = str(entry.get("summary") or "").strip()
            data = entry.get("data") if isinstance(entry.get("data"), dict) else {}
            if kind == "read_skill" and summary:
                name = str(data.get("name") or summary).strip()
                if name and name not in skills:
                    skills.append(name)
            elif kind in {"recipe", "recipe_handoff"} and summary:
                bit = summary
                leftover = str(data.get("leftover") or "").strip()
                if leftover:
                    bit = f"{summary} | leftover: {leftover[:200]}"
                recipes.append(bit)
            elif kind == "zmq_message":
                text = str(data.get("text") or summary).strip()
                if text:
                    user_msgs.append(text[:300])
            elif kind == "ask_user" and summary:
                asks.append(summary[:300])
        return {
            "skills_loaded": skills[-8:],
            "recipes": recipes[-4:],
            "user_midtask": user_msgs[-6:],
            "ask_user": asks[-4:],
        }
