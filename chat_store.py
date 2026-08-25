"""Local SQLite chat history + screenshot files for the desktop chat UI."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
    conn.commit()


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
        return [
            MessageRow(
                id=str(r["id"]),
                chat_id=str(r["chat_id"]),
                role=str(r["role"]),
                content=str(r["content"]),
                screenshot_relpath=r["screenshot_relpath"],
                created_at=str(r["created_at"]),
                seq=int(r["seq"]),
            )
            for r in rows
        ]

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
        seq = self.next_seq(chat_id)
        with _lock:
            conn = self._conn()
            conn.execute(
                "INSERT INTO messages(id, chat_id, role, content, screenshot_relpath, created_at, seq) "
                "VALUES(?, ?, ?, ?, ?, ?, ?)",
                (msg_id, chat_id, role, content, screenshot_relpath, now, seq),
            )
            conn.execute(
                "UPDATE chats SET updated_at = ? WHERE id = ?",
                (now, chat_id),
            )
            conn.commit()
        return MessageRow(
            id=msg_id,
            chat_id=chat_id,
            role=role,
            content=content,
            screenshot_relpath=screenshot_relpath,
            created_at=now,
            seq=seq,
        )

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
