"""Passive desktop observer daemon (``cua observe``).

Watches the user's own mouse activity. Logs cheap metadata (app, window,
URL, event kind). Captures a screenshot when the session ends (app/URL
change) or after OBSERVE_IDLE_SECONDS of idle, on the display that holds
the focused window. Accumulates that into a window and only then extracts
a draft (default 10 minutes). Does not click, type, or steal focus. Pauses
while a computer-use agent is driving the pointer.
"""

from __future__ import annotations

from envfile import load_dotenv

load_dotenv()

import base64
import json
import os
import re
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = Path(os.environ.get("AGENT_RUNTIME_DIR") or ROOT / ".runtime")
OBSERVE_DIR = RUNTIME_DIR / "observe"
PROPOSED_DIR = OBSERVE_DIR / "proposed"
ACCEPTED_DIR = OBSERVE_DIR / "accepted"
REJECTED_DIR = OBSERVE_DIR / "rejected"
SKIPPED_DIR = OBSERVE_DIR / "skipped"
PID_PATH = RUNTIME_DIR / "observe.pid"
LOG_PATH = ROOT / "logs" / "observe.log"
EVENTS_LOG = OBSERVE_DIR / "events.jsonl"

IDLE_SECONDS = float(os.environ.get("OBSERVE_IDLE_SECONDS", "3"))
DRAFT_SECONDS = float(os.environ.get("OBSERVE_DRAFT_SECONDS", "600"))
SCROLL_DEBOUNCE = float(os.environ.get("OBSERVE_SCROLL_DEBOUNCE", "0.25"))
MAX_SHOTS_PER_HOUR = int(os.environ.get("OBSERVE_MAX_SHOTS_PER_HOUR", "40"))
SHOT_MAX_WIDTH = int(os.environ.get("OBSERVE_SHOT_WIDTH", "1024"))
EXTRACT_MODEL = (
    os.environ.get("OBSERVE_EXTRACT_MODEL")
    or os.environ.get("MEMORY_EXTRACT_MODEL")
    or os.environ.get("EVAL_MODEL")
    or os.environ.get("ORCHESTRATOR_MODEL")
    or "gpt-5-mini"
).strip() or "gpt-5-mini"

_EXCLUDE_APPS = {
    "1password",
    "1password for safari",
    "bitwarden",
    "lastpass",
    "keychain access",
    "wallet",
    "loginwindow",
    "securityagent",
    "screencapture",
}

_BROWSER_APPS = {
    "google chrome",
    "chromium",
    "brave browser",
    "microsoft edge",
    "safari",
}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def observe_enabled() -> bool:
    return os.environ.get("OBSERVE", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def exclude_app(name: str) -> bool:
    return (name or "").strip().lower() in _EXCLUDE_APPS


def computer_use_active() -> bool:
    """True while a computer-use job owns the pointer."""
    try:
        from app_status import active_agents, read_status

        if active_agents():
            return True
        return (read_status().get("state") or "") == "agent"
    except Exception:
        return False


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _slug(text: str, max_len: int = 32) -> str:
    slug = _SLUG_RE.sub("-", (text or "").strip().lower()).strip("-")
    return (slug[:max_len] or "session").rstrip("-")


def _unique_session_dir(root: Path, app: str) -> Path:
    stamp = _stamp()
    slug = _slug(app)
    folder = root / f"{stamp}_{slug}"
    n = 2
    while folder.exists():
        folder = root / f"{stamp}_{slug}_{n}"
        n += 1
    return folder


@dataclass
class Focus:
    app: str = ""
    title: str = ""
    url: str = ""

    def key(self) -> tuple[str, str, str]:
        return (self.app.strip().lower(), self.title.strip(), self.url.strip())

    def as_dict(self) -> dict[str, str]:
        return {"app": self.app, "title": self.title, "url": self.url}


@dataclass
class SessionBuffer:
    focus: Focus = field(default_factory=Focus)
    events: list[dict[str, Any]] = field(default_factory=list)
    started_at: float = 0.0
    last_event_at: float = 0.0
    last_scroll_at: float = 0.0

    def idle_seconds(self, now: float | None = None) -> float:
        if not self.events:
            return 0.0
        return max(0.0, (now if now is not None else time.monotonic()) - self.last_event_at)

    def should_rotate(self, focus: Focus) -> bool:
        if not self.events:
            return False
        return focus.key() != self.focus.key()

    def note(self, kind: str, focus: Focus, *, now: float | None = None) -> None:
        ts = now if now is not None else time.monotonic()
        if kind == "scroll":
            if self.last_scroll_at and (ts - self.last_scroll_at) < SCROLL_DEBOUNCE:
                self.last_event_at = ts
                self.last_scroll_at = ts
                return
            self.last_scroll_at = ts
        if not self.events:
            self.started_at = ts
            self.focus = focus
        self.last_event_at = ts
        self.events.append(
            {
                "t": datetime.now(timezone.utc).isoformat(),
                "kind": kind,
                "app": focus.app,
                "title": focus.title,
                "url": focus.url,
            }
        )

    def take(self) -> dict[str, Any] | None:
        if not self.events:
            return None
        payload = {
            "focus": self.focus.as_dict(),
            "started_at": self.started_at,
            "ended_at": self.last_event_at,
            "events": list(self.events),
        }
        self.events.clear()
        self.started_at = 0.0
        self.last_event_at = 0.0
        self.last_scroll_at = 0.0
        self.focus = Focus()
        return payload


@dataclass
class WindowBuffer:
    """Accumulates closed sessions until OBSERVE_DRAFT_SECONDS have elapsed."""

    started_at: float = 0.0
    segments: list[dict[str, Any]] = field(default_factory=list)
    pngs: list[bytes] = field(default_factory=list)

    def empty(self) -> bool:
        return not self.segments

    def age(self, now: float | None = None) -> float:
        if not self.started_at:
            return 0.0
        return max(0.0, (now if now is not None else time.monotonic()) - self.started_at)

    def add(self, segment: dict[str, Any], png: bytes | None = None) -> None:
        if not self.started_at:
            self.started_at = float(segment.get("started_at") or time.monotonic())
        self.segments.append(segment)
        if png:
            self.pngs.append(png)

    def take(self) -> dict[str, Any] | None:
        if not self.segments:
            return None
        payload = {
            "started_at": self.started_at,
            "segments": list(self.segments),
            "pngs": list(self.pngs),
        }
        self.segments.clear()
        self.pngs.clear()
        self.started_at = 0.0
        return payload


_EXTRACT_PROMPT = """You watch a passive log of what a person did on their Mac (not an agent).
Extract durable memories and optional UI playbooks.

Memories: standing facts the assistant should recall later (preferred apps,
accounts that are not passwords, repo names, usual workflows).

Skills: only if the session shows a repeatable UI procedure the computer-use
agent could follow with menus, hotkeys, or named buttons — never click
coordinates, never pixel positions.

Do NOT save:
- Passwords, API keys, OTPs, tokens, payment details
- One-off clicks, scrolling, or "opened Chrome"
- Hardware telemetry (online/offline, last ping)
- Anything already in existing memories unless this session updates it
- Playbooks that only work as raw mouse coordinates

Existing memories:
<<<CATALOG>>>

Observation window (~10 minutes of desktop activity: apps, windows, URLs, event kinds):
<<<SESSION>>>

Respond with JSON only (no markdown fences):
{"memories": [{"kind": "personal" or "app", "name": "short-slug", "text": "bullets"}],
 "skills": [{"name": "hyphen-slug", "description": "one line", "body": "## Steps\\n..."}]}
If nothing is worth saving, return {"memories": [], "skills": []}.
"""


def parse_observe_extract(payload: Any) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    from memory import parse_extracted_memory_items
    from skills import sanitize_skill_name

    if not isinstance(payload, dict):
        return [], []
    memories = parse_extracted_memory_items({"items": payload.get("memories") or []})
    skills: list[dict[str, str]] = []
    raw = payload.get("skills") or []
    if not isinstance(raw, list):
        return memories, skills
    for row in raw:
        if not isinstance(row, dict):
            continue
        try:
            name = sanitize_skill_name(str(row.get("name") or ""))
        except ValueError:
            continue
        description = " ".join(str(row.get("description") or "").split()).strip()
        body = str(row.get("body") or "").strip()
        if not description or not body:
            continue
        if "click" in body.lower() and re.search(r"\b\d{2,}\s*,\s*\d{2,}\b", body):
            continue
        skills.append({"name": name, "description": description, "body": body})
    return memories, skills


def list_proposed(*, root: Path | None = None, include_empty: bool = False) -> list[Path]:
    base = root or PROPOSED_DIR
    if not base.is_dir():
        return []
    out: list[Path] = []
    for path in sorted(base.iterdir()):
        if not path.is_dir() or not (path / "draft.json").is_file():
            continue
        if not include_empty:
            try:
                data = load_draft(path)
            except (OSError, json.JSONDecodeError):
                continue
            if not (data.get("memories") or data.get("skills")):
                continue
        out.append(path)
    return out


def load_draft(path: Path) -> dict[str, Any]:
    return json.loads((path / "draft.json").read_text(encoding="utf-8"))


def save_draft(path: Path, data: dict[str, Any]) -> None:
    (path / "draft.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _preview_line(text: str, width: int = 88) -> str:
    first = " ".join((text or "").split())
    if len(first) <= width:
        return first
    return first[: width - 1] + "…"


def format_draft_listing(path: Path, data: dict[str, Any] | None = None) -> str:
    data = data if data is not None else load_draft(path)
    focus = data.get("focus") or {}
    lines = [
        f"{path.name}  {focus.get('app') or '?'}  "
        f"memories={len(data.get('memories') or [])} "
        f"skills={len(data.get('skills') or [])}"
    ]
    for i, item in enumerate(data.get("memories") or [], start=1):
        kind = str(item.get("kind") or "app")
        name = str(item.get("name") or "?")
        lines.append(f"  m{i}  {kind}/{name}")
        preview = _preview_line(str(item.get("text") or ""))
        if preview:
            lines.append(f"      {preview}")
    for i, item in enumerate(data.get("skills") or [], start=1):
        name = str(item.get("name") or "?")
        lines.append(f"  s{i}  {name}")
        preview = _preview_line(str(item.get("description") or item.get("body") or ""))
        if preview:
            lines.append(f"      {preview}")
    return "\n".join(lines)


_ITEM_REF_RE = re.compile(r"^([ms])(\d+)$", re.I)


def resolve_item_selection(
    data: dict[str, Any],
    *,
    items: list[str] | None = None,
    memories: list[str] | None = None,
    skills: list[str] | None = None,
) -> tuple[set[int], set[int]]:
    """Return 0-based indexes of memories and skills to keep/write.

    Empty selectors mean every item. Indexes are ``m1`` / ``s2`` (1-based).
    Names match ``--memory`` / ``--skill`` or leftover args.
    """
    mems = list(data.get("memories") or [])
    sks = list(data.get("skills") or [])
    refs = [str(x).strip() for x in (items or []) if str(x).strip()]
    mem_names = [str(x).strip() for x in (memories or []) if str(x).strip()]
    skill_names = [str(x).strip() for x in (skills or []) if str(x).strip()]
    if not refs and not mem_names and not skill_names:
        return set(range(len(mems))), set(range(len(sks)))

    sel_m: set[int] = set()
    sel_s: set[int] = set()

    def add_named(kind: str, name: str) -> None:
        rows = mems if kind == "memory" else sks
        target = sel_m if kind == "memory" else sel_s
        exact = [i for i, row in enumerate(rows) if str(row.get("name") or "") == name]
        hits = exact or [
            i
            for i, row in enumerate(rows)
            if str(row.get("name") or "").startswith(name)
        ]
        label = "memory" if kind == "memory" else "skill"
        if not hits:
            raise ValueError(f"No {label} named {name!r}")
        if len(hits) > 1:
            raise ValueError(f"Ambiguous {label} name {name!r}")
        target.add(hits[0])

    for ref in refs:
        match = _ITEM_REF_RE.fullmatch(ref)
        if match:
            kind, num = match.group(1).lower(), int(match.group(2))
            idx = num - 1
            if kind == "m":
                if not (0 <= idx < len(mems)):
                    raise ValueError(f"No memory {ref}")
                sel_m.add(idx)
            else:
                if not (0 <= idx < len(sks)):
                    raise ValueError(f"No skill {ref}")
                sel_s.add(idx)
            continue
        mem_hit = any(str(row.get("name") or "") == ref or str(row.get("name") or "").startswith(ref) for row in mems)
        skill_hit = any(str(row.get("name") or "") == ref or str(row.get("name") or "").startswith(ref) for row in sks)
        if mem_hit and not skill_hit:
            add_named("memory", ref)
        elif skill_hit and not mem_hit:
            add_named("skill", ref)
        elif mem_hit and skill_hit:
            raise ValueError(f"{ref!r} matches both a memory and a skill; use mN/sN")
        else:
            raise ValueError(f"No memory or skill named {ref!r}")

    for name in mem_names:
        add_named("memory", name)
    for name in skill_names:
        add_named("skill", name)
    if not sel_m and not sel_s:
        raise ValueError("No matching memories or skills")
    return sel_m, sel_s


def _write_memory_item(
    item: dict[str, Any],
    *,
    memory_dir: Path | None = None,
) -> str:
    from memory import save_memory

    kind = str(item.get("kind") or "app")
    name = str(item.get("name") or "").strip()
    text = str(item.get("text") or "").strip()
    if not name or not text:
        return ""
    dest = save_memory(kind, name, text, mode="append", memory_dir=memory_dir)
    return str(dest)


def _write_skill_item(
    item: dict[str, Any],
    *,
    skills_dir: Path | None = None,
) -> str:
    from skills import write_skill

    name = str(item.get("name") or "").strip()
    description = str(item.get("description") or "").strip()
    body = str(item.get("body") or "").strip()
    if not name or not description or not body:
        return ""
    try:
        dest = write_skill(
            name,
            description,
            body,
            skills_dir=skills_dir,
            overwrite=False,
        )
    except FileExistsError:
        return f"skipped skill {name} (already exists)"
    return str(dest)


def accept_draft(
    path: Path,
    *,
    memory_dir: Path | None = None,
    skills_dir: Path | None = None,
    dest_root: Path | None = None,
    items: list[str] | None = None,
    memories: list[str] | None = None,
    skills: list[str] | None = None,
) -> list[str]:
    """Merge selected draft items into memory/ and skills/. Returns written paths.

    With no selectors, every memory and skill is accepted. Remaining items stay
    in the proposed folder; an empty draft is archived.
    """
    data = load_draft(path)
    sel_m, sel_s = resolve_item_selection(
        data, items=items, memories=memories, skills=skills
    )
    mems = list(data.get("memories") or [])
    sks = list(data.get("skills") or [])
    written: list[str] = []
    for i in sorted(sel_m):
        line = _write_memory_item(mems[i], memory_dir=memory_dir)
        if line:
            written.append(line)
    for i in sorted(sel_s):
        line = _write_skill_item(sks[i], skills_dir=skills_dir)
        if line:
            written.append(line)
    remaining_mem = [row for i, row in enumerate(mems) if i not in sel_m]
    remaining_sk = [row for i, row in enumerate(sks) if i not in sel_s]
    if remaining_mem or remaining_sk:
        data["memories"] = remaining_mem
        data["skills"] = remaining_sk
        data["status"] = "proposed"
        save_draft(path, data)
    else:
        _archive_draft(path, dest_root or ACCEPTED_DIR, status="accepted")
    return written


def reject_draft(
    path: Path,
    *,
    dest_root: Path | None = None,
    items: list[str] | None = None,
    memories: list[str] | None = None,
    skills: list[str] | None = None,
) -> None:
    data = load_draft(path)
    selectors = bool(items or memories or skills)
    if not selectors:
        _archive_draft(path, dest_root or REJECTED_DIR, status="rejected")
        return
    sel_m, sel_s = resolve_item_selection(
        data, items=items, memories=memories, skills=skills
    )
    mems = list(data.get("memories") or [])
    sks = list(data.get("skills") or [])
    remaining_mem = [row for i, row in enumerate(mems) if i not in sel_m]
    remaining_sk = [row for i, row in enumerate(sks) if i not in sel_s]
    if remaining_mem or remaining_sk:
        data["memories"] = remaining_mem
        data["skills"] = remaining_sk
        save_draft(path, data)
        return
    _archive_draft(path, dest_root or REJECTED_DIR, status="rejected")


def _archive_draft(path: Path, dest_root: Path, *, status: str) -> None:
    dest_root.mkdir(parents=True, exist_ok=True)
    target = dest_root / path.name
    if target.exists():
        target = dest_root / f"{path.name}-{int(time.time())}"
    path.rename(target)
    draft = target / "draft.json"
    if draft.is_file():
        try:
            data = json.loads(draft.read_text(encoding="utf-8"))
            data["status"] = status
            draft.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            pass


def _pid_alive(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def running_pid() -> int | None:
    try:
        raw = PID_PATH.read_text(encoding="utf-8").strip()
        pid = int(raw)
    except (OSError, ValueError):
        return None
    if _pid_alive(pid):
        return pid
    try:
        PID_PATH.unlink(missing_ok=True)
    except OSError:
        pass
    return None


def cmd_start() -> int:
    pid = running_pid()
    if pid is not None:
        print(f"observe is already running (pid {pid})")
        return 0
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    OBSERVE_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("PYTHONPATH", str(ROOT))
    import subprocess

    log_fh = open(LOG_PATH, "a", encoding="utf-8")
    try:
        log_fh.write(f"\n--- observe start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        log_fh.flush()
        proc = subprocess.Popen(
            [_python(), str(ROOT / "observe.py")],
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )
    finally:
        log_fh.close()
    time.sleep(0.4)
    if proc.poll() is not None:
        print(f"observe failed to start (exit {proc.returncode}). See {LOG_PATH}", file=sys.stderr)
        return 1
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(f"{proc.pid}\n", encoding="utf-8")
    print(f"observe started (pid {proc.pid})")
    print(f"logs: {LOG_PATH}")
    print(f"drafts: {PROPOSED_DIR}")
    return 0


def cmd_stop() -> int:
    pid = running_pid()
    if pid is None:
        print("observe is not running")
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            break
        time.sleep(0.15)
    if _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        time.sleep(0.2)
    try:
        PID_PATH.unlink(missing_ok=True)
    except OSError:
        pass
    print(f"observe stopped (pid {pid})")
    return 0


def cmd_status() -> int:
    pid = running_pid()
    drafts = list_proposed()
    if pid is None:
        print("observe is not running")
    else:
        print(f"observe is running (pid {pid})")
    print(f"drafts: {len(drafts)} in {PROPOSED_DIR}")
    return 0 if pid is not None else 1


def cmd_list() -> int:
    drafts = list_proposed()
    if not drafts:
        print("No proposed drafts.")
        return 0
    for path in drafts:
        print(format_draft_listing(path))
        print()
    print("Accept items:  cua observe accept <id> m1 s2")
    print("Accept names:  cua observe accept <id> --memory NAME --skill NAME")
    print("Accept all:    cua observe accept <id>   or   cua observe accept --all")
    print("Reject all:    cua observe reject --all")
    return 0


def _find_drafts(name: str | None, drafts: list[Path]) -> list[Path]:
    if not name:
        return drafts
    return [p for p in drafts if p.name == name or p.name.startswith(name)]


def cmd_accept(
    *,
    name: str | None = None,
    all_drafts: bool = False,
    items: list[str] | None = None,
    memories: list[str] | None = None,
    skills: list[str] | None = None,
) -> int:
    drafts = list_proposed()
    if not drafts:
        print("No proposed drafts.")
        return 0
    selectors = bool(items or memories or skills)
    if all_drafts and selectors:
        print("Pass a draft id to accept individual items (not --all).", file=sys.stderr)
        return 2
    if all_drafts:
        chosen = drafts
    elif name:
        chosen = _find_drafts(name, drafts)
        if not chosen:
            print(f"No draft matching {name!r}. Try: cua observe list", file=sys.stderr)
            return 1
    elif len(drafts) == 1:
        chosen = drafts
    else:
        print("Multiple drafts; pass an id or --all. Current:")
        cmd_list()
        return 2
    if selectors and len(chosen) != 1:
        print("Pass one draft id when selecting individual items.", file=sys.stderr)
        return 2
    for path in chosen:
        try:
            written = accept_draft(
                path,
                items=items,
                memories=memories,
                skills=skills,
            )
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 1
        leftover = path.exists()
        print(f"{'accepted items from' if leftover else 'accepted'} {path.name}")
        for line in written:
            print(f"  {line}")
        if leftover:
            print("  remaining:")
            print(format_draft_listing(path))
    return 0


def cmd_reject(
    *,
    name: str | None = None,
    all_drafts: bool = False,
    items: list[str] | None = None,
    memories: list[str] | None = None,
    skills: list[str] | None = None,
) -> int:
    drafts = list_proposed()
    if not drafts:
        print("No proposed drafts.")
        return 0
    selectors = bool(items or memories or skills)
    if all_drafts and selectors:
        print("Pass a draft id to reject individual items (not --all).", file=sys.stderr)
        return 2
    if all_drafts:
        chosen = drafts
    elif name:
        chosen = _find_drafts(name, drafts)
        if not chosen:
            print(f"No draft matching {name!r}.", file=sys.stderr)
            return 1
    else:
        print("Pass a draft id or --all. Try: cua observe list", file=sys.stderr)
        return 2
    if selectors and len(chosen) != 1:
        print("Pass one draft id when selecting individual items.", file=sys.stderr)
        return 2
    for path in chosen:
        try:
            reject_draft(
                path,
                items=items,
                memories=memories,
                skills=skills,
            )
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 1
        leftover = path.exists()
        print(f"{'dropped items from' if leftover else 'rejected'} {path.name}")
        if leftover:
            print(format_draft_listing(path))
    return 0


def _python() -> str:
    venv = ROOT / ".venv" / "bin" / "python"
    if venv.is_file():
        return str(venv)
    return sys.executable


class Observer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._session = SessionBuffer()
        self._window = WindowBuffer()
        self._stop = threading.Event()
        self._shot_times: list[float] = []
        self._tab_cache: tuple[float, list[dict[str, Any]]] = (0.0, [])
        self._extract_lock = threading.Lock()
        self._shot_lock = threading.Lock()
        self._busy_flushed = False

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            self._close_session_locked(reason="shutdown")
            if not self._maybe_draft_locked():
                age = self._window.age()
                if not self._window.empty():
                    print(
                        f"[observe] stopping with {age / 60:.1f} min buffered; "
                        f"no draft until {DRAFT_SECONDS / 60:g} min",
                        flush=True,
                    )

    def handle_input(self, kind: str) -> None:
        if self._stop.is_set():
            return
        if computer_use_active():
            with self._lock:
                if not self._busy_flushed:
                    self._close_session_locked(reason="computer-use")
                    self._busy_flushed = True
                self._maybe_draft_locked()
            return
        self._busy_flushed = False
        focus = self._focus()
        with self._lock:
            if self._session.should_rotate(focus):
                self._close_session_locked(reason="focus-change")
            if exclude_app(focus.app):
                self._maybe_draft_locked()
                return
            self._session.note(kind, focus)
            if not self._window.started_at:
                self._window.started_at = self._session.started_at
            self._maybe_draft_locked()

    def tick_idle(self) -> None:
        if computer_use_active():
            with self._lock:
                if not self._busy_flushed:
                    self._close_session_locked(reason="computer-use")
                    self._busy_flushed = True
                self._maybe_draft_locked()
            return
        with self._lock:
            if self._session.events and self._session.idle_seconds() >= IDLE_SECONDS:
                self._close_session_locked(reason="idle")
            self._maybe_draft_locked()

    def _close_session_locked(self, *, reason: str) -> None:
        payload = self._session.take()
        if payload is None:
            return
        payload["reason"] = reason
        png = None
        app = str((payload.get("focus") or {}).get("app") or "")
        if self._allow_screenshot() and not exclude_app(app):
            png, monitor = self._take_screenshot(app)
            if png:
                with self._shot_lock:
                    self._shot_times.append(time.monotonic())
            if monitor:
                payload["monitor"] = {
                    "index": monitor.get("index"),
                    "name": monitor.get("name"),
                    "main": bool(monitor.get("main")),
                }
        _append_events_log(payload.get("events") or [])
        self._window.add(payload, png)

    def _maybe_draft_locked(self, now: float | None = None) -> bool:
        ts = now if now is not None else time.monotonic()
        if not self._window.started_at and self._session.started_at:
            self._window.started_at = self._session.started_at
        if not self._window.started_at:
            return False
        if self._window.age(ts) < DRAFT_SECONDS:
            return False
        self._close_session_locked(reason="window")
        payload = self._window.take()
        if payload is None:
            return False
        self._schedule_persist(payload, "window")
        return True

    def _take_screenshot(self, app: str = "") -> tuple[bytes | None, dict | None]:
        return _capture_focused_display(app)

    def _schedule_persist(self, payload: dict[str, Any], reason: str) -> None:
        threading.Thread(
            target=self._persist_and_extract,
            args=(payload, reason),
            name="observe-extract",
            daemon=True,
        ).start()

    def _focus(self) -> Focus:
        app = ""
        title = ""
        try:
            from accessibility import frontmost_app_name

            app = (frontmost_app_name() or "").strip()
        except Exception:
            pass
        title = _frontmost_window_title(app)
        url = ""
        if app.lower() in _BROWSER_APPS:
            url = self._active_tab_url(app)
        return Focus(app=app, title=title, url=url)

    def _active_tab_url(self, app: str) -> str:
        now = time.monotonic()
        cached_at, browsers = self._tab_cache
        if now - cached_at > 8:
            try:
                from displays import list_browser_tabs

                browsers = list_browser_tabs()
                self._tab_cache = (now, browsers)
            except Exception:
                browsers = []
        needle = app.lower()
        for browser in browsers:
            if needle not in str(browser.get("browser") or "").lower():
                continue
            for win in browser.get("windows") or []:
                for tab in win.get("tabs") or []:
                    if tab.get("active"):
                        return str(tab.get("url") or "").strip()
        return ""

    def _persist_and_extract(self, payload: dict[str, Any], reason: str) -> None:
        try:
            OBSERVE_DIR.mkdir(parents=True, exist_ok=True)
            PROPOSED_DIR.mkdir(parents=True, exist_ok=True)
            segments = list(payload.get("segments") or [])
            events: list[dict[str, Any]] = []
            for seg in segments:
                events.extend(seg.get("events") or [])
            last_focus = {}
            for seg in reversed(segments):
                if seg.get("focus"):
                    last_focus = seg["focus"]
                    break
            app = str(last_focus.get("app") or "window")
            folder = _unique_session_dir(PROPOSED_DIR, app)
            folder.mkdir(parents=True, exist_ok=True)
            pngs = list(payload.get("pngs") or [])
            meta_segments = []
            for i, seg in enumerate(segments):
                row = {k: v for k, v in seg.items() if k != "png"}
                row["screenshot"] = i < len(pngs)
                meta_segments.append(row)
            (folder / "session.json").write_text(
                json.dumps(
                    {
                        "reason": reason,
                        "focus": last_focus,
                        "segments": meta_segments,
                        "n_events": len(events),
                        "n_segments": len(segments),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            png = pngs[-1] if pngs else None
            if png:
                (folder / "screen.png").write_bytes(png)
            print(
                f"[observe] window {folder.name} reason={reason} "
                f"segments={len(segments)} events={len(events)} "
                f"shot={'yes' if png else 'no'}",
                flush=True,
            )
            self._extract(
                folder,
                {
                    "focus": last_focus,
                    "events": events,
                    "segments": meta_segments,
                },
                png,
            )
        except Exception as e:
            print(f"[observe] persist failed: {e}", flush=True)

    def _allow_screenshot(self) -> bool:
        with self._shot_lock:
            cutoff = time.monotonic() - 3600
            self._shot_times = [t for t in self._shot_times if t >= cutoff]
            return len(self._shot_times) < MAX_SHOTS_PER_HOUR

    def _extract(self, folder: Path, payload: dict[str, Any], png: bytes | None) -> None:
        with self._extract_lock:
            memories, skills = _run_extract(payload, png)
        draft = {
            "id": folder.name,
            "status": "proposed",
            "focus": payload.get("focus") or {},
            "n_events": len(payload.get("events") or []),
            "n_segments": len(payload.get("segments") or []),
            "screenshot": "screen.png" if png else None,
            "memories": memories,
            "skills": skills,
        }
        (folder / "draft.json").write_text(
            json.dumps(draft, indent=2) + "\n",
            encoding="utf-8",
        )
        if not memories and not skills:
            print(f"[observe] {folder.name}: nothing durable", flush=True)
            _archive_draft(folder, SKIPPED_DIR, status="empty")
            return
        print(
            f"[observe] draft {folder.name} " f"memories={len(memories)} skills={len(skills)}",
            flush=True,
        )


def _append_events_log(events: list[dict[str, Any]]) -> None:
    OBSERVE_DIR.mkdir(parents=True, exist_ok=True)
    with EVENTS_LOG.open("a", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def _frontmost_window_title(app: str) -> str:
    if not app:
        return ""
    try:
        from displays import _window_title, frontmost_window_info

        info = frontmost_window_info(app)
        return _window_title(info) if info else ""
    except Exception:
        return ""


def _downscale_png(data: bytes) -> bytes:
    try:
        import io

        from PIL import Image
    except Exception:
        return data
    try:
        img = Image.open(io.BytesIO(data))
        if img.width > SHOT_MAX_WIDTH:
            ratio = SHOT_MAX_WIDTH / img.width
            img = img.resize((SHOT_MAX_WIDTH, max(1, round(img.height * ratio))))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return data


def _capture_cg_display(display_id: int) -> bytes | None:
    if sys.platform != "darwin" or not display_id:
        return None
    try:
        from AppKit import NSBitmapImageRep
        from Quartz import CGDisplayCreateImage
    except Exception:
        return None
    try:
        from AppKit import NSBitmapImageFileTypePNG as png_type
    except ImportError:
        try:
            from AppKit import NSPNGFileType as png_type
        except ImportError:
            return None
    try:
        image = CGDisplayCreateImage(int(display_id))
        if image is None:
            return None
        rep = NSBitmapImageRep.alloc().initWithCGImage_(image)
        blob = rep.representationUsingType_properties_(png_type, None)
        if blob is None:
            return None
        return bytes(blob)
    except Exception as e:
        print(f"[observe] display capture failed: {e}", flush=True)
        return None


def _capture_primary_png() -> bytes | None:
    try:
        import io

        import pyautogui
        from PIL import Image
    except Exception:
        return None
    try:
        img = pyautogui.screenshot()
        if not isinstance(img, Image.Image):
            return None
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        print(f"[observe] screenshot failed: {e}", flush=True)
        return None


def _capture_focused_display(app: str) -> tuple[bytes | None, dict | None]:
    """Screenshot the monitor that holds ``app``'s focused window."""
    monitor = None
    try:
        from displays import monitor_for_app_window

        monitor = monitor_for_app_window(app)
    except Exception:
        monitor = None
    png = None
    display_id = (monitor or {}).get("display_id")
    if display_id:
        png = _capture_cg_display(int(display_id))
    if not png:
        png = _capture_primary_png()
    if png:
        png = _downscale_png(png)
    return png, monitor


def _capture_png_bytes(app: str = "") -> bytes | None:
    png, _monitor = _capture_focused_display(app)
    return png


def _capture_png(path: Path) -> bytes | None:
    data = _capture_png_bytes()
    if data:
        path.write_bytes(data)
    return data


def _run_extract(
    payload: dict[str, Any],
    png: bytes | None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    from memory import _parse_json_object, _response_output_text, format_memory_catalog

    session_blob = json.dumps(
        {
            "focus": payload.get("focus"),
            "segments": payload.get("segments") or [],
            "events": payload.get("events") or [],
        },
        indent=2,
    )[:24000]
    prompt = _EXTRACT_PROMPT.replace("<<<CATALOG>>>", format_memory_catalog()).replace("<<<SESSION>>>", session_blob)
    content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    if png:
        b64 = base64.b64encode(png).decode("ascii")
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{b64}",
                "detail": "low",
            }
        )
    try:
        from openai import OpenAI

        client = OpenAI()
        response = client.responses.create(
            model=EXTRACT_MODEL,
            input=[{"role": "user", "content": content}],
        )
        raw = _response_output_text(response)
        parsed = _parse_json_object(raw) or {}
        return parse_observe_extract(parsed)
    except Exception as e:
        print(f"[observe] extract failed: {e}", flush=True)
        return [], []


def _install_event_tap(observer: Observer) -> bool:
    if sys.platform != "darwin":
        return False
    try:
        from Quartz import (
            CFMachPortCreateRunLoopSource,
            CFRunLoopAddSource,
            CFRunLoopGetCurrent,
            CGEventMaskBit,
            CGEventTapCreate,
            CGEventTapEnable,
            kCFRunLoopCommonModes,
            kCGEventLeftMouseDown,
            kCGEventOtherMouseDown,
            kCGEventRightMouseDown,
            kCGEventScrollWheel,
            kCGEventTapOptionListenOnly,
            kCGHeadInsertEventTap,
            kCGSessionEventTap,
        )
    except Exception as e:
        print(f"[observe] Quartz unavailable ({e}); polling focus only", flush=True)
        return False

    def callback(_proxy, etype, event, _ref):
        try:
            if etype == kCGEventScrollWheel:
                observer.handle_input("scroll")
            else:
                observer.handle_input("click")
        except Exception:
            pass
        return event

    mask = (
        CGEventMaskBit(kCGEventLeftMouseDown)
        | CGEventMaskBit(kCGEventRightMouseDown)
        | CGEventMaskBit(kCGEventOtherMouseDown)
        | CGEventMaskBit(kCGEventScrollWheel)
    )
    tap = CGEventTapCreate(
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        kCGEventTapOptionListenOnly,
        mask,
        callback,
        None,
    )
    if tap is None:
        print(
            "[observe] event tap unavailable — grant Accessibility to this terminal, "
            "or continuing with app-switch polling only.",
            flush=True,
        )
        return False
    source = CFMachPortCreateRunLoopSource(None, tap, 0)
    CFRunLoopAddSource(CFRunLoopGetCurrent(), source, kCFRunLoopCommonModes)
    CGEventTapEnable(tap, True)
    print("[observe] listening for click/scroll (listen-only tap)", flush=True)
    return True


def _poll_loop(observer: Observer) -> None:
    last_key: tuple[str, str, str] | None = None
    while not observer._stop.is_set():
        focus = observer._focus()
        key = focus.key()
        if last_key is not None and key != last_key and not exclude_app(focus.app):
            observer.handle_input("app-switch")
        last_key = key
        observer.tick_idle()
        observer._stop.wait(0.4)


def run_observer() -> None:
    if not observe_enabled():
        print("[observe] disabled (OBSERVE=0)", flush=True)
        return
    OBSERVE_DIR.mkdir(parents=True, exist_ok=True)
    PROPOSED_DIR.mkdir(parents=True, exist_ok=True)
    observer = Observer()

    def handle_sig(_signum, _frame) -> None:
        observer.stop()
        try:
            from Quartz import CFRunLoopGetCurrent, CFRunLoopStop

            CFRunLoopStop(CFRunLoopGetCurrent())
        except Exception:
            pass

    signal.signal(signal.SIGTERM, handle_sig)
    signal.signal(signal.SIGINT, handle_sig)
    print(
        f"[observe] idle shot={IDLE_SECONDS:g}s draft={DRAFT_SECONDS / 60:g}min "
        f"shots/hour≤{MAX_SHOTS_PER_HOUR} drafts={PROPOSED_DIR}",
        flush=True,
    )

    idle = threading.Thread(target=_poll_loop, args=(observer,), name="observe-idle", daemon=True)
    idle.start()
    tapped = _install_event_tap(observer)
    if tapped:
        try:
            from Quartz import CFRunLoopRun

            CFRunLoopRun()
        except Exception as e:
            print(f"[observe] run loop ended: {e}", flush=True)
    else:
        while not observer._stop.is_set():
            observer._stop.wait(0.5)
    observer.stop()
    print("[observe] stopped", flush=True)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print("observe.py takes no args; use: cua observe start", file=sys.stderr)
        return 2
    run_observer()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
