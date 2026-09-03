"""Chat bridge persists spoken inbox to SQLite without the UI."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app_status as st  # noqa: E402
import chat_bridge as cb  # noqa: E402
from chat_store import ChatStore  # noqa: E402


class PersistInboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.status = root / "status.json"
        self.store = ChatStore(db_path=root / "chats.sqlite3")
        self._patches = [
            patch.object(st, "STATUS_PATH", self.status),
            patch.object(st, "RUNTIME_DIR", root),
            patch.object(cb, "get_store", return_value=self.store),
        ]
        for p in self._patches:
            p.start()
        self.status.write_text("{}", encoding="utf-8")

    def tearDown(self) -> None:
        for p in reversed(self._patches):
            p.stop()
        self.tmp.cleanup()

    def test_persist_writes_assistant_messages(self) -> None:
        chat = self.store.create_chat(title="Mine")
        self.store.set_active_chat_id(chat.id)
        st.set_chat_overlay_enabled(True)
        st.set_last_spoken("first reply")
        st.set_last_spoken("second reply")

        out = cb.persist_chat_inbox()
        self.assertEqual(out["appended"], 2)
        self.assertEqual(out["chat_id"], chat.id)
        msgs = self.store.list_messages(chat.id)
        self.assertEqual([m.role for m in msgs], ["assistant", "assistant"])
        self.assertEqual([m.content for m in msgs], ["first reply", "second reply"])
        self.assertEqual(st.consume_chat_inbox(), [])

    def test_persist_creates_chat_when_none(self) -> None:
        st.set_chat_overlay_enabled(True)
        st.set_last_spoken("orphan reply")
        out = cb.persist_chat_inbox()
        self.assertEqual(out["appended"], 1)
        self.assertTrue(out["chat_id"])
        msgs = self.store.list_messages(out["chat_id"])
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].content, "orphan reply")

    def test_agent_message_posts_to_active_chat(self) -> None:
        chat = self.store.create_chat(title="Mine")
        self.store.set_active_chat_id(chat.id)

        out = cb.post_assistant_message("Results: **done**", store=self.store)

        self.assertEqual(out["chat_id"], chat.id)
        self.assertFalse(out["opened"])
        msgs = self.store.list_messages(chat.id)
        self.assertEqual([(m.role, m.content) for m in msgs], [("assistant", "Results: **done**")])

    def test_agent_message_creates_chat_when_none(self) -> None:
        out = cb.post_assistant_message("A standalone update", store=self.store)

        self.assertTrue(out["chat_id"])
        self.assertEqual(self.store.active_chat_id(), out["chat_id"])
        self.assertEqual(self.store.list_messages(out["chat_id"])[0].content, "A standalone update")


if __name__ == "__main__":
    unittest.main()
