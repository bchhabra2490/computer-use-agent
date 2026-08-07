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

    def finish(self, status: str, note: str = "") -> None:
        self.status = status
        ended = datetime.now(timezone.utc).isoformat()
        self._write_meta(ended_at=ended, note=note)
        with self.transcript_path.open("a", encoding="utf-8") as f:
            f.write(f"---\n\n**Status:** {status}\n")
            if note:
                f.write(f"\n{note}\n")
        print(f"[log] finished ({status}) → {self.dir}")

    def steps_for_prompt(self, max_chars: int = 12_000) -> str:
        """Compact transcript for skill-proposal prompts."""
        if not self.steps_path.exists():
            return "(no steps recorded)"
        lines = []
        for line in self.steps_path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            lines.append(f"{entry['n']}. [{entry['kind']}] {entry['summary']}")
            data = entry.get("data")
            if data:
                snippet = json.dumps(data, ensure_ascii=False)
                if len(snippet) > 500:
                    snippet = snippet[:500] + "…"
                lines.append(f"   {snippet}")
        text = "\n".join(lines)
        if len(text) > max_chars:
            return text[:max_chars] + "\n… (truncated)"
        return text
