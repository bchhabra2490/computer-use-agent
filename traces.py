"""
Executable action traces for easy desktop tasks.

First successful run records keypress/type/wait sequences. Later matching
utterances replay through DesktopController with no screenshot / CU model.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from task_log import TaskLog, _jsonable, _slugify

TRACES_DIR = Path(__file__).resolve().parent / "traces"

TRACE_REPLAY = os.environ.get("TRACE_REPLAY", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
TRACE_RECORD = os.environ.get("TRACE_RECORD", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
TRACE_MAX_ACTIONS = int(os.environ.get("TRACE_MAX_ACTIONS", "20"))

_STABLE = frozenset({"keypress", "type", "wait"})
_UNSTABLE = frozenset({"click", "double_click", "move", "scroll", "drag"})
_SKIP_TYPES = frozenset({"screenshot"})

_HARD_TASK = re.compile(
    r"\b(easyeda|kicad|fusion|solidworks|schematic|pcb|gerber|" r"checkout|place an order|wire|routing|cad)\b",
    re.I,
)
_URL_RE = re.compile(
    r"(https?://[^\s]+|(?:www\.)[a-z0-9.-]+\.[a-z]{2,}(?:/[^\s]*)?|" r"[a-z0-9.-]+\.[a-z]{2,}(?:/[^\s]*)?)",
    re.I,
)
_STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "to",
        "for",
        "in",
        "on",
        "of",
        "at",
        "please",
        "my",
        "me",
        "it",
        "that",
        "this",
        "with",
        "from",
        "into",
        "then",
        "now",
        "just",
        "can",
        "you",
    }
)
_APP_TYPE = re.compile(
    r"^(google chrome|chrome|safari|firefox|notes|terminal|slack|mail|"
    r"messages|finder|preview|spotify|music|calendar)$",
    re.I,
)


class ReplayInterrupted(Exception):
    """Wake word / quit during trace replay."""


@dataclass
class Trace:
    name: str
    match: list[str]
    params: list[str] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    verify: dict = field(default_factory=dict)
    source_task: str = ""
    difficulty: str = "easy"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "match": list(self.match),
            "params": list(self.params),
            "actions": list(self.actions),
            "verify": dict(self.verify),
            "source_task": self.source_task,
            "difficulty": self.difficulty,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Trace:
        return cls(
            name=str(data.get("name") or "trace"),
            match=[str(m) for m in (data.get("match") or []) if str(m).strip()],
            params=[str(p) for p in (data.get("params") or []) if str(p).strip()],
            actions=[a for a in (data.get("actions") or []) if isinstance(a, dict)],
            verify=dict(data.get("verify") or {}),
            source_task=str(data.get("source_task") or ""),
            difficulty=str(data.get("difficulty") or "easy"),
        )


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s.:/-]", " ", (text or "").lower())).strip()


def content_words(text: str, extra_remove: tuple[str, ...] = ()) -> list[str]:
    lowered = (text or "").lower().replace("google chrome", "chrome")
    words = re.findall(r"[a-z0-9]+", lowered)
    skip = _STOP | {w.lower() for w in extra_remove}
    return [w for w in words if w not in skip and len(w) > 2]


def collect_logged_actions(log: TaskLog) -> list[dict]:
    if not log.steps_path.exists():
        return []
    actions: list[dict] = []
    for line in log.steps_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("kind") != "computer_actions":
            continue
        data = entry.get("data") or {}
        batch = data.get("actions") if isinstance(data, dict) else None
        if isinstance(batch, list):
            for item in batch:
                if isinstance(item, dict):
                    actions.append(item)
    return actions


def logged_difficulty(log: TaskLog) -> str | None:
    if not log.steps_path.exists():
        return None
    found: str | None = None
    for line in log.steps_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("kind") != "router":
            continue
        data = entry.get("data") or {}
        if isinstance(data, dict) and data.get("difficulty"):
            found = str(data["difficulty"]).strip().lower()
    return found


def sanitize_actions(raw: list[dict]) -> list[dict]:
    """Keep replay-safe actions; drop screenshots; normalize wait."""
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        atype = str(item.get("type") or "").strip()
        if not atype or atype in _SKIP_TYPES:
            continue
        action = {k: v for k, v in item.items() if v is not None}
        if atype == "wait" and "ms" not in action:
            action["ms"] = 2000
        out.append(_jsonable(action))
    return out


def _unstable_count(actions: list[dict]) -> int:
    return sum(1 for a in actions if str(a.get("type")) in _UNSTABLE)


def _stable_only(actions: list[dict]) -> list[dict]:
    return [a for a in actions if str(a.get("type")) in _STABLE]


def should_skip_record(
    task: str,
    *,
    difficulty: str | None,
    actions: list[dict],
) -> str | None:
    """
    Easy = router said easy (or unset) and the run is not a CAD/checkout keyword.
    Short medium = router said medium and the *replayable* spine (keypress/type/wait)
    has at most 12 steps.

    Clicks/drags are dropped from the saved trace; they do not fail recording if
    a keyboard spine remains (YouTube search is mostly clicks + a few keypresses).
    """
    if _HARD_TASK.search(task or ""):
        return "hard-task keywords"
    if difficulty == "hard":
        return "router=hard"
    cleaned = sanitize_actions(actions)
    stable = _stable_only(cleaned)
    if len(stable) < 2:
        return "not enough keypress/type/wait actions"
    if len(stable) > TRACE_MAX_ACTIONS:
        return "too many actions"
    if difficulty == "medium" and len(stable) > 12:
        return "medium run too long"
    dropped = _unstable_count(cleaned)
    if dropped:
        print(
            f"[trace] dropping {dropped} click/drag/scroll action(s); " f"keeping {len(stable)} keypress/type/wait",
            flush=True,
        )
    return None


def _extract_urls(text: str) -> list[str]:
    found = [m.group(0).rstrip(".,);") for m in _URL_RE.finditer(text or "")]
    # Drop bare words that look like versions (e.g. "v0.1").
    return [u for u in found if "." in u and not re.fullmatch(r"v?\d+(\.\d+)+", u)]


def parameterize_actions(task: str, actions: list[dict]) -> tuple[list[dict], list[str]]:
    """Replace typed values that came from the task with {{url}} / {{query}}."""
    urls = _extract_urls(task)
    quoted = re.findall(r"[\"']([^\"']{2,})[\"']", task or "")
    candidates: list[tuple[str, str]] = []
    for url in urls:
        candidates.append(("url", url))
    for q in quoted:
        if q not in urls:
            candidates.append(("query", q))

    used: list[str] = []
    out: list[dict] = []
    for action in actions:
        if str(action.get("type")) != "type":
            out.append(action)
            continue
        text = str(action.get("text") or "")
        if _APP_TYPE.match(text.strip()):
            out.append(action)
            continue
        replaced = False
        for name, value in candidates:
            if value and value.lower() in text.lower():
                if name not in used:
                    used.append(name)
                new = dict(action)
                # Preserve surrounding text if any.
                pattern = re.compile(re.escape(value), re.I)
                new["text"] = pattern.sub("{{" + name + "}}", text, count=1)
                out.append(new)
                replaced = True
                break
        if not replaced:
            # Typed blob equals leftover task content (no URL) → {{query}}.
            leftover = _norm(task)
            for url in urls:
                leftover = leftover.replace(_norm(url), " ")
            leftover = re.sub(r"\s+", " ", leftover).strip()
            typed_norm = _norm(text)
            if typed_norm and len(typed_norm) >= 4 and typed_norm in leftover and not _APP_TYPE.match(text.strip()):
                if "query" not in used:
                    used.append("query")
                new = dict(action)
                new["text"] = "{{query}}"
                out.append(new)
            else:
                out.append(action)
    return out, used


def match_phrases_for(task: str, param_values: list[str]) -> list[str]:
    stripped = _norm(task)
    for value in param_values:
        stripped = stripped.replace(_norm(value), " ")
    stripped = re.sub(r"\s+", " ", stripped).strip()
    words = content_words(stripped)
    seen: set[str] = set()
    out: list[str] = []
    for w in words:
        if w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out


def infer_verify(actions: list[dict]) -> dict:
    for action in actions:
        if str(action.get("type")) != "type":
            continue
        text = str(action.get("text") or "").strip()
        if "{{" in text:
            continue
        if _APP_TYPE.match(text):
            name = "Google Chrome" if text.lower() in {"chrome", "google chrome"} else text
            return {"ax_app": name}
    joined = " ".join(str(a.get("text") or "") for a in actions if str(a.get("type")) == "type").lower()
    if "chrome" in joined:
        return {"ax_app": "Google Chrome"}
    return {}


def propose_trace(task: str, log: TaskLog) -> Trace | None:
    difficulty = logged_difficulty(log)
    raw = collect_logged_actions(log)
    reason = should_skip_record(task, difficulty=difficulty, actions=raw)
    if reason:
        print(f"[trace] skip record ({reason})", flush=True)
        return None
    stable = _stable_only(sanitize_actions(raw))
    param_values = _extract_urls(task) + re.findall(r"[\"']([^\"']{2,})[\"']", task or "")
    actions, params = parameterize_actions(task, stable)
    match = match_phrases_for(task, param_values)
    if not match:
        return None
    name = _slugify(" ".join(content_words(task, tuple(param_values))) or "trace")
    return Trace(
        name=name,
        match=match,
        params=params,
        actions=actions,
        verify=infer_verify(stable),
        source_task=task,
        difficulty=difficulty or "easy",
    )


def save_trace(trace: Trace, traces_dir: Path | None = None) -> Path:
    root = traces_dir or TRACES_DIR
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{trace.name}.json"
    path.write_text(json.dumps(trace.to_dict(), indent=2) + "\n", encoding="utf-8")
    print(f"[trace] saved {path.name} ({len(trace.actions)} actions)", flush=True)
    return path


def load_traces(traces_dir: Path | None = None) -> list[Trace]:
    root = traces_dir or TRACES_DIR
    if not root.is_dir():
        return []
    traces: list[Trace] = []
    for path in sorted(root.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                traces.append(Trace.from_dict(data))
        except (OSError, json.JSONDecodeError) as e:
            print(f"[trace] skip {path.name}: {e}", flush=True)
    return traces


def _phrase_in(utterance: str, phrase: str) -> bool:
    u = _norm(utterance)
    p = _norm(phrase)
    if not p:
        return False
    if p in u:
        return True
    return all(w in u.split() or w in u for w in p.split() if len(w) > 2)


def score_trace(trace: Trace, utterance: str) -> float:
    if not trace.match or not trace.actions:
        return 0.0
    hits = sum(1 for p in trace.match if _phrase_in(utterance, p))
    if hits == 0:
        return 0.0
    return hits / float(len(trace.match))


def bind_params(trace: Trace, utterance: str) -> dict[str, str] | None:
    values: dict[str, str] = {}
    urls = _extract_urls(utterance)
    leftover = _norm(utterance)
    for phrase in trace.match:
        leftover = leftover.replace(_norm(phrase), " ")
    leftover = re.sub(r"\s+", " ", leftover).strip()
    for name in trace.params:
        if name == "url":
            if urls:
                values[name] = urls[0]
            elif leftover:
                values[name] = leftover
            else:
                return None
        elif name == "query":
            if leftover:
                values[name] = leftover
            elif urls:
                values[name] = urls[0]
            else:
                return None
        else:
            if leftover:
                values[name] = leftover
            else:
                return None
    return values


def bind_actions(trace: Trace, params: dict[str, str]) -> list[dict]:
    out: list[dict] = []
    for action in trace.actions:
        item = dict(action)
        text = item.get("text")
        if isinstance(text, str):
            for key, value in params.items():
                text = text.replace("{{" + key + "}}", value)
            item["text"] = text
        out.append(item)
    return out


def find_matching_trace(
    utterance: str,
    traces: list[Trace] | None = None,
    *,
    min_score: float = 1.0,
) -> tuple[Trace, dict[str, str]] | None:
    traces = load_traces() if traces is None else traces
    best: tuple[float, int, Trace, dict[str, str]] | None = None
    for trace in traces:
        score = score_trace(trace, utterance)
        if score < min_score:
            continue
        params = bind_params(trace, utterance)
        if params is None:
            continue
        key = (score, len(trace.match), trace, params)
        if best is None or (key[0], key[1]) > (best[0], best[1]):
            best = key
    if best is None:
        return None
    return best[2], best[3]


def frontmost_app_name() -> str | None:
    try:
        from accessibility import frontmost_app_name as _name

        return _name()
    except Exception:
        return None


def verify_trace(trace: Trace) -> bool:
    want = str((trace.verify or {}).get("ax_app") or "").strip()
    if not want:
        return True
    got = frontmost_app_name() or ""
    if not got:
        print("[trace] verify skipped (no frontmost app name)", flush=True)
        return True
    ok = want.lower() in got.lower() or got.lower() in want.lower()
    print(f"[trace] verify ax_app={want!r} frontmost={got!r} ok={ok}", flush=True)
    return ok


def _should_stop_replay() -> bool:
    try:
        from app_status import quit_requested

        if quit_requested():
            return True
    except Exception:
        pass
    try:
        from wake import get_persistent_wake

        mon = get_persistent_wake()
        if mon is not None and mon.woken.is_set():
            return True
    except Exception:
        pass
    return False


def replay_actions(actions: list[dict], *, desktop=None) -> None:
    """Run bound actions. Raises ReplayInterrupted on wake/quit."""
    from actions import ActionStopped, DesktopController

    ctl = desktop or DesktopController()
    try:
        ctl.run_actions(actions, should_stop=_should_stop_replay)
    except ActionStopped as e:
        raise ReplayInterrupted(str(e)) from e


def maybe_save_trace(log: TaskLog, task: str) -> Path | None:
    if not TRACE_RECORD:
        return None
    trace = propose_trace(task, log)
    if trace is None:
        return None
    return save_trace(trace)


def try_replay(task: str, *, desktop=None, traces_dir: Path | None = None) -> str | None:
    """
    If a saved trace matches `task`, replay it.

    Returns a status string on success, None to fall through to the CU loop.
    """
    if not TRACE_REPLAY:
        return None
    traces = load_traces(traces_dir)
    hit = find_matching_trace(task, traces)
    if hit is None:
        return None
    trace, params = hit
    print(
        f"[trace] replay {trace.name} params={params}",
        flush=True,
    )
    actions = bind_actions(trace, params)
    try:
        replay_actions(actions, desktop=desktop)
    except ReplayInterrupted:
        print("[trace] interrupted — falling back to computer-use", flush=True)
        return None
    except Exception as e:
        print(f"[trace] replay failed ({e}) — falling back", flush=True)
        return None
    if not verify_trace(trace):
        print("[trace] verify failed — falling back to computer-use", flush=True)
        return None
    return f"completed\nResult:\nReplayed saved trace {trace.name}."
