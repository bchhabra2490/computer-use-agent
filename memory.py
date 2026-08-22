"""Personal, application, and screen memories stored under ``memory/``.

Kinds:
  - personal — facts about the user (name, preferences, accounts that are not
    app-specific)
  - app — per-application notes (usernames, UI quirks, usual workflows)
  - screen — screenshot + LLM description for later recall

After each orchestrator turn and computer-use run, user input plus LLM
steps are reviewed and durable facts (repos, songs, preferences) are
appended here automatically. A second background thread then condenses
those files to drop repetition.

Files: ``memory/personal/<slug>.md``, ``memory/apps/<slug>.md``,
``memory/screens/<slug>.md`` (+ matching ``.png`` for screen captures).
"""

from __future__ import annotations

import base64
import json
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MEMORY_DIR = Path(__file__).resolve().parent / "memory"
_MEMORY_WRITE_LOCK = threading.Lock()
_CONDENSE_STATE_LOCK = threading.Lock()
_condense_running = False
_condense_pending = False
MEMORY_VISION_MODEL = (
    os.environ.get("MEMORY_VISION_MODEL") or os.environ.get("ORCHESTRATOR_MODEL") or "gpt-4o-mini"
).strip() or "gpt-4o-mini"
MEMORY_EXTRACT_MODEL = (
    os.environ.get("MEMORY_EXTRACT_MODEL")
    or os.environ.get("EVAL_MODEL")
    or os.environ.get("ORCHESTRATOR_MODEL")
    or "gpt-5-mini"
).strip() or "gpt-5-mini"
MEMORY_CONDENSE_MODEL = (
    os.environ.get("MEMORY_CONDENSE_MODEL")
    or os.environ.get("MEMORY_EXTRACT_MODEL")
    or os.environ.get("EVAL_MODEL")
    or os.environ.get("ORCHESTRATOR_MODEL")
    or "gpt-5-mini"
).strip() or "gpt-5-mini"

_KIND_DIR = {
    "personal": "personal",
    "app": "apps",
    "apps": "apps",
    "application": "apps",
    "screen": "screens",
    "screens": "screens",
    "screenshot": "screens",
}
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class MemoryNote:
    kind: str  # personal | app | screen
    name: str
    path: Path
    text: str

    @property
    def rel(self) -> str:
        return f"{self.kind}/{self.name}.md"


def _root(memory_dir: Path | None) -> Path:
    return Path(memory_dir) if memory_dir is not None else MEMORY_DIR


def _canonical_kind(kind: str) -> str:
    key = (kind or "").strip().lower()
    if key not in _KIND_DIR:
        raise ValueError("Memory kind must be 'personal', 'app', or 'screen'.")
    folder = _KIND_DIR[key]
    if folder == "personal":
        return "personal"
    if folder == "apps":
        return "app"
    return "screen"


def _subdir(kind: str, memory_dir: Path | None = None) -> Path:
    canon = _canonical_kind(kind)
    folder = {"personal": "personal", "app": "apps", "screen": "screens"}[canon]
    return _root(memory_dir) / folder


def sanitize_memory_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    if not slug or not _SLUG_RE.match(slug):
        raise ValueError(f"Invalid memory name: {name!r}")
    if len(slug) > 64:
        raise ValueError(f"Memory name too long: {slug!r}")
    return slug


def ensure_memory_dirs(memory_dir: Path | None = None) -> Path:
    root = _root(memory_dir)
    (root / "personal").mkdir(parents=True, exist_ok=True)
    (root / "apps").mkdir(parents=True, exist_ok=True)
    (root / "screens").mkdir(parents=True, exist_ok=True)
    return root


def _is_live_layout_memory(kind: str, name: str) -> bool:
    """True for the auto-written per-monitor occupancy note (not user facts)."""
    try:
        return _canonical_kind(kind) == "app" and sanitize_memory_name(name) == "displays"
    except ValueError:
        return False


def _preview(text: str) -> str:
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
            return stripped[:120]
    return "(empty)"


def list_memories(
    kind: str = "all",
    *,
    memory_dir: Path | None = None,
) -> list[MemoryNote]:
    """List saved notes. ``kind`` is personal, app, or all."""
    ensure_memory_dirs(memory_dir)
    kinds: list[str]
    raw = (kind or "all").strip().lower()
    if raw in {"", "all", "*"}:
        kinds = ["personal", "app", "screen"]
    else:
        kinds = [_canonical_kind(raw)]

    notes: list[MemoryNote] = []
    for k in kinds:
        folder = _subdir(k, memory_dir)
        for path in sorted(folder.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            notes.append(MemoryNote(kind=k, name=path.stem, path=path, text=text))
    return notes


def read_memory(
    kind: str,
    name: str | None = None,
    *,
    memory_dir: Path | None = None,
) -> str:
    """
    Return markdown for one note, or all notes of that kind when ``name`` is empty.
    """
    ensure_memory_dirs(memory_dir)
    canon = _canonical_kind(kind)
    slug = (name or "").strip()
    if not slug:
        notes = list_memories(canon, memory_dir=memory_dir)
        if not notes:
            return f"No {canon} memories saved yet."
        parts = [f"# {n.rel}\n\n{n.text.strip()}" for n in notes]
        return "\n\n---\n\n".join(parts)

    slug = sanitize_memory_name(slug)
    path = _subdir(canon, memory_dir) / f"{slug}.md"
    if not path.is_file():
        available = ", ".join(n.name for n in list_memories(canon, memory_dir=memory_dir)) or "(none)"
        raise FileNotFoundError(f"No {canon} memory named {slug!r}. Available: {available}")
    return path.read_text(encoding="utf-8")


def save_memory(
    kind: str,
    name: str,
    text: str,
    *,
    mode: str = "append",
    memory_dir: Path | None = None,
    condense: bool = True,
) -> Path:
    """Create or update a memory file. ``mode`` is append (default) or replace."""
    ensure_memory_dirs(memory_dir)
    canon = _canonical_kind(kind)
    slug = sanitize_memory_name(name)
    body = (text or "").strip()
    if not body:
        raise ValueError("Memory text is empty.")

    how = (mode or "append").strip().lower()
    if how not in {"append", "replace"}:
        raise ValueError("Memory mode must be 'append' or 'replace'.")

    path = _subdir(canon, memory_dir) / f"{slug}.md"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    block = f"## {stamp}\n\n{body}\n"

    with _MEMORY_WRITE_LOCK:
        if how == "replace" or not path.exists():
            header = f"# {canon} / {slug}\n\n"
            path.write_text(header + block, encoding="utf-8")
        else:
            existing = path.read_text(encoding="utf-8").rstrip() + "\n\n"
            path.write_text(existing + block, encoding="utf-8")
    if condense:
        schedule_memory_condense(memory_dir=memory_dir)
    return path


def format_memory_catalog(*, memory_dir: Path | None = None) -> str:
    """Compact index for prompts (names + one-line preview, not full text)."""
    notes = [
        n
        for n in list_memories("all", memory_dir=memory_dir)
        if not _is_live_layout_memory(n.kind, n.name)
    ]
    if not notes:
        return "No memories saved yet. Use save_memory for facts, or " "save_screen_memory to snapshot the display."
    lines = [
        "Saved memories (contemplate whether these answer the user before ask_user; "
        "call read_memory for full text; save_memory / save_screen_memory to update):"
    ]
    for note in notes:
        lines.append(f"  - {note.rel}: {_preview(note.text)}")
    return "\n".join(lines)


def memory_extract_enabled() -> bool:
    return os.environ.get("MEMORY_EXTRACT", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


class TurnTrace:
    """User utterance plus each LLM step (replies, tool calls, results)."""

    def __init__(self, user_input: str = ""):
        self.user_input = (user_input or "").strip()
        self.steps: list[tuple[str, str]] = []

    def add(self, kind: str, text: str, *, max_len: int = 4000) -> None:
        body = (text or "").strip()
        if not body:
            return
        if len(body) > max_len:
            body = body[:max_len] + "\n… (truncated)"
        self.steps.append(((kind or "step").strip() or "step", body))

    def as_text(self, max_chars: int = 20_000) -> str:
        parts = [f"User input:\n{self.user_input or '(empty)'}"]
        for i, (kind, text) in enumerate(self.steps, start=1):
            parts.append(f"Step {i} [{kind}]:\n{text}")
        blob = "\n\n".join(parts)
        if len(blob) > max_chars:
            return blob[:max_chars] + "\n… (truncated)"
        return blob


_SECRET_TEXT_RE = re.compile(
    r"(?i)\b(password|passwd|api[_-]?key|secret|otp|one[- ]time(?: code)?)\b\s*[:=]"
    r"|sk-[A-Za-z0-9]{10,}"
    r"|ghp_[A-Za-z0-9]{10,}"
    r"|github_pat_[A-Za-z0-9_]{10,}"
)


def _text_looks_secret(text: str) -> bool:
    return bool(_SECRET_TEXT_RE.search(text or ""))


_VOLATILE_HARDWARE_MEMORY_RE = re.compile(
    r"(?is)\b("
    r"last\s+ping"
    r"|last\s+seen"
    r"|heartbeat"
    r"|memory\s+snapshot"
    r"|online\s*:\s*(true|false)"
    r"|offline"
    r"|uptime"
    r"|signal\s+strength"
    r"|battery\s*%"
    r"|temperature\s*[:=]"
    r"|humidity\s*[:=]"
    r")\b"
)


def _text_looks_volatile_hardware(text: str) -> bool:
    """True for transient hardware telemetry that should not become durable memory."""
    return bool(_VOLATILE_HARDWARE_MEMORY_RE.search(text or ""))


def _response_output_text(response: Any) -> str:
    text = _response_text(response)
    if text:
        return text
    return (getattr(response, "output_text", None) or "").strip()


def parse_extracted_memory_items(payload: Any) -> list[dict[str, str]]:
    """Normalize extractor JSON into ``{kind, name, text}`` rows."""
    if payload is None:
        return []
    raw: Any
    if isinstance(payload, list):
        raw = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("kind"), str) and payload.get("text"):
            raw = [payload]
        else:
            raw = payload.get("items") or payload.get("memories") or []
    else:
        return []
    if not isinstance(raw, list):
        return []

    items: list[dict[str, str]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("kind") or "").strip().lower()
        name = str(row.get("name") or "").strip()
        text = str(row.get("text") or "").strip()
        if kind not in {"personal", "app"} or not name or not text:
            continue
        if _is_live_layout_memory(kind, name):
            continue
        if _text_looks_secret(text):
            continue
        if _text_looks_volatile_hardware(text):
            continue
        items.append({"kind": kind, "name": name, "text": text})
    return items


def _parse_json_object(text: str) -> Any | None:
    blob = (text or "").strip()
    if not blob:
        return None
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", blob, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def apply_extracted_memory_items(
    items: list[dict[str, str]],
    *,
    memory_dir: Path | None = None,
) -> list[str]:
    """Append extracted facts. Returns relative paths that were written."""
    written: list[str] = []
    for item in items:
        if _is_live_layout_memory(item.get("kind", ""), item.get("name", "")):
            continue
        try:
            path = save_memory(
                item["kind"],
                item["name"],
                item["text"],
                mode="append",
                memory_dir=memory_dir,
                condense=False,
            )
        except (ValueError, OSError) as e:
            print(f"[memory] skip {item.get('kind')}/{item.get('name')}: {e}", flush=True)
            continue
        try:
            shown = str(path.relative_to(_root(memory_dir)))
        except ValueError:
            shown = path.name
        written.append(shown)
        print(f"[memory] extracted → {shown}", flush=True)
    if written:
        schedule_memory_condense(memory_dir=memory_dir)
    return written


_EXTRACT_PROMPT = """You extract durable memories from a completed voice-assistant run.

Save facts the assistant should recall on later tasks, for example:
- GitHub repos the user owns or asked about (owner/name, star count if known)
- Songs, artists, playlists, or YouTube videos that were played or requested
- App usernames, preferred apps, labels, issue-splitting choices, volume
- People, places, standing preferences, accounts (not passwords)

Do NOT save:
- Passwords, API keys, OTPs, tokens, or payment details
- One-off clicks, "opened Chrome", raw tool dumps, or the task itself with no fact
- Live window/monitor occupancy (that is stored automatically as app/displays)
- Hardware live telemetry/status snapshots (online/offline, last ping/last seen,
  heartbeat, battery/temperature/humidity point-in-time readings)
- Anything already in existing memories unless this run has a new or updated value

Existing memories (do not repeat unless updated):
<<<CATALOG>>>

Full run (user input, model replies, tool calls, tool results):
<<<TRANSCRIPT>>>

Respond with JSON only (no markdown fences):
{"items": [{"kind": "personal" or "app", "name": "short-slug", "text": "one or more bullets", "reason": "why"}]}

Use kind=app and a slug like github, youtube, hn, chrome when the fact is tied to an app.
Use kind=personal and name=profile for who the user is / standing preferences.
If nothing is worth saving, return {"items": []}.
"""


def _new_extract_client() -> Any:
    from openai import OpenAI

    return OpenAI()


def _extract_run_memories_impl(
    client: Any,
    *,
    user_input: str,
    transcript: str,
    memory_dir: Path | None = None,
) -> list[str]:
    catalog = format_memory_catalog(memory_dir=memory_dir)
    prompt = _EXTRACT_PROMPT.replace("<<<CATALOG>>>", catalog).replace("<<<TRANSCRIPT>>>", transcript)
    print("[memory] extracting facts from this run…", flush=True)
    try:
        response = client.responses.create(
            model=MEMORY_EXTRACT_MODEL,
            input=prompt,
        )
        raw = _response_output_text(response)
        payload = _parse_json_object(raw)
        items = parse_extracted_memory_items(payload)
        if not items:
            print("[memory] nothing durable to save", flush=True)
            return []
        return apply_extracted_memory_items(items, memory_dir=memory_dir)
    except Exception as e:
        print(f"[memory] extract failed: {e}", flush=True)
        return []


def maybe_extract_run_memories(
    client: Any | None = None,
    *,
    user_input: str,
    transcript: str,
    memory_dir: Path | None = None,
    background: bool = True,
) -> list[str]:
    """
    After a run, combine user input + LLM steps and append durable facts.

    By default this starts a daemon thread and returns immediately so the
    agent / orchestrator are not blocked on the extract LLM call. Pass
    ``background=False`` to run inline (tests). Failures are logged and
    do not raise.
    """
    if not memory_extract_enabled():
        return []
    user = (user_input or "").strip()
    blob = (transcript or "").strip()
    if not user and not blob:
        return []
    if not blob:
        blob = f"User input:\n{user}"

    if not background:
        if client is None:
            return []
        return _extract_run_memories_impl(
            client,
            user_input=user,
            transcript=blob,
            memory_dir=memory_dir,
        )

    def _work() -> None:
        try:
            worker_client = _new_extract_client()
            _extract_run_memories_impl(
                worker_client,
                user_input=user,
                transcript=blob,
                memory_dir=memory_dir,
            )
        except Exception as e:
            print(f"[memory] extract failed: {e}", flush=True)

    threading.Thread(target=_work, name="memory-extract", daemon=True).start()
    print("[memory] extracting facts in background…", flush=True)
    return []


def memory_condense_enabled() -> bool:
    return os.environ.get("MEMORY_CONDENSE", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _dated_heading_count(text: str) -> int:
    return sum(1 for line in (text or "").splitlines() if line.startswith("## "))


def notes_need_condense(notes: list[MemoryNote]) -> bool:
    """True when personal/app notes have stacked dated sections or are long."""
    for note in notes:
        if note.kind == "screen" or _is_live_layout_memory(note.kind, note.name):
            continue
        if _dated_heading_count(note.text) >= 2:
            return True
        if len(note.text) > 2500:
            return True
    return False


def parse_condensed_memory_files(payload: Any) -> list[dict[str, str]]:
    """Normalize condense JSON into ``{kind, name, text}`` rows."""
    if not isinstance(payload, dict):
        return []
    raw = payload.get("files") or payload.get("items") or []
    if not isinstance(raw, list):
        return []
    files: list[dict[str, str]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("kind") or "").strip().lower()
        name = str(row.get("name") or "").strip()
        text = str(row.get("text") or "").strip()
        if kind not in {"personal", "app"} or not name or not text:
            continue
        if _is_live_layout_memory(kind, name):
            continue
        if _text_looks_secret(text):
            continue
        files.append({"kind": kind, "name": name, "text": text})
    return files


def write_condensed_memory(
    kind: str,
    name: str,
    text: str,
    *,
    memory_dir: Path | None = None,
) -> Path:
    """Overwrite a note with compact markdown (no extra dated section)."""
    ensure_memory_dirs(memory_dir)
    canon = _canonical_kind(kind)
    slug = sanitize_memory_name(name)
    body = (text or "").strip()
    if not body:
        raise ValueError("Memory text is empty.")
    if not body.lstrip().startswith("#"):
        body = f"# {canon} / {slug}\n\n{body}"
    path = _subdir(canon, memory_dir) / f"{slug}.md"
    with _MEMORY_WRITE_LOCK:
        path.write_text(body.rstrip() + "\n", encoding="utf-8")
    return path


def apply_condensed_memory_files(
    files: list[dict[str, str]],
    *,
    memory_dir: Path | None = None,
) -> list[str]:
    written: list[str] = []
    for item in files:
        try:
            path = write_condensed_memory(
                item["kind"],
                item["name"],
                item["text"],
                memory_dir=memory_dir,
            )
        except (ValueError, OSError) as e:
            print(f"[memory] condense skip {item.get('kind')}/{item.get('name')}: {e}", flush=True)
            continue
        try:
            shown = str(path.relative_to(_root(memory_dir)))
        except ValueError:
            shown = path.name
        written.append(shown)
        print(f"[memory] condensed → {shown}", flush=True)
    return written


def _format_notes_for_condense(notes: list[MemoryNote], *, max_chars: int = 24_000) -> str:
    parts: list[str] = []
    used = 0
    for note in notes:
        if note.kind == "screen" or _is_live_layout_memory(note.kind, note.name):
            continue
        chunk = f"### {note.rel}\n{note.text.strip()}\n"
        if len(chunk) > 8000:
            chunk = chunk[:8000] + "\n… (truncated)\n"
        if used + len(chunk) > max_chars:
            parts.append("… (further files omitted)")
            break
        parts.append(chunk)
        used += len(chunk)
    return "\n".join(parts).strip() or "(none)"


_CONDENSE_PROMPT = """You condense voice-assistant memory files to save tokens.

Rules:
- Keep every distinct durable fact (prefs, usernames, repos, songs, issue/PR ids).
- Drop repeated bullets and restated dated sections.
- If preferences conflict (volume 40% vs 50%), keep the latest.
- Unique events stay once (do not list the same song or branch delete twice).
- Do not invent facts. Do not include passwords, API keys, or tokens.
- Rewrite each file as compact markdown: one title line, then bullets.
  No dated ## timestamps.
- Omit a file from the result if it is already compact.
- Only personal and app notes (never screens or the auto-written displays layout).

Current files:
<<<FILES>>>

Respond with JSON only (no markdown fences):
{"files": [{"kind": "personal" or "app", "name": "slug", "text": "# kind / slug\\n\\n- fact", "reason": "why"}]}
If nothing needs rewriting, return {"files": []}.
"""


def _condense_memories_impl(
    client: Any,
    *,
    memory_dir: Path | None = None,
) -> list[str]:
    notes = [
        n
        for n in list_memories("all", memory_dir=memory_dir)
        if n.kind in {"personal", "app"} and not _is_live_layout_memory(n.kind, n.name)
    ]
    if not notes_need_condense(notes):
        print("[memory] condense skipped (already compact)", flush=True)
        return []
    blob = _format_notes_for_condense(notes)
    prompt = _CONDENSE_PROMPT.replace("<<<FILES>>>", blob)
    print("[memory] condensing memories…", flush=True)
    try:
        response = client.responses.create(
            model=MEMORY_CONDENSE_MODEL,
            input=prompt,
        )
        raw = _response_output_text(response)
        payload = _parse_json_object(raw)
        files = parse_condensed_memory_files(payload)
        if not files:
            print("[memory] condense left files unchanged", flush=True)
            return []
        return apply_condensed_memory_files(files, memory_dir=memory_dir)
    except Exception as e:
        print(f"[memory] condense failed: {e}", flush=True)
        return []


def _condense_worker(*, memory_dir: Path | None) -> None:
    global _condense_running, _condense_pending
    try:
        while True:
            try:
                client = _new_extract_client()
                _condense_memories_impl(client, memory_dir=memory_dir)
            except Exception as e:
                print(f"[memory] condense failed: {e}", flush=True)
            with _CONDENSE_STATE_LOCK:
                if not _condense_pending:
                    _condense_running = False
                    return
                _condense_pending = False
    except Exception:
        with _CONDENSE_STATE_LOCK:
            _condense_running = False
            _condense_pending = False
        raise


def schedule_memory_condense(
    *,
    memory_dir: Path | None = None,
    background: bool = True,
) -> None:
    """
    Deduplicate personal/app memory files on a daemon thread.

    Coalesces overlapping requests so extract + save_memory do not stack
    parallel LLM calls. No-op when MEMORY_CONDENSE=0.
    """
    if not memory_condense_enabled():
        return
    global _condense_running, _condense_pending
    with _CONDENSE_STATE_LOCK:
        if _condense_running:
            _condense_pending = True
            return
        _condense_running = True
    if not background:
        _condense_worker(memory_dir=memory_dir)
        return
    threading.Thread(
        target=_condense_worker,
        kwargs={"memory_dir": memory_dir},
        name="memory-condense",
        daemon=True,
    ).start()
    print("[memory] condensing in background…", flush=True)


_SAVE_SCREEN_RE = re.compile(
    r"\b("
    r"(?:save|remember|memorize|store)\b.{0,40}\b(?:the |this )?(?:screen|screenshot|display)\b"
    r"|\bscreen as memory\b"
    r"|what's on (?:the )?screen"
    r")",
    re.IGNORECASE,
)


def is_save_screen_utterance(text: str) -> bool:
    """True when the user wants the current display stored as memory."""
    low = (text or "").strip().lower()
    if not low:
        return False
    return bool(_SAVE_SCREEN_RE.search(low))


def _frontmost_app_name() -> str:
    try:
        from AppKit import NSWorkspace  # type: ignore

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        name = str(app.localizedName() or "") if app is not None else ""
        return name.strip()
    except Exception:
        return ""


def _capture_png() -> bytes:
    from actions import DesktopController

    return DesktopController().capture_screenshot()


def _response_text(response: Any) -> str:
    chunks: list[str] = []
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) != "message":
            continue
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", None) == "output_text":
                chunks.append(part.text)
    if chunks:
        return "\n".join(chunks).strip()
    return (getattr(response, "output_text", None) or "").strip()


def _describe_screenshot(client: Any, png: bytes, *, hint: str | None, app: str) -> str:
    b64 = base64.b64encode(png).decode("ascii")
    extra = f"\nUser hint: {hint.strip()}\n" if (hint or "").strip() else ""
    app_line = f"Frontmost app (OS): {app}\n" if app else ""
    prompt = (
        "Describe this desktop screenshot so a voice assistant can recall it later.\n"
        f"{app_line}{extra}"
        "Write markdown:\n"
        "- First line: a short '# Title'\n"
        "- Then bullets: visible app/window, main content, important text, "
        "names, numbers, URLs, diagram labels, settings.\n"
        "Be concrete. Redact passwords, OTPs, and API keys. "
        "Do not say that this is a screenshot."
    )
    response = client.responses.create(
        model=MEMORY_VISION_MODEL,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{b64}",
                        "detail": "high",
                    },
                ],
            }
        ],
    )
    text = _response_text(response)
    if not text:
        raise RuntimeError("Vision model returned an empty description.")
    return text


def capture_screen_png() -> tuple[bytes, str]:
    """Grab the display now. Returns (png_bytes, frontmost_app_name)."""
    png = _capture_png()
    if not png:
        raise RuntimeError("Screenshot was empty.")
    return png, _frontmost_app_name()


def save_screen_from_png(
    client: Any,
    png: bytes,
    *,
    app: str = "",
    name: str | None = None,
    hint: str | None = None,
    memory_dir: Path | None = None,
) -> str:
    """Describe an already-captured PNG and write ``memory/screens/``."""
    if not png:
        raise RuntimeError("Screenshot was empty.")
    ensure_memory_dirs(memory_dir)
    app = (app or "").strip()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug_src = (name or "").strip() or (f"{app}-{stamp}" if app else f"screen-{stamp}")
    try:
        slug = sanitize_memory_name(slug_src)
    except ValueError:
        slug = sanitize_memory_name(f"screen-{stamp}")

    folder = _subdir("screen", memory_dir)
    png_path = folder / f"{slug}.png"
    md_path = folder / f"{slug}.md"
    n = 2
    while png_path.exists() or md_path.exists():
        slug = sanitize_memory_name(f"{slug_src}-{n}")
        png_path = folder / f"{slug}.png"
        md_path = folder / f"{slug}.md"
        n += 1

    try:
        description = _describe_screenshot(client, png, hint=hint, app=app)
    except Exception as e:
        description = f"(Description failed: {e})"

    png_path.write_bytes(png)
    utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    app_line = f"**App:** {app}\n\n" if app else ""
    hint_line = f"**Hint:** {hint.strip()}\n\n" if (hint or "").strip() else ""
    body = (
        f"# screen / {slug}\n\n"
        f"**Captured:** {utc}\n\n"
        f"{app_line}{hint_line}"
        f"**Image:** `{png_path.name}`\n\n"
        f"{description.strip()}\n"
    )
    md_path.write_text(body, encoding="utf-8")
    try:
        shown = md_path.relative_to(_root(memory_dir))
    except ValueError:
        shown = md_path.name
    print(f"[memory] saved screen {shown} ({len(png)} byte png)", flush=True)
    return f"Saved screen memory {shown} (app={app or 'unknown'})."


def capture_and_save_screen(
    client: Any,
    *,
    name: str | None = None,
    hint: str | None = None,
    memory_dir: Path | None = None,
) -> str:
    """
    Screenshot the desktop, describe it with a vision LLM, save PNG + markdown.

    Returns a short status string for the tool / orchestrator.
    """
    png, app = capture_screen_png()
    return save_screen_from_png(
        client,
        png,
        app=app,
        name=name,
        hint=hint,
        memory_dir=memory_dir,
    )


LIST_MEMORIES_TOOL = {
    "type": "function",
    "name": "list_memories",
    "description": (
        "List saved memories under memory/ (personal facts and per-app notes). "
        "Returns name + a one-line preview. Use read_memory for full text."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["personal", "app", "screen", "all"],
                "description": "Which memories to list.",
            },
        },
        "required": ["kind"],
        "additionalProperties": False,
    },
    "strict": True,
}

READ_MEMORY_TOOL = {
    "type": "function",
    "name": "read_memory",
    "description": (
        "Read stored memory markdown. kind=personal is user facts "
        "(usually name=profile); kind=app is per-application notes "
        "(name=hn, chrome, …); kind=screen is screenshot descriptions. "
        "Pass name=null to load every note of that kind. "
        "Use before ask_user — read when a fact you need may already be saved "
        "(profile, app habits, screen context). Pass name=null to load every note "
        "of that kind when unsure which file holds the answer."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["personal", "app", "screen"],
                "description": "personal, app, or screen.",
            },
            "name": {
                "type": ["string", "null"],
                "description": (
                    "Note slug without .md (profile, hn, or a screen slug). "
                    "Pass null to read all notes of this kind."
                ),
            },
        },
        "required": ["kind", "name"],
        "additionalProperties": False,
    },
    "strict": True,
}

SAVE_MEMORY_TOOL = {
    "type": "function",
    "name": "save_memory",
    "description": (
        "Save a durable fact to memory/. personal → memory/personal/<name>.md; "
        "app → memory/apps/<name>.md. Use when the user says remember/save this, "
        "or after you learn a preference you will need again. Never store "
        "passwords or API keys unless explicitly asked."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["personal", "app"],
                "description": "personal or app.",
            },
            "name": {
                "type": "string",
                "description": "Short slug (profile, hn, gmail, …).",
            },
            "text": {
                "type": "string",
                "description": "Fact(s) to store, plain language or bullets.",
            },
            "mode": {
                "type": "string",
                "enum": ["append", "replace"],
                "description": "append adds a dated section; replace overwrites the file.",
            },
        },
        "required": ["kind", "name", "text", "mode"],
        "additionalProperties": False,
    },
    "strict": True,
}

SAVE_SCREEN_MEMORY_TOOL = {
    "type": "function",
    "name": "save_screen_memory",
    "description": (
        "Capture the current desktop, describe it with a vision model, and save "
        "PNG + markdown under memory/screens/. Use when the user says "
        "'save the screen as memory', 'remember this screen', or wants a visual "
        "snapshot for later. Do not start a computer-use task just to screenshot."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": ["string", "null"],
                "description": "Optional slug (pin-diagram, maps-wentworth). Null to auto-name.",
            },
            "hint": {
                "type": ["string", "null"],
                "description": "Optional context from the user about what matters on screen.",
            },
        },
        "required": ["name", "hint"],
        "additionalProperties": False,
    },
    "strict": True,
}

MEMORY_TOOLS = [
    LIST_MEMORIES_TOOL,
    READ_MEMORY_TOOL,
    SAVE_MEMORY_TOOL,
    SAVE_SCREEN_MEMORY_TOOL,
]


def run_memory_tool(name: str, args: dict, *, client: Any | None = None) -> str:
    """Execute list/read/save memory tools from a function call."""
    kind = args.get("kind")
    mem_name = args.get("name")
    if isinstance(mem_name, str):
        mem_name = mem_name.strip() or None
    else:
        mem_name = None

    try:
        if name == "list_memories":
            notes = list_memories(str(kind or "all"))
            if not notes:
                return "No memories saved yet."
            return "\n".join(f"{n.rel}: {_preview(n.text)}" for n in notes)

        if name == "read_memory":
            return read_memory(str(kind or "personal"), mem_name)

        if name == "save_memory":
            text = (args.get("text") or "").strip()
            mode = str(args.get("mode") or "append")
            if not mem_name:
                return "Error: save_memory requires a name (e.g. profile, hn)."
            path = save_memory(str(kind or "personal"), mem_name, text, mode=mode)
            try:
                shown = path.relative_to(_root(None))
            except ValueError:
                shown = path.name
            return f"Saved {shown}."

        if name == "save_screen_memory":
            if client is None:
                return "Error: save_screen_memory requires an API client."
            hint = args.get("hint")
            if not isinstance(hint, str):
                hint = None
            return capture_and_save_screen(client, name=mem_name, hint=hint)

        return f"Unsupported memory tool: {name}"
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        return f"Error: {e}"
