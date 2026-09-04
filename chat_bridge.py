"""Localhost HTTP API for the Electron chat desktop app.

Bound to 127.0.0.1 only. Auth: Bearer token in ``.runtime/chat.token``.
The Electron UI talks here for SQLite history and orchestrator IPC
(``enqueue_utterance`` / ``consume_chat_inbox``).

Started by the tray when chat is enabled, or: ``python chat_bridge.py``.
"""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from envfile import load_dotenv

load_dotenv()

from app_status import (  # noqa: E402
    RUNTIME_DIR,
    chat_stream_payload,
    consume_chat_inbox,
    consume_chat_inbox_items,
    enqueue_utterance,
    pid_alive,
    read_status,
    save_chat_screenshot_png,
    set_chat_bridge_pid,
    set_chat_stream,
)
from chat_store import (  # noqa: E402
    PREF_CHAT_TTS,
    PREF_SCREENSHOT_DISPLAYS,
    PREF_SCREENSHOT_ON,
    get_store,
    title_from_text,
)

HOST = "127.0.0.1"
PORT = int(os.environ.get("CHAT_BRIDGE_PORT", "8743"))
TOKEN_PATH = RUNTIME_DIR / "chat.token"
_INBOX_WORKER_STARTED = False
_INBOX_WORKER_LOCK = threading.Lock()
TOKEN_LEN = 24
PID_KEY = "chat_bridge_pid"
_OFF = {"0", "false", "no", "off"}
ROOT = Path(__file__).resolve().parent
_SECRET_KEY_RE = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|authorization|credential)",
    re.I,
)


def _mcp_config_path() -> Path:
    return Path(os.environ.get("MCP_CONFIG") or ROOT / "mcp.json")


def _read_mcp_raw() -> dict[str, Any]:
    path = _mcp_config_path()
    if not path.is_file():
        return {"mcpServers": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"mcpServers": {}}
    if not isinstance(data, dict):
        return {"mcpServers": {}}
    if "mcpServers" not in data or not isinstance(data.get("mcpServers"), dict):
        data["mcpServers"] = {}
    return data


def _write_mcp_raw(data: dict[str, Any]) -> Path:
    path = _mcp_config_path()
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def _redact_map(data: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(data, dict):
        return out
    for key, val in data.items():
        k = str(key)
        if _SECRET_KEY_RE.search(k):
            out[k] = "***"
        else:
            s = str(val)
            out[k] = "***" if len(s) > 24 and s.lower().startswith("bearer ") else s
    return out


def list_mcp_connections() -> list[dict[str, Any]]:
    """Connections as stored in mcp.json (secrets redacted for the UI)."""
    raw = _read_mcp_raw().get("mcpServers") or {}
    rows: list[dict[str, Any]] = []
    if not isinstance(raw, dict):
        return rows
    for name, spec in raw.items():
        if not isinstance(spec, dict):
            continue
        command = spec.get("command")
        url = spec.get("url") or spec.get("serverUrl")
        transport = str(spec.get("type") or spec.get("transport") or "").strip().lower()
        if not transport:
            transport = "stdio" if command else "http"
        if transport in {"streamable-http", "streamable_http"}:
            transport = "http"
        disabled = spec.get("disabled") is True or spec.get("enabled") is False
        rows.append(
            {
                "name": str(name),
                "transport": transport,
                "url": str(url) if url else None,
                "command": str(command) if command else None,
                "args": [str(a) for a in (spec.get("args") or [])]
                if isinstance(spec.get("args"), list)
                else [],
                "auth": str(spec.get("auth") or "").strip().lower() or None,
                "headers": _redact_map(spec.get("headers")),
                "env": _redact_map(spec.get("env")),
                "enabled": not disabled,
            }
        )
    rows.sort(key=lambda r: r["name"])
    return rows


def upsert_mcp_connection(body: dict[str, Any]) -> dict[str, Any]:
    """Add or replace a server entry in mcp.json."""
    from mcp_auth import sanitize_server_name

    name = sanitize_server_name(str(body.get("name") or ""))
    kind = str(body.get("kind") or body.get("transport") or "").strip().lower()
    url = str(body.get("url") or "").strip()
    command = str(body.get("command") or "").strip()
    auth = str(body.get("auth") or "").strip().lower()
    if auth in {"oauth2", "browser", "login"}:
        auth = "oauth"
    elif auth in {"bearer", "pat"}:
        auth = "token"
    elif auth in {"", "none", "off"}:
        auth = ""

    if kind in {"stdio", "command", "local"}:
        kind = "stdio"
    elif kind in {"http", "url", "sse", "remote"}:
        kind = "http" if kind != "sse" else "sse"
    elif url:
        kind = "http"
    elif command:
        kind = "stdio"
    else:
        raise ValueError("Provide a URL (remote) or command (local stdio)")

    entry: dict[str, Any] = {}
    if kind == "stdio":
        if not command:
            raise ValueError("command is required for local MCP servers")
        entry["command"] = command
        args_raw = body.get("args")
        if isinstance(args_raw, list):
            entry["args"] = [str(a) for a in args_raw if str(a).strip()]
        elif isinstance(args_raw, str) and args_raw.strip():
            # Prefer newline-separated; fall back to shlex-like split on spaces.
            lines = [ln.strip() for ln in args_raw.splitlines() if ln.strip()]
            entry["args"] = lines if len(lines) > 1 else args_raw.strip().split()
        env = body.get("env")
        if isinstance(env, dict) and env:
            entry["env"] = {str(k): str(v) for k, v in env.items()}
        elif isinstance(env, str) and env.strip():
            parsed = json.loads(env)
            if not isinstance(parsed, dict):
                raise ValueError("env must be a JSON object")
            entry["env"] = {str(k): str(v) for k, v in parsed.items()}
    else:
        if not url:
            raise ValueError("url is required for remote MCP servers")
        entry["url"] = url
        if kind == "sse":
            entry["transport"] = "sse"
        if auth:
            entry["auth"] = auth
        headers: dict[str, str] = {}
        raw_headers = body.get("headers")
        if isinstance(raw_headers, dict):
            headers.update({str(k): str(v) for k, v in raw_headers.items()})
        elif isinstance(raw_headers, str) and raw_headers.strip():
            parsed = json.loads(raw_headers)
            if not isinstance(parsed, dict):
                raise ValueError("headers must be a JSON object")
            headers.update({str(k): str(v) for k, v in parsed.items()})
        token = str(body.get("token") or body.get("bearer") or "").strip()
        if token:
            if not token.lower().startswith("bearer "):
                token = f"Bearer {token}"
            headers["Authorization"] = token
            if not auth:
                entry["auth"] = "token"
        if headers:
            entry["headers"] = headers

    data = _read_mcp_raw()
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        servers = {}
        data["mcpServers"] = servers
    existing = servers.get(name) if isinstance(servers.get(name), dict) else {}
    # Preserve unknown keys; replace known connection fields.
    merged = dict(existing)
    for drop in ("command", "args", "env", "url", "serverUrl", "headers", "auth", "transport", "type"):
        if drop not in entry:
            merged.pop(drop, None)
    merged.update(entry)
    merged.pop("disabled", None)
    servers[name] = merged
    path = _write_mcp_raw(data)
    return {"name": name, "path": str(path), "server": merged}


def delete_mcp_connection(name: str) -> None:
    from mcp_auth import sanitize_server_name

    slug = sanitize_server_name(name)
    data = _read_mcp_raw()
    servers = data.get("mcpServers")
    if not isinstance(servers, dict) or slug not in servers:
        raise KeyError(f"unknown MCP server {slug!r}")
    del servers[slug]
    _write_mcp_raw(data)


def chat_bridge_enabled() -> bool:
    """Bridge runs when chat is on, or CHAT_BRIDGE=1 forces it."""
    if os.environ.get("CHAT_BRIDGE", "").strip().lower() not in {"", *_OFF}:
        return True
    return bool(read_status().get("chat_overlay_enabled"))


def _new_token() -> str:
    return secrets.token_urlsafe(TOKEN_LEN)[:TOKEN_LEN]


def load_or_create_token() -> str:
    env = (os.environ.get("CHAT_BRIDGE_TOKEN") or "").strip()
    if env:
        return env
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if TOKEN_PATH.is_file():
        raw = TOKEN_PATH.read_text(encoding="utf-8").strip()
        if len(raw) >= 16:
            return raw
    token = _new_token()
    TOKEN_PATH.write_text(token + "\n", encoding="utf-8")
    try:
        TOKEN_PATH.chmod(0o600)
    except OSError:
        pass
    return token


def command_for_orchestrator(text: str, *, look_at_screen: bool) -> str:
    body = (text or "").strip()
    if look_at_screen:
        if body:
            return f"Look at the attached screenshot. {body}"
        return "Look at the attached screenshot and tell me what you see."
    return body


def _parse_display_indexes(raw: Any) -> list[int] | None:
    """None = all displays. Empty list also means all."""
    if raw is None:
        return None
    if isinstance(raw, str):
        text = raw.strip().lower()
        if not text or text in {"all", "*", "any"}:
            return None
        try:
            raw = json.loads(raw)
        except Exception:
            parts = [p.strip() for p in text.split(",") if p.strip()]
            raw = parts
    if not isinstance(raw, (list, tuple)):
        return None
    out: list[int] = []
    for item in raw:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out or None


def screenshot_display_indexes(store=None) -> list[int] | None:
    st = store or get_store()
    return _parse_display_indexes(st.get_pref(PREF_SCREENSHOT_DISPLAYS))


def set_screenshot_display_indexes(indexes: list[int] | None, store=None) -> list[int] | None:
    st = store or get_store()
    if not indexes:
        st.set_pref(PREF_SCREENSHOT_DISPLAYS, "[]")
        return None
    clean = sorted({int(i) for i in indexes})
    st.set_pref(PREF_SCREENSHOT_DISPLAYS, json.dumps(clean))
    return clean


def displays_payload() -> dict[str, Any]:
    from actions import list_monitors

    store = get_store()
    selected = screenshot_display_indexes(store)
    monitors = []
    for m in list_monitors():
        idx = int(m["index"])
        monitors.append(
            {
                "index": idx,
                "name": m.get("name") or f"Display {idx}",
                "main": bool(m.get("main")),
                "width": int(m.get("width") or 0),
                "height": int(m.get("height") or 0),
                "selected": selected is None or idx in selected,
            }
        )
    return {
        "ok": True,
        "displays": monitors,
        "all": selected is None,
        "selected": selected,
    }


def _capture_desktop_png(*, display_indexes: list[int] | None = None) -> bytes:
    from actions import capture_displays_png

    return capture_displays_png(display_indexes)


def _json_body(handler: BaseHTTPRequestHandler, *, max_bytes: int = 8_000_000) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0 or length > max_bytes:
        return {}
    raw = handler.rfile.read(length)
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def list_speaker_payload() -> dict[str, Any]:
    from speaker_id import (
        ENROLLMENT_PASSAGES,
        LONG_PASSAGE_COUNT,
        SPEAKER_ID_ENABLED,
        SPEAKER_ID_MODEL,
        list_profiles,
    )

    speakers = []
    for p in list_profiles():
        speakers.append(
            {
                "slug": p.get("slug") or p.get("name"),
                "display_name": p.get("display_name") or p.get("slug") or p.get("name"),
                "enrolled_at": p.get("enrolled_at"),
                "threshold": p.get("threshold"),
                "threshold_short": p.get("threshold_short"),
                "model": p.get("model") or SPEAKER_ID_MODEL,
                "sample_count": len(p.get("embeddings") or []),
            }
        )
    passages = [
        {
            "index": i,
            "title": title,
            "text": text,
            "short": i >= LONG_PASSAGE_COUNT,
        }
        for i, (title, text) in enumerate(ENROLLMENT_PASSAGES)
    ]
    return {
        "ok": True,
        "enabled": SPEAKER_ID_ENABLED,
        "model": SPEAKER_ID_MODEL,
        "speakers": speakers,
        "passages": passages,
        "required_samples": len(ENROLLMENT_PASSAGES),
    }


def enroll_speaker_from_body(body: dict[str, Any]) -> dict[str, Any]:
    from speaker_enroll import _release_audio_for_capture
    from speaker_id import (
        ENROLLMENT_PASSAGES,
        enroll_speaker,
        slug_name,
        wav_has_min_speech,
    )

    name = str(body.get("name") or body.get("display_name") or "").strip()
    if not name:
        raise ValueError("name is required")
    samples_b64 = body.get("samples") or body.get("wav_b64") or []
    if not isinstance(samples_b64, list):
        raise ValueError("samples must be a list of base64 WAV strings")
    if len(samples_b64) != len(ENROLLMENT_PASSAGES):
        raise ValueError(
            f"Need {len(ENROLLMENT_PASSAGES)} WAV samples (got {len(samples_b64)})"
        )
    _release_audio_for_capture()
    samples: list[bytes] = []
    for i, raw in enumerate(samples_b64):
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"sample {i + 1} is empty")
        try:
            wav = base64.b64decode(raw.strip(), validate=False)
        except Exception as e:
            raise ValueError(f"sample {i + 1} is not valid base64: {e}") from e
        if not wav.startswith(b"RIFF"):
            raise ValueError(f"sample {i + 1} must be WAV (RIFF) audio")
        short = i >= 3
        if not wav_has_min_speech(wav):
            kind = "short phrase" if short else "passage"
            raise ValueError(f"sample {i + 1} ({kind}) has too little speech — record again")
        samples.append(wav)
    root = enroll_speaker(name, samples)
    return {
        "ok": True,
        "slug": slug_name(name),
        "display_name": name,
        "path": str(root),
        "note": "Restart the orchestrator (or wait for the next utterance) to use speaker ID.",
    }


def observe_status_payload() -> dict[str, Any]:
    import observe as observe_mod

    pid = observe_mod.running_pid()
    drafts = []
    for path in observe_mod.list_proposed():
        try:
            data = observe_mod.load_draft(path)
        except Exception:
            continue
        focus = data.get("focus") or {}
        memories = []
        for i, item in enumerate(data.get("memories") or [], start=1):
            memories.append(
                {
                    "ref": f"m{i}",
                    "kind": item.get("kind") or "app",
                    "name": item.get("name") or "",
                    "text": item.get("text") or "",
                }
            )
        skills = []
        for i, item in enumerate(data.get("skills") or [], start=1):
            skills.append(
                {
                    "ref": f"s{i}",
                    "name": item.get("name") or "",
                    "description": item.get("description") or "",
                    "body": item.get("body") or "",
                }
            )
        drafts.append(
            {
                "id": path.name,
                "app": focus.get("app") or "",
                "url": focus.get("url") or "",
                "created_at": data.get("created_at") or data.get("started_at"),
                "memories": memories,
                "skills": skills,
            }
        )
    return {
        "ok": True,
        "running": pid is not None,
        "pid": pid,
        "draft_seconds": observe_mod.DRAFT_SECONDS,
        "proposed_dir": str(observe_mod.PROPOSED_DIR),
        "drafts": drafts,
    }


def set_observe_running(enabled: bool) -> dict[str, Any]:
    import observe as observe_mod

    if enabled:
        code = observe_mod.cmd_start()
        if code != 0 and observe_mod.running_pid() is None:
            raise RuntimeError("Failed to start observe daemon")
    else:
        observe_mod.cmd_stop()
    return observe_status_payload()


def accept_observe_draft(
    draft_id: str,
    *,
    items: list[str] | None = None,
    all_drafts: bool = False,
) -> dict[str, Any]:
    import observe as observe_mod

    drafts = observe_mod.list_proposed()
    if all_drafts:
        chosen = drafts
    else:
        chosen = observe_mod._find_drafts(draft_id, drafts)
        if not chosen:
            raise KeyError(f"unknown draft {draft_id!r}")
    written: list[str] = []
    for path in chosen:
        written.extend(
            observe_mod.accept_draft(
                path,
                items=items if not all_drafts else None,
            )
        )
    return {"ok": True, "written": written, **observe_status_payload()}


def reject_observe_draft(
    draft_id: str,
    *,
    items: list[str] | None = None,
    all_drafts: bool = False,
) -> dict[str, Any]:
    import observe as observe_mod

    drafts = observe_mod.list_proposed()
    if all_drafts:
        chosen = drafts
    else:
        chosen = observe_mod._find_drafts(draft_id, drafts)
        if not chosen:
            raise KeyError(f"unknown draft {draft_id!r}")
    for path in chosen:
        observe_mod.reject_draft(
            path,
            items=items if not all_drafts else None,
        )
    return {"ok": True, **observe_status_payload()}


def list_memories_payload() -> dict[str, Any]:
    from memory import (
        PERSONAL_FILE_SLUG,
        _is_live_layout_memory,
        list_memories,
    )

    notes = []
    for note in list_memories("all"):
        if _is_live_layout_memory(note.kind, note.name):
            continue
        preview = " ".join((note.text or "").split())
        if len(preview) > 140:
            preview = preview[:139] + "…"
        notes.append(
            {
                "kind": note.kind,
                "name": note.name,
                "rel": note.rel,
                "preview": preview or "(empty)",
                "text": note.text,
                "editable": True,
                "locked_name": note.kind == "personal" and note.name == PERSONAL_FILE_SLUG,
            }
        )
    return {"ok": True, "memories": notes, "count": len(notes)}


def _face_option(spec: Any, *, selected: bool, size: int = 96) -> dict[str, Any]:
    from face_overlay import BLOBATARS, blobatar_png_bytes

    png = blobatar_png_bytes(size, mood="wink", seed=spec.id)
    return {
        "id": spec.id,
        "title": getattr(spec, "title", None) or spec.id,
        "blurb": getattr(spec, "blurb", None) or "",
        "custom": spec.id not in BLOBATARS,
        "selected": selected,
        "b64": base64.b64encode(png).decode("ascii"),
    }


def face_status_payload(*, include_previews: bool = True) -> dict[str, Any]:
    """Face overlay on/off + curated blobatars (with optional PNG previews)."""
    from AppKit import NSApplication  # type: ignore

    from app_status import read_status
    from face_overlay import (
        BLOBATARS,
        blobatar_png_bytes,
        current_blobatar,
        face_overlay_enabled,
        face_overlay_env_enabled,
    )

    NSApplication.sharedApplication()
    snap = read_status()
    current = current_blobatar(snap)
    presets: list[dict[str, Any]] = []
    for spec in BLOBATARS.values():
        if include_previews:
            presets.append(_face_option(spec, selected=spec.id == current.id))
        else:
            presets.append(
                {
                    "id": spec.id,
                    "title": spec.title,
                    "blurb": spec.blurb,
                    "custom": False,
                    "selected": spec.id == current.id,
                }
            )
    if current.id not in BLOBATARS:
        if include_previews:
            presets.append(_face_option(current, selected=True))
        else:
            presets.append(
                {
                    "id": current.id,
                    "title": getattr(current, "title", None) or current.id,
                    "blurb": getattr(current, "blurb", None) or "custom seed",
                    "custom": True,
                    "selected": True,
                }
            )
    preview_b64 = None
    if include_previews:
        preview_b64 = base64.b64encode(
            blobatar_png_bytes(128, mood="wink", seed=current.id)
        ).decode("ascii")
    return {
        "ok": True,
        "enabled": face_overlay_enabled(snap),
        "env_disabled": not face_overlay_env_enabled(),
        "current": {
            "id": current.id,
            "title": getattr(current, "title", None) or current.id,
            "blurb": getattr(current, "blurb", None) or "",
        },
        "preview_b64": preview_b64,
        "presets": presets,
    }


def update_face_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Toggle face overlay and/or switch blobatar preset / custom seed."""
    from app_status import set_face_overlay_enabled
    from face_overlay import face_overlay_env_enabled, set_blobatar

    if "enabled" in body or "running" in body:
        enabled = body.get("enabled")
        if enabled is None:
            enabled = body.get("running")
        if not face_overlay_env_enabled() and bool(enabled):
            raise ValueError("FACE_OVERLAY=0 in the environment — cannot enable")
        set_face_overlay_enabled(bool(enabled))

    preset = body.get("preset")
    if preset is None:
        preset = body.get("name") or body.get("seed")
    if preset is not None:
        name = str(preset).strip()
        if not name:
            raise ValueError("preset name is empty")
        set_blobatar(name)

    return face_status_payload()


def write_memory_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Replace a memory file's markdown contents (full-file edit)."""
    from memory import (
        PERSONAL_FILE_SLUG,
        _canonical_kind,
        _is_live_layout_memory,
        _subdir,
        ensure_memory_dirs,
        personal_memory_path,
        sanitize_memory_name,
    )

    kind = _canonical_kind(str(body.get("kind") or ""))
    name = str(body.get("name") or "").strip()
    text = body.get("text")
    if text is None:
        raise ValueError("text is required")
    text = str(text)
    if not text.strip():
        raise ValueError("Memory text is empty")
    ensure_memory_dirs()
    if kind == "personal":
        path = personal_memory_path()
        name = PERSONAL_FILE_SLUG
    else:
        if not name:
            raise ValueError("name is required")
        slug = sanitize_memory_name(name)
        if _is_live_layout_memory(kind, slug):
            raise ValueError("That memory is system-managed and cannot be edited here")
        path = _subdir(kind) / f"{slug}.md"
        name = slug
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    return {
        "ok": True,
        "kind": kind,
        "name": name,
        "rel": f"{kind}/{name}.md",
        **list_memories_payload(),
    }


def resolve_active_chat_id(store=None) -> str | None:
    """Chat that should receive spoken replies (send target / last selection)."""
    st = store or get_store()
    return st.active_chat_id()


def post_assistant_message(
    text: str,
    *,
    chat_id: str | None = None,
    open_window: bool = False,
    store=None,
) -> dict[str, Any]:
    """Persist an agent-authored line in chat, optionally opening the window."""
    body = (text or "").strip()
    if not body:
        raise ValueError("Chat message is empty.")
    st = store or get_store()
    target = (chat_id or "").strip() or resolve_active_chat_id(st)
    if target and st.get_chat(target) is None:
        raise ValueError(f"Chat {target!r} does not exist.")
    if not target:
        chat = st.create_chat(title=title_from_text(body, fallback="Agent message"))
        target = chat.id
    st.set_active_chat_id(target)
    row = st.add_message(target, "assistant", body)
    if open_window:
        from chat_overlay import ensure_chat_bridge_and_app

        ensure_chat_bridge_and_app(focus=True)
    return {
        "ok": True,
        "chat_id": target,
        "message_id": row.id,
        "opened": bool(open_window),
    }


def persist_chat_inbox() -> dict[str, Any]:
    """Drain spoken inbox into SQLite so replies survive a closed chat window.

    The Electron UI used to be the only consumer of ``chat_inbox``; if the
    window was closed mid-reply, lines were lost or never written to history.
    """
    items = consume_chat_inbox_items()
    if not items:
        return {"ok": True, "appended": 0, "chat_id": resolve_active_chat_id()}
    store = get_store()
    fallback_chat_id = resolve_active_chat_id(store)
    appended_chat_ids: list[str] = []
    for item in items:
        chat_id = str(item.get("chat_id") or "").strip() or fallback_chat_id
        if not chat_id or store.get_chat(chat_id) is None:
            chat = store.create_chat(title="Chat")
            chat_id = chat.id
            fallback_chat_id = chat_id
            store.set_active_chat_id(chat_id)
        store.add_message(chat_id, "assistant", str(item["text"]))
        appended_chat_ids.append(chat_id)
    # History now has the final line — drop the live stream cursor.
    try:
        set_chat_stream(None)
    except Exception:
        pass
    return {
        "ok": True,
        "appended": len(items),
        "chat_id": appended_chat_ids[-1],
        "chat_ids": list(dict.fromkeys(appended_chat_ids)),
    }


def ensure_inbox_worker() -> None:
    """Background drain so persistence does not depend on UI polling."""
    global _INBOX_WORKER_STARTED
    with _INBOX_WORKER_LOCK:
        if _INBOX_WORKER_STARTED:
            return
        _INBOX_WORKER_STARTED = True

    def _loop() -> None:
        while True:
            try:
                persist_chat_inbox()
            except Exception as e:
                print(f"[chat-bridge] inbox persist failed: {e}", flush=True)
            time.sleep(0.45)

    threading.Thread(target=_loop, name="chat-inbox-persist", daemon=True).start()


def _chat_row(c) -> dict[str, Any]:
    return {
        "id": c.id,
        "title": c.title,
        "model_id": c.model_id,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


def _msg_row(m, store) -> dict[str, Any]:
    shot_b64 = None
    if m.screenshot_relpath:
        png = store.read_screenshot(m.screenshot_relpath)
        if png:
            shot_b64 = base64.b64encode(png).decode("ascii")
    return {
        "id": m.id,
        "chat_id": m.chat_id,
        "role": m.role,
        "content": m.content,
        "screenshot_relpath": m.screenshot_relpath,
        "screenshot_b64": shot_b64,
        "created_at": m.created_at,
        "seq": m.seq,
    }


class ChatBridgeHandler(BaseHTTPRequestHandler):
    token: str = ""

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        print(f"[chat-bridge] " + fmt % args, flush=True)

    def _auth_ok(self) -> bool:
        auth = self.headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            got = auth[7:].strip()
            return bool(got) and secrets.compare_digest(got, self.token)
        qs = parse_qs(urlparse(self.path).query)
        got = (qs.get("token") or [""])[0]
        return bool(got) and secrets.compare_digest(got, self.token)

    def _send(self, code: int, payload: Any, *, content_type: str = "application/json") -> None:
        body = (
            payload
            if isinstance(payload, (bytes, bytearray))
            else json.dumps(payload).encode("utf-8")
        )
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, b"")

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/v1/health":
            self._send(200, {"ok": True, "service": "cua-chat-bridge"})
            return
        if not self._auth_ok():
            self._send(401, {"ok": False, "error": "unauthorized"})
            return
        store = get_store()
        if path == "/v1/status":
            snap = read_status()
            persisted = persist_chat_inbox()
            stream = chat_stream_payload()
            self._send(
                200,
                {
                    "ok": True,
                    "orchestrator_alive": pid_alive(snap.get("orchestrator_pid")),
                    "chat_enabled": bool(snap.get("chat_overlay_enabled")),
                    "overlay_hidden": bool(snap.get("overlay_hidden")),
                    "screenshot_on": store.get_pref(PREF_SCREENSHOT_ON, "0") == "1",
                    "screenshot_displays": screenshot_display_indexes(store),
                    "chat_tts_on": store.get_pref(PREF_CHAT_TTS, "1") != "0",
                    "face_preset": snap.get("face_preset"),
                    "inbox": [],
                    "assistant_appended": int(persisted.get("appended") or 0),
                    "active_chat_id": persisted.get("chat_id") or resolve_active_chat_id(store),
                    "appended_chat_ids": persisted.get("chat_ids") or [],
                    "chat_stream": stream,
                },
            )
            return
        if path == "/v1/displays":
            try:
                self._send(200, displays_payload())
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
            return
        if path == "/v1/chats":
            self._send(200, {"ok": True, "chats": [_chat_row(c) for c in store.list_chats()]})
            return
        if path == "/v1/mcp":
            self._send(
                200,
                {
                    "ok": True,
                    "path": str(_mcp_config_path()),
                    "connections": list_mcp_connections(),
                },
            )
            return
        if path == "/v1/speakers":
            try:
                self._send(200, list_speaker_payload())
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
            return
        if path == "/v1/systems" or path == "/v1/observe":
            try:
                self._send(200, observe_status_payload())
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
            return
        if path == "/v1/latency":
            try:
                from latency_report import build_report, report_payload

                build_report()
                self._send(200, report_payload(limit=30))
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
            return
        if path == "/v1/face":
            try:
                self._send(200, face_status_payload())
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
            return
        if path == "/v1/memories":
            try:
                self._send(200, list_memories_payload())
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
            return
        if path == "/v1/avatars":
            try:
                from AppKit import NSApplication  # type: ignore

                NSApplication.sharedApplication()
                from face_overlay import chat_avatar_pngs

                avatars = chat_avatar_pngs(size=128)
                self._send(
                    200,
                    {
                        "ok": True,
                        "assistant_id": avatars["assistant_id"],
                        "user_id": avatars["user_id"],
                        "assistant_b64": base64.b64encode(avatars["assistant_png"]).decode(
                            "ascii"
                        ),
                        "user_b64": base64.b64encode(avatars["user_png"]).decode("ascii"),
                    },
                )
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
            return
        if path.startswith("/v1/chats/") and path.endswith("/messages"):
            chat_id = path[len("/v1/chats/") : -len("/messages")]
            msgs = store.list_messages(chat_id)
            self._send(200, {"ok": True, "messages": [_msg_row(m, store) for m in msgs]})
            return
        if path.startswith("/v1/screenshots/"):
            rel = path[len("/v1/screenshots/") :]
            png = store.read_screenshot(rel)
            if not png:
                self._send(404, {"ok": False, "error": "not found"})
                return
            self._send(200, png, content_type="image/png")
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if not self._auth_ok():
            self._send(401, {"ok": False, "error": "unauthorized"})
            return
        max_bytes = 40_000_000 if path == "/v1/speakers" else 8_000_000
        body = _json_body(self, max_bytes=max_bytes)
        store = get_store()
        if path == "/v1/chats":
            chat = store.create_chat(
                title=str(body.get("title") or "New chat"),
                model_id=str(body.get("model_id") or "orchestrator"),
            )
            store.set_active_chat_id(chat.id)
            self._send(200, {"ok": True, "chat": _chat_row(chat)})
            return
        if path == "/v1/prefs/screenshot":
            on = bool(body.get("on"))
            store.set_pref(PREF_SCREENSHOT_ON, "1" if on else "0")
            self._send(200, {"ok": True, "screenshot_on": on})
            return
        if path == "/v1/prefs/tts":
            on = bool(body.get("on"))
            store.set_pref(PREF_CHAT_TTS, "1" if on else "0")
            self._send(200, {"ok": True, "chat_tts_on": on})
            return
        if path == "/v1/prefs/screenshot-displays":
            try:
                if body.get("all") is True or body.get("displays") in (None, "all", "*", []):
                    selected = set_screenshot_display_indexes(None, store)
                else:
                    selected = set_screenshot_display_indexes(
                        _parse_display_indexes(body.get("displays")),
                        store,
                    )
                self._send(200, {**displays_payload(), "selected": selected})
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
            return
        if path == "/v1/prefs/active-chat":
            chat_id = str(body.get("chat_id") or "").strip()
            if not chat_id:
                self._send(400, {"ok": False, "error": "chat_id required"})
                return
            if store.get_chat(chat_id) is None:
                self._send(404, {"ok": False, "error": "chat not found"})
                return
            store.set_active_chat_id(chat_id)
            self._send(200, {"ok": True, "active_chat_id": chat_id})
            return
        if path == "/v1/mcp":
            try:
                result = upsert_mcp_connection(body)
            except ValueError as e:
                self._send(400, {"ok": False, "error": str(e)})
                return
            except json.JSONDecodeError as e:
                self._send(400, {"ok": False, "error": f"invalid JSON: {e}"})
                return
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
                return
            self._send(
                200,
                {
                    "ok": True,
                    "connection": next(
                        (c for c in list_mcp_connections() if c["name"] == result["name"]),
                        {"name": result["name"]},
                    ),
                    "note": "Restart the orchestrator to load new MCP servers.",
                },
            )
            return
        if path == "/v1/speakers":
            try:
                result = enroll_speaker_from_body(body)
            except ValueError as e:
                self._send(400, {"ok": False, "error": str(e)})
                return
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
                return
            self._send(200, result)
            return
        if path == "/v1/speakers/prepare":
            try:
                from speaker_enroll import _release_audio_for_capture

                _release_audio_for_capture()
            except Exception:
                pass
            self._send(200, {"ok": True})
            return
        if path == "/v1/observe":
            try:
                enabled = body.get("enabled")
                if enabled is None and "running" in body:
                    enabled = body.get("running")
                if enabled is None:
                    self._send(400, {"ok": False, "error": "enabled required"})
                    return
                self._send(200, set_observe_running(bool(enabled)))
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
            return
        if path == "/v1/face":
            try:
                self._send(200, update_face_payload(body))
            except ValueError as e:
                self._send(400, {"ok": False, "error": str(e)})
                return
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
                return
            return
        if path == "/v1/observe/accept":
            try:
                result = accept_observe_draft(
                    str(body.get("id") or ""),
                    items=[str(x) for x in (body.get("items") or [])],
                    all_drafts=bool(body.get("all")),
                )
            except KeyError as e:
                self._send(404, {"ok": False, "error": str(e)})
                return
            except ValueError as e:
                self._send(400, {"ok": False, "error": str(e)})
                return
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
                return
            self._send(200, result)
            return
        if path == "/v1/observe/reject":
            try:
                result = reject_observe_draft(
                    str(body.get("id") or ""),
                    items=[str(x) for x in (body.get("items") or [])],
                    all_drafts=bool(body.get("all")),
                )
            except KeyError as e:
                self._send(404, {"ok": False, "error": str(e)})
                return
            except ValueError as e:
                self._send(400, {"ok": False, "error": str(e)})
                return
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
                return
            self._send(200, result)
            return
        if path == "/v1/memories":
            try:
                result = write_memory_payload(body)
            except ValueError as e:
                self._send(400, {"ok": False, "error": str(e)})
                return
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
                return
            self._send(200, result)
            return
        if path == "/v1/send":
            chat_id = str(body.get("chat_id") or "").strip()
            text = str(body.get("text") or "")
            look = bool(body.get("look_at_screen"))
            if not chat_id:
                self._send(400, {"ok": False, "error": "chat_id required"})
                return
            if not text.strip() and not look:
                self._send(400, {"ok": False, "error": "text or look_at_screen required"})
                return
            relpath = None
            shot_file = None
            if look:
                try:
                    indexes = _parse_display_indexes(body.get("displays"))
                    if indexes is None:
                        indexes = screenshot_display_indexes(store)
                    png = _capture_desktop_png(display_indexes=indexes)
                    relpath = store.save_screenshot(chat_id, png)
                    shot_file = save_chat_screenshot_png(png)
                except Exception as e:
                    self._send(500, {"ok": False, "error": f"screenshot failed: {e}"})
                    return
            user_text = text.strip() or "(screenshot)"
            store.add_message(chat_id, "user", user_text, screenshot_relpath=relpath)
            store.set_active_chat_id(chat_id)
            chat = store.get_chat(chat_id)
            if chat and chat.title == "New chat":
                store.touch_chat(chat_id, title=title_from_text(user_text), model_id="orchestrator")
            else:
                store.touch_chat(chat_id, model_id="orchestrator")
            cmd = command_for_orchestrator(text, look_at_screen=look)
            tts_on = store.get_pref(PREF_CHAT_TTS, "1") != "0"
            enqueue_utterance(
                cmd,
                source="chat",
                tts=tts_on,
                screenshot_file=shot_file,
                chat_id=chat_id,
            )
            orch_ok = pid_alive(read_status().get("orchestrator_pid"))
            self._send(
                200,
                {
                    "ok": True,
                    "orchestrator_alive": orch_ok,
                    "warning": None
                    if orch_ok
                    else "Orchestrator is not running. Start: python orchestrator.py --auto",
                },
            )
            return
        if path == "/v1/assistant":
            # Optional: UI can push a line; normally inbox poll handles this.
            chat_id = str(body.get("chat_id") or "").strip()
            text = str(body.get("text") or "").strip()
            if not chat_id or not text:
                self._send(400, {"ok": False, "error": "chat_id and text required"})
                return
            store.add_message(chat_id, "assistant", text)
            self._send(200, {"ok": True})
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_DELETE(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if not self._auth_ok():
            self._send(401, {"ok": False, "error": "unauthorized"})
            return
        if path.startswith("/v1/chats/"):
            chat_id = path[len("/v1/chats/") :]
            get_store().delete_chat(chat_id)
            self._send(200, {"ok": True})
            return
        if path.startswith("/v1/mcp/"):
            name = path[len("/v1/mcp/") :]
            try:
                delete_mcp_connection(name)
            except KeyError as e:
                self._send(404, {"ok": False, "error": str(e)})
                return
            except ValueError as e:
                self._send(400, {"ok": False, "error": str(e)})
                return
            self._send(200, {"ok": True})
            return
        if path.startswith("/v1/speakers/"):
            name = path[len("/v1/speakers/") :]
            try:
                from speaker_id import delete_profile

                if not delete_profile(name):
                    self._send(404, {"ok": False, "error": f"unknown speaker {name!r}"})
                    return
            except ValueError as e:
                self._send(400, {"ok": False, "error": str(e)})
                return
            except Exception as e:
                self._send(500, {"ok": False, "error": str(e)})
                return
            self._send(200, {"ok": True})
            return
        self._send(404, {"ok": False, "error": "not found"})


def serve_forever(*, host: str = HOST, port: int = PORT) -> None:
    token = load_or_create_token()
    ChatBridgeHandler.token = token
    ensure_inbox_worker()
    server = ThreadingHTTPServer((host, port), ChatBridgeHandler)
    print(f"[chat-bridge] http://{host}:{port}", flush=True)
    print(f"[chat-bridge] token at {TOKEN_PATH}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[chat-bridge] stopped.", flush=True)


def ensure_chat_bridge() -> subprocess.Popen | None:
    """Start the bridge subprocess if not already running."""
    # The PID file can be stale after an unclean restart. The listening server
    # is the source of truth; do not create a process storm against an occupied
    # port merely because its recorded PID has gone away.
    try:
        import urllib.request

        urllib.request.urlopen(f"http://{HOST}:{PORT}/v1/health", timeout=0.2)
        return None
    except Exception:
        pass
    data = read_status()
    pid = data.get(PID_KEY)
    if pid_alive(pid):
        return None
    cmd = [sys.executable, str(Path(__file__).resolve())]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(Path(__file__).resolve().parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        print(f"[chat-bridge] failed to start: {e}", file=sys.stderr)
        return None
    set_chat_bridge_pid(proc.pid)
    for _ in range(40):
        try:
            import urllib.request

            urllib.request.urlopen(f"http://{HOST}:{PORT}/v1/health", timeout=0.2)
            break
        except Exception:
            time.sleep(0.05)
    print(f"[chat-bridge] started (pid={proc.pid}) port={PORT}", flush=True)
    return proc


def stop_chat_bridge(*, wait: float = 1.5) -> None:
    data = read_status()
    pid = data.get(PID_KEY)
    if not pid_alive(pid):
        set_chat_bridge_pid(None)
        return
    try:
        os.kill(int(pid), 15)
    except Exception:
        pass
    deadline = time.time() + wait
    while time.time() < deadline and pid_alive(pid):
        time.sleep(0.05)
    if pid_alive(pid):
        try:
            os.kill(int(pid), 9)
        except Exception:
            pass
    set_chat_bridge_pid(None)


def main(argv: list[str] | None = None) -> int:
    serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
