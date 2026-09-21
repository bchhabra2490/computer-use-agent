"""Local SQLite chat history + screenshot files for the desktop chat UI."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CHAT_HISTORY_LIMIT = 8
CHAT_HISTORY_CHAR_BUDGET = 2400
CHAT_HISTORY_MAX_AGE_HOURS = 12.0
CHAT_HISTORY_MSG_CHARS = 400

from app_status import RUNTIME_DIR

CHAT_DIR = Path(
    __import__("os").environ.get("CHAT_DATA_DIR", str(RUNTIME_DIR / "chat"))
)
DB_PATH = CHAT_DIR / "chats.sqlite3"
SCREENSHOTS_DIR = CHAT_DIR / "screenshots"

_lock = threading.Lock()
PREF_SELECTED_MODEL = "selected_model"
PREF_SCREENSHOT_ON = "screenshot_on"
PREF_ACTIVE_CHAT = "active_chat_id"
PREF_SCREENSHOT_DISPLAYS = "screenshot_displays"
PREF_CHAT_TTS = "chat_tts_on"
PREF_INBOX_HISTORY_REV = "inbox_history_rev"
PREF_INBOX_CHAT_REVS = "inbox_chat_revs"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _connect() -> sqlite3.Connection:
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS prefs (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chats (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            model_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            screenshot_relpath TEXT,
            created_at TEXT NOT NULL,
            seq INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_messages_chat_seq
            ON messages(chat_id, seq);
        CREATE INDEX IF NOT EXISTS idx_chats_updated
            ON chats(updated_at DESC);
        """
    )
    _ensure_inbox_schema(conn)
    conn.commit()


def _ensure_inbox_schema(conn: sqlite3.Connection) -> None:
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(chats)").fetchall()}
    if "inbox_rev" not in cols:
        conn.execute("ALTER TABLE chats ADD COLUMN inbox_rev INTEGER NOT NULL DEFAULT 0")
    if "assistant_rev" not in cols:
        conn.execute("ALTER TABLE chats ADD COLUMN assistant_rev INTEGER NOT NULL DEFAULT 0")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS inbox_meta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            history_rev INTEGER NOT NULL DEFAULT 0,
            assistant_rev INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute("INSERT OR IGNORE INTO inbox_meta(id, history_rev) VALUES (1, 0)")
    meta_cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(inbox_meta)").fetchall()}
    if "assistant_rev" not in meta_cols:
        conn.execute(
            "ALTER TABLE inbox_meta ADD COLUMN assistant_rev INTEGER NOT NULL DEFAULT 0"
        )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_inbox_rev ON chats(inbox_rev)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_assistant_rev ON chats(assistant_rev)")
    _migrate_inbox_prefs(conn)


def _migrate_inbox_prefs(conn: sqlite3.Connection) -> None:
    """Copy one-shot JSON prefs into the shared inbox tables, then drop them."""
    hist_row = conn.execute(
        "SELECT value FROM prefs WHERE key = ?", (PREF_INBOX_HISTORY_REV,)
    ).fetchone()
    revs_row = conn.execute(
        "SELECT value FROM prefs WHERE key = ?", (PREF_INBOX_CHAT_REVS,)
    ).fetchone()
    if hist_row is None and revs_row is None:
        return
    stored_rev = 0
    if hist_row is not None:
        try:
            stored_rev = max(0, int(hist_row["value"] or 0))
        except (TypeError, ValueError):
            stored_rev = 0
    current = conn.execute("SELECT history_rev FROM inbox_meta WHERE id = 1").fetchone()
    current_rev = int(current["history_rev"]) if current else 0
    if stored_rev > current_rev:
        conn.execute(
            "UPDATE inbox_meta SET history_rev = ? WHERE id = 1",
            (stored_rev,),
        )
    parsed: dict[str, int] = {}
    if revs_row is not None:
        try:
            raw = json.loads(revs_row["value"] or "{}")
        except json.JSONDecodeError:
            raw = {}
        if isinstance(raw, dict):
            for cid, rev in raw.items():
                key = str(cid).strip()
                if not key:
                    continue
                try:
                    parsed[key] = int(rev)
                except (TypeError, ValueError):
                    continue
    for cid, rev in parsed.items():
        conn.execute(
            "UPDATE chats SET inbox_rev = ? WHERE id = ? AND inbox_rev < ?",
            (rev, cid, rev),
        )
    conn.execute(
        "DELETE FROM prefs WHERE key IN (?, ?)",
        (PREF_INBOX_HISTORY_REV, PREF_INBOX_CHAT_REVS),
    )


@dataclass
class ChatRow:
    id: str
    title: str
    model_id: str | None
    created_at: str
    updated_at: str


@dataclass
class MessageRow:
    id: str
    chat_id: str
    role: str
    content: str
    screenshot_relpath: str | None
    created_at: str
    seq: int

    @property
    def screenshot_path(self) -> Path | None:
        if not self.screenshot_relpath:
            return None
        # Resolved by ChatStore.read_screenshot / delete; keep name only here.
        return Path(self.screenshot_relpath)


class ChatStore:
    """Thread-safe SQLite store for chats / messages / prefs."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.chat_dir = self.db_path.parent
        self.screenshots_dir = self.chat_dir / "screenshots"
        self._local = threading.local()
        with _lock:
            conn = self._conn()
            _init_schema(conn)

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            self.chat_dir.mkdir(parents=True, exist_ok=True)
            self.screenshots_dir.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.Error:
                pass
            self._local.conn = conn
        return conn

    def get_pref(self, key: str, default: str | None = None) -> str | None:
        with _lock:
            row = self._conn().execute(
                "SELECT value FROM prefs WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return default
        return str(row["value"])

    def set_pref(self, key: str, value: str) -> None:
        with _lock:
            conn = self._conn()
            conn.execute(
                "INSERT INTO prefs(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            conn.commit()

    def active_chat_id(self) -> str | None:
        raw = (self.get_pref(PREF_ACTIVE_CHAT) or "").strip()
        if raw and self.get_chat(raw) is not None:
            return raw
        chats = self.list_chats(limit=1)
        return chats[0].id if chats else None

    def set_active_chat_id(self, chat_id: str | None) -> None:
        cid = (chat_id or "").strip()
        if not cid:
            return
        self.set_pref(PREF_ACTIVE_CHAT, cid)

    def list_chats(self, limit: int = 100) -> list[ChatRow]:
        with _lock:
            rows = self._conn().execute(
                "SELECT id, title, model_id, created_at, updated_at "
                "FROM chats ORDER BY updated_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [
            ChatRow(
                id=str(r["id"]),
                title=str(r["title"]),
                model_id=r["model_id"],
                created_at=str(r["created_at"]),
                updated_at=str(r["updated_at"]),
            )
            for r in rows
        ]

    def get_chat(self, chat_id: str) -> ChatRow | None:
        with _lock:
            r = self._conn().execute(
                "SELECT id, title, model_id, created_at, updated_at "
                "FROM chats WHERE id = ?",
                (chat_id,),
            ).fetchone()
        if r is None:
            return None
        return ChatRow(
            id=str(r["id"]),
            title=str(r["title"]),
            model_id=r["model_id"],
            created_at=str(r["created_at"]),
            updated_at=str(r["updated_at"]),
        )

    def create_chat(self, *, title: str = "New chat", model_id: str | None = None) -> ChatRow:
        chat_id = uuid.uuid4().hex
        now = _utc_now()
        with _lock:
            conn = self._conn()
            conn.execute(
                "INSERT INTO chats(id, title, model_id, created_at, updated_at) "
                "VALUES(?, ?, ?, ?, ?)",
                (chat_id, title, model_id, now, now),
            )
            conn.commit()
        return ChatRow(
            id=chat_id,
            title=title,
            model_id=model_id,
            created_at=now,
            updated_at=now,
        )

    def delete_chat(self, chat_id: str) -> None:
        """Remove chat, cascaded messages, and screenshot files for this chat."""
        msgs = self.list_messages(chat_id)
        rels = {m.screenshot_relpath for m in msgs if m.screenshot_relpath}
        with _lock:
            conn = self._conn()
            conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            conn.commit()
        shots_root = self.screenshots_dir.resolve()
        for rel in rels:
            path = (self.screenshots_dir / Path(rel).name).resolve()
            try:
                if path.is_file() and path.parent == shots_root:
                    path.unlink()
            except OSError:
                pass
        # Any leftover PNGs written as ``{chat_id}_*.png``.
        try:
            for path in self.screenshots_dir.glob(f"{chat_id}_*"):
                if path.is_file():
                    path.unlink()
        except OSError:
            pass

    def touch_chat(self, chat_id: str, *, title: str | None = None, model_id: str | None = None) -> None:
        fields: list[str] = ["updated_at = ?"]
        args: list[Any] = [_utc_now()]
        if title is not None:
            fields.append("title = ?")
            args.append(title)
        if model_id is not None:
            fields.append("model_id = ?")
            args.append(model_id)
        args.append(chat_id)
        with _lock:
            conn = self._conn()
            conn.execute(f"UPDATE chats SET {', '.join(fields)} WHERE id = ?", args)
            conn.commit()

    def list_messages(self, chat_id: str) -> list[MessageRow]:
        with _lock:
            rows = self._conn().execute(
                "SELECT id, chat_id, role, content, screenshot_relpath, created_at, seq "
                "FROM messages WHERE chat_id = ? ORDER BY seq ASC",
                (chat_id,),
            ).fetchall()
        return [_message_from_row(r) for r in rows]

    def list_recent_messages(self, chat_id: str, *, limit: int) -> list[MessageRow]:
        """Newest ``limit`` messages, returned oldest-first for display."""
        n = max(1, int(limit))
        with _lock:
            rows = self._conn().execute(
                "SELECT id, chat_id, role, content, screenshot_relpath, created_at, seq "
                "FROM messages WHERE chat_id = ? ORDER BY seq DESC LIMIT ?",
                (chat_id, n),
            ).fetchall()
        return [_message_from_row(r) for r in reversed(rows)]

    def next_seq(self, chat_id: str) -> int:
        with _lock:
            row = self._conn().execute(
                "SELECT COALESCE(MAX(seq), 0) AS m FROM messages WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        return int(row["m"] if row else 0) + 1

    def add_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        *,
        screenshot_relpath: str | None = None,
    ) -> MessageRow:
        msg_id = uuid.uuid4().hex
        now = _utc_now()
        with _lock:
            conn = self._conn()
            try:
                seq_row = conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) AS m FROM messages WHERE chat_id = ?",
                    (chat_id,),
                ).fetchone()
                seq = int(seq_row["m"] if seq_row else 0) + 1
                conn.execute(
                    "INSERT INTO messages(id, chat_id, role, content, screenshot_relpath, created_at, seq) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?)",
                    (msg_id, chat_id, role, content, screenshot_relpath, now, seq),
                )
                conn.execute(
                    "UPDATE inbox_meta SET history_rev = history_rev + 1 WHERE id = 1"
                )
                rev_row = conn.execute(
                    "SELECT history_rev FROM inbox_meta WHERE id = 1"
                ).fetchone()
                rev = int(rev_row["history_rev"]) if rev_row else 1
                if (role or "").strip().lower() == "assistant":
                    conn.execute(
                        "UPDATE inbox_meta SET assistant_rev = ? WHERE id = 1",
                        (rev,),
                    )
                    conn.execute(
                        "UPDATE chats SET updated_at = ?, inbox_rev = ?, assistant_rev = ? "
                        "WHERE id = ?",
                        (now, rev, rev, chat_id),
                    )
                else:
                    conn.execute(
                        "UPDATE chats SET updated_at = ?, inbox_rev = ? WHERE id = ?",
                        (now, rev, chat_id),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return MessageRow(
            id=msg_id,
            chat_id=chat_id,
            role=role,
            content=content,
            screenshot_relpath=screenshot_relpath,
            created_at=now,
            seq=seq,
        )

    def inbox_persist_view(self, *, since: int | None = None) -> dict[str, Any]:
        """Shared revision cursor: every process reads this after each poll."""
        since_n: int | None = None
        if since is not None:
            try:
                since_n = int(since)
            except (TypeError, ValueError):
                since_n = None
        with _lock:
            conn = self._conn()
            hist = conn.execute(
                "SELECT history_rev, assistant_rev FROM inbox_meta WHERE id = 1"
            ).fetchone()
            history_rev = int(hist["history_rev"]) if hist else 0
            assistant_rev = int(hist["assistant_rev"]) if hist else 0
            rows = conn.execute(
                "SELECT id, inbox_rev, assistant_rev FROM chats WHERE inbox_rev > 0"
            ).fetchall()
        chat_revs = {str(r["id"]): int(r["inbox_rev"]) for r in rows}
        assistant_revs = {
            str(r["id"]): int(r["assistant_rev"])
            for r in rows
            if int(r["assistant_rev"] or 0) > 0
        }
        if since_n is None:
            changed = list(chat_revs.keys())
            completed = [
                cid for cid, rev in assistant_revs.items() if rev == assistant_rev
            ]
        else:
            changed = [cid for cid, rev in chat_revs.items() if rev > since_n]
            completed = [cid for cid, rev in assistant_revs.items() if rev > since_n]
        return {
            "history_rev": history_rev,
            "assistant_rev": assistant_rev,
            "assistant_appended": len(completed),
            "appended_chat_ids": completed,
            "completed_chat_ids": completed,
            "chat_id": completed[-1] if completed else None,
            "chat_revs": chat_revs,
            "changed_chat_ids": changed,
        }

    def save_screenshot(self, chat_id: str, png: bytes) -> str:
        """Write PNG under screenshots/; return relative path stored in DB."""
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        name = f"{chat_id}_{uuid.uuid4().hex}.png"
        path = self.screenshots_dir / name
        path.write_bytes(png)
        return name

    def read_screenshot(self, relpath: str | None) -> bytes | None:
        if not relpath:
            return None
        path = self.screenshots_dir / relpath
        if not path.is_file():
            return None
        return path.read_bytes()


def _message_from_row(r: sqlite3.Row) -> MessageRow:
    return MessageRow(
        id=str(r["id"]),
        chat_id=str(r["chat_id"]),
        role=str(r["role"]),
        content=str(r["content"]),
        screenshot_relpath=r["screenshot_relpath"],
        created_at=str(r["created_at"]),
        seq=int(r["seq"]),
    )


def _clip(text: str, limit: int) -> str:
    body = (text or "").strip()
    if len(body) <= limit:
        return body
    cut = body[: limit - 1].rsplit("\n", 1)[0].rstrip()
    return (cut or body[: limit - 1]) + "…"


def _iso_age_hours(created_at: str) -> float | None:
    raw = (created_at or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600.0


def format_recent_chat_block(
    store: ChatStore,
    *,
    chat_id: str,
    current_utterance: str = "",
    limit: int = CHAT_HISTORY_LIMIT,
    char_budget: int = CHAT_HISTORY_CHAR_BUDGET,
    max_age_hours: float = CHAT_HISTORY_MAX_AGE_HOURS,
) -> str:
    """Last N desktop-chat messages for the orchestrator prompt (empty if none)."""
    cid = (chat_id or "").strip()
    if not cid:
        return ""
    take = max(1, int(limit))
    # Extra row so we can drop the in-flight user turn and still keep ``limit``.
    msgs = store.list_recent_messages(cid, limit=take + 1)
    if not msgs:
        return ""
    current = (current_utterance or "").strip()
    if (
        current
        and msgs[-1].role == "user"
        and (msgs[-1].content or "").strip() == current
    ):
        msgs = msgs[:-1]
    if max_age_hours > 0:
        msgs = [
            m
            for m in msgs
            if (age := _iso_age_hours(m.created_at)) is None or age <= max_age_hours
        ]
    msgs = msgs[-max(1, int(limit)) :]
    role_label = {"user": "User", "assistant": "Assistant", "system": "System"}
    lines: list[str] = []
    for m in msgs:
        body = (m.content or "").strip()
        if not body:
            body = "(screenshot attached)" if m.screenshot_relpath else ""
        if not body:
            continue
        label = role_label.get(m.role, m.role)
        lines.append(f"{label}: {_clip(body, CHAT_HISTORY_MSG_CHARS)}")
    if not lines:
        return ""
    blob = "\n".join(lines)
    return _clip(blob, int(char_budget))


def title_from_text(text: str, fallback: str = "New chat") -> str:
    line = (text or "").strip().replace("\n", " ")
    if not line:
        return fallback
    if len(line) > 48:
        return line[:45].rstrip() + "…"
    return line


_store: ChatStore | None = None


def get_store() -> ChatStore:
    global _store
    if _store is None:
        _store = ChatStore()
    return _store
