"""Chat store + overlay helpers (no AppKit / no network)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from chat_overlay import (  # noqa: E402
    AVATAR_SIZE,
    BUBBLE_PAD_X,
    STACK_PAD,
    _bubble_text_max_width,
    chat_overlay_enabled,
    chat_should_show,
    command_for_orchestrator,
)
from chat_store import ChatStore, PREF_SELECTED_MODEL, title_from_text  # noqa: E402


class OrchestratorCommandTests(unittest.TestCase):
    def test_plain_text(self) -> None:
        self.assertEqual(command_for_orchestrator("open notes", look_at_screen=False), "open notes")

    def test_look_at_screen(self) -> None:
        self.assertEqual(
            command_for_orchestrator("what is this", look_at_screen=True),
            "Look at the current screen. what is this",
        )
        self.assertEqual(
            command_for_orchestrator("  ", look_at_screen=True),
            "Look at the current screen and tell me what you see.",
        )


class BubbleLayoutTests(unittest.TestCase):
    def test_long_text_uses_almost_full_row(self) -> None:
        row = 800.0
        text_w = _bubble_text_max_width(row)
        bubble_w = text_w + 2 * BUBBLE_PAD_X
        used = STACK_PAD * 2 + AVATAR_SIZE + 8.0 + bubble_w
        self.assertAlmostEqual(used, row, places=4)
        self.assertGreater(text_w, 600.0)
        self.assertGreater(text_w, row * 0.7)

    def test_narrow_row_still_has_readable_width(self) -> None:
        self.assertGreaterEqual(_bubble_text_max_width(200.0), 80.0)


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


class ChatAliveTests(unittest.TestCase):
    def test_dead_without_window(self) -> None:
        from chat_overlay import ChatOverlay

        ov = ChatOverlay.__new__(ChatOverlay)
        ov.window = None
        ov._closed = False
        self.assertFalse(ov.is_alive())
        ov._closed = True
        ov.window = object()
        self.assertFalse(ov.is_alive())


class RelativeTimeTests(unittest.TestCase):
    def test_just_now_and_minutes(self) -> None:
        from datetime import datetime, timedelta, timezone

        from chat_overlay import relative_chat_time

        now = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(
            relative_chat_time(now.isoformat(), now=now),
            "Just now",
        )
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
        with patch("chat_overlay.pid_alive", return_value=True):
            self.assertFalse(
                chat_should_show(
                    {
                        "chat_overlay_enabled": True,
                        "overlay_hidden": True,
                        "tray_pid": 1,
                    }
                )
            )
            self.assertTrue(
                chat_should_show(
                    {
                        "chat_overlay_enabled": True,
                        "overlay_hidden": False,
                        "tray_pid": 1,
                    }
                )
            )


if __name__ == "__main__":
    unittest.main()
