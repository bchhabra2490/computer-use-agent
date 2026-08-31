"""Chat store + Electron launcher helpers (no AppKit / no network)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from chat_bridge import command_for_orchestrator as bridge_cmd  # noqa: E402
from chat_overlay import (  # noqa: E402
    chat_overlay_enabled,
    chat_should_show,
    command_for_orchestrator,
    relative_chat_time,
)
from chat_store import ChatStore, PREF_SELECTED_MODEL, title_from_text  # noqa: E402


class OrchestratorCommandTests(unittest.TestCase):
    def test_plain_text(self) -> None:
        self.assertEqual(command_for_orchestrator("open notes", look_at_screen=False), "open notes")
        self.assertEqual(bridge_cmd("open notes", look_at_screen=False), "open notes")

    def test_look_at_screen(self) -> None:
        self.assertEqual(
            command_for_orchestrator("what is this", look_at_screen=True),
            "Look at the attached screenshot. what is this",
        )
        self.assertEqual(
            command_for_orchestrator("  ", look_at_screen=True),
            "Look at the attached screenshot and tell me what you see.",
        )


class TitleTests(unittest.TestCase):
    def test_title_from_text(self) -> None:
        self.assertEqual(title_from_text("hello"), "hello")
        self.assertTrue(title_from_text("x" * 60).endswith("…"))


class ChatStoreTests(unittest.TestCase):
    def test_chat_roundtrip_and_screenshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ChatStore(Path(tmp) / "t.sqlite3")
            chat = store.create_chat(title="New chat", model_id="orchestrator")
            rel = store.save_screenshot(chat.id, b"\x89PNG\r\n")
            store.add_message(chat.id, "user", "hi", screenshot_relpath=rel)
            store.add_message(chat.id, "assistant", "hello")
            store.touch_chat(chat.id, title="hi")
            store.set_pref(PREF_SELECTED_MODEL, "openai:gpt-4o")
            self.assertEqual(store.get_pref(PREF_SELECTED_MODEL), "openai:gpt-4o")
            msgs = store.list_messages(chat.id)
            self.assertEqual(len(msgs), 2)
            self.assertEqual(msgs[0].screenshot_relpath, rel)
            self.assertEqual(store.read_screenshot(rel), b"\x89PNG\r\n")
            listed = store.list_chats()
            self.assertEqual(listed[0].title, "hi")

    def test_delete_chat_removes_messages_and_screenshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ChatStore(Path(tmp) / "t.sqlite3")
            keep = store.create_chat(title="keep")
            gone = store.create_chat(title="gone")
            rel = store.save_screenshot(gone.id, b"\x89PNG gone")
            orphan = store.screenshots_dir / f"{gone.id}_orphan.png"
            orphan.write_bytes(b"orphan")
            store.add_message(gone.id, "user", "bye", screenshot_relpath=rel)
            store.add_message(keep.id, "user", "stay")
            store.delete_chat(gone.id)
            self.assertIsNone(store.get_chat(gone.id))
            self.assertEqual(store.list_messages(gone.id), [])
            self.assertFalse((store.screenshots_dir / rel).exists())
            self.assertFalse(orphan.exists())
            self.assertEqual(store.get_chat(keep.id).title, "keep")
            self.assertEqual(len(store.list_messages(keep.id)), 1)


class RelativeTimeTests(unittest.TestCase):
    def test_just_now_and_minutes(self) -> None:
        from datetime import datetime, timedelta, timezone

        now = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(relative_chat_time(now.isoformat(), now=now), "Just now")
        self.assertEqual(
            relative_chat_time((now - timedelta(minutes=5)).isoformat(), now=now),
            "5m ago",
        )
        self.assertEqual(
            relative_chat_time((now - timedelta(hours=3)).isoformat(), now=now),
            "3h ago",
        )
        self.assertEqual(
            relative_chat_time((now - timedelta(days=1)).isoformat(), now=now),
            "Yesterday",
        )


class ChatToggleTests(unittest.TestCase):
    def test_enabled_from_status(self) -> None:
        with patch.dict("os.environ", {"CHAT_OVERLAY": "0"}, clear=False):
            self.assertFalse(chat_overlay_enabled({}))
            self.assertTrue(chat_overlay_enabled({"chat_overlay_enabled": True}))
            self.assertFalse(chat_overlay_enabled({"chat_overlay_enabled": False}))

    def test_hidden_during_capture(self) -> None:
        self.assertFalse(
            chat_should_show(
                {
                    "chat_overlay_enabled": True,
                    "overlay_hidden": True,
                }
            )
        )
        self.assertTrue(
            chat_should_show(
                {
                    "chat_overlay_enabled": True,
                    "overlay_hidden": False,
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
