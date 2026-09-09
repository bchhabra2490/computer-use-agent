"""Chat bridge persists spoken inbox to SQLite without the UI."""

from __future__ import annotations

import json
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

    def test_persist_routes_reply_to_originating_chat(self) -> None:
        first = self.store.create_chat(title="First")
        second = self.store.create_chat(title="Second")
        self.store.set_active_chat_id(second.id)
        st.set_chat_overlay_enabled(True)
        st.enqueue_utterance("question", source="chat", chat_id=first.id)
        self.assertEqual(st.consume_utterance(), "question")
        st.set_last_spoken("answer for first")

        out = cb.persist_chat_inbox()

        self.assertEqual(out["chat_ids"], [first.id])
        self.assertEqual(
            [m.content for m in self.store.list_messages(first.id)],
            ["answer for first"],
        )
        self.assertEqual(self.store.list_messages(second.id), [])

    def test_empty_persist_does_not_write_status(self) -> None:
        before = cb.inbox_persist_view()["history_rev"]
        with patch.object(st, "_write") as write:
            out = cb.persist_chat_inbox()
        self.assertEqual(out["appended"], 0)
        write.assert_not_called()
        self.assertEqual(cb.inbox_persist_view()["history_rev"], before)

    def test_persist_bumps_history_rev_without_status_get(self) -> None:
        before = cb.inbox_persist_view()["history_rev"]
        st.set_chat_overlay_enabled(True)
        st.set_last_spoken("rev bump")
        self.assertEqual(cb.inbox_persist_view()["history_rev"], before)
        out = cb.persist_chat_inbox()
        after = cb.inbox_persist_view()
        self.assertEqual(out["appended"], 1)
        self.assertEqual(after["history_rev"], before + 1)
        self.assertEqual(after["assistant_appended"], 1)
        self.assertEqual(after["appended_chat_ids"], [out["chat_id"]])
        self.assertEqual(after["chat_revs"].get(out["chat_id"]), after["history_rev"])

    def test_second_persist_keeps_earlier_chat_rev(self) -> None:
        first = self.store.create_chat(title="First")
        second = self.store.create_chat(title="Second")
        st.set_chat_overlay_enabled(True)
        st.enqueue_utterance("q1", source="chat", chat_id=first.id)
        self.assertEqual(st.consume_utterance(), "q1")
        st.set_last_spoken("answer A")
        cb.persist_chat_inbox()
        st.enqueue_utterance("q2", source="chat", chat_id=second.id)
        self.assertEqual(st.consume_utterance(), "q2")
        st.set_last_spoken("answer B")
        cb.persist_chat_inbox()
        view = cb.inbox_persist_view()
        self.assertEqual(view["appended_chat_ids"], [second.id])
        self.assertIn(first.id, view["chat_revs"])
        self.assertIn(second.id, view["chat_revs"])
        self.assertLess(view["chat_revs"][first.id], view["chat_revs"][second.id])
        after_a = cb.inbox_persist_view(since=view["chat_revs"][first.id])
        self.assertIn(second.id, after_a["changed_chat_ids"])
        self.assertNotIn(first.id, after_a["changed_chat_ids"])
        missed_poll = cb.inbox_persist_view(since=view["chat_revs"][first.id] - 1)
        self.assertIn(first.id, missed_poll["changed_chat_ids"])
        self.assertIn(second.id, missed_poll["changed_chat_ids"])

    def test_agent_message_posts_to_active_chat(self) -> None:
        chat = self.store.create_chat(title="Mine")
        self.store.set_active_chat_id(chat.id)
        before = cb.inbox_persist_view()

        out = cb.post_assistant_message("Results: **done**", store=self.store)

        self.assertEqual(out["chat_id"], chat.id)
        self.assertFalse(out["opened"])
        msgs = self.store.list_messages(chat.id)
        self.assertEqual([(m.role, m.content) for m in msgs], [("assistant", "Results: **done**")])
        after = cb.inbox_persist_view()
        self.assertEqual(after["history_rev"], before["history_rev"] + 1)
        self.assertEqual(after["chat_revs"].get(chat.id), after["history_rev"])

    def test_agent_message_creates_chat_when_none(self) -> None:
        out = cb.post_assistant_message("A standalone update", store=self.store)

        self.assertTrue(out["chat_id"])
        self.assertEqual(self.store.active_chat_id(), out["chat_id"])
        self.assertEqual(self.store.list_messages(out["chat_id"])[0].content, "A standalone update")

    def test_bridge_id_is_stable_until_process_reset(self) -> None:
        first = cb.inbox_persist_view()["bridge_id"]
        self.assertTrue(first)
        self.assertEqual(cb.inbox_persist_view()["bridge_id"], first)

    def test_bridge_restart_restores_rev_and_changes_instance_id(self) -> None:
        st.set_chat_overlay_enabled(True)
        st.set_last_spoken("before restart")
        out = cb.persist_chat_inbox()
        before = cb.inbox_persist_view()
        saved = before["history_rev"]
        old_id = before["bridge_id"]
        chat_id = out["chat_id"]
        self.assertGreaterEqual(saved, 1)

        cb.reset_inbox_persist_process()
        after = cb.inbox_persist_view()
        self.assertEqual(after["history_rev"], saved)
        self.assertEqual(after["chat_revs"].get(chat_id), saved)
        self.assertNotEqual(after["bridge_id"], old_id)
        stale = cb.inbox_persist_view(since=saved)
        self.assertNotIn(chat_id, stale["changed_chat_ids"])

        st.set_last_spoken("after restart")
        cb.persist_chat_inbox()
        resumed = cb.inbox_persist_view(since=saved)
        self.assertEqual(resumed["history_rev"], saved + 1)
        self.assertIn(chat_id, resumed["changed_chat_ids"])

    def test_other_process_write_is_visible_without_rehydrate(self) -> None:
        before = cb.inbox_persist_view()
        self.assertEqual(before["history_rev"], 0)
        other = ChatStore(db_path=self.store.db_path)
        chat = other.create_chat(title="Orchestrator")
        other.add_message(chat.id, "assistant", "from another process")
        stale_if_cached = cb.inbox_persist_view(since=0)
        self.assertEqual(stale_if_cached["history_rev"], 1)
        self.assertIn(chat.id, stale_if_cached["changed_chat_ids"])
        self.assertEqual(stale_if_cached["chat_revs"].get(chat.id), 1)

    def test_migrates_json_inbox_prefs_into_sqlite(self) -> None:
        chat = self.store.create_chat(title="Legacy")
        self.store.set_pref("inbox_history_rev", "7")
        self.store.set_pref("inbox_chat_revs", json.dumps({chat.id: 7}))
        migrated = ChatStore(db_path=self.store.db_path)
        view = migrated.inbox_persist_view()
        self.assertEqual(view["history_rev"], 7)
        self.assertEqual(view["chat_revs"].get(chat.id), 7)
        self.assertIsNone(self.store.get_pref("inbox_history_rev"))
        self.assertIsNone(self.store.get_pref("inbox_chat_revs"))

    def test_user_message_does_not_count_as_assistant_completion(self) -> None:
        chat = self.store.create_chat(title="Mine")
        self.store.add_message(chat.id, "user", "hello")
        view = cb.inbox_persist_view(since=0)
        self.assertEqual(view["history_rev"], 1)
        self.assertEqual(view["assistant_rev"], 0)
        self.assertEqual(view["assistant_appended"], 0)
        self.assertIn(chat.id, view["changed_chat_ids"])
        self.assertNotIn(chat.id, view["completed_chat_ids"])
        self.assertEqual(view["appended_chat_ids"], [])

        self.store.add_message(chat.id, "assistant", "hi there")
        done = cb.inbox_persist_view(since=1)
        self.assertEqual(done["history_rev"], 2)
        self.assertEqual(done["assistant_rev"], 2)
        self.assertEqual(done["assistant_appended"], 1)
        self.assertIn(chat.id, done["changed_chat_ids"])
        self.assertIn(chat.id, done["completed_chat_ids"])
        self.assertEqual(done["appended_chat_ids"], [chat.id])


if __name__ == "__main__":
    unittest.main()
