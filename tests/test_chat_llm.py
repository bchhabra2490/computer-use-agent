"""Desktop chat request shaping + SQLite store (no AppKit / no network)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from chat_llm import (  # noqa: E402
    CHAT_DEEPSEEK_VISION_MODEL,
    CHAT_MODEL,
    ChatSession,
    api_model_name,
    chat_backend,
    chat_model,
    complete_chat,
    extract_output_text,
    generate_chat_title,
    get_model,
    list_chat_models,
    make_chat_client,
    session_input,
    title_from_text,
    user_content,
    _clean_title,
)
from chat_overlay import chat_overlay_enabled, chat_should_show  # noqa: E402
from chat_store import ChatStore, PREF_SELECTED_MODEL  # noqa: E402


class UserContentTests(unittest.TestCase):
    def test_text_only_is_plain_string(self) -> None:
        self.assertEqual(user_content("hello", None), "hello")

    def test_screenshot_is_multipart(self) -> None:
        parts = user_content("what is this", b"\x89PNG")
        self.assertIsInstance(parts, list)
        kinds = [p["type"] for p in parts]
        self.assertEqual(kinds, ["input_text", "input_image"])
        self.assertTrue(parts[1]["image_url"].startswith("data:image/png;base64,"))


class SessionInputTests(unittest.TestCase):
    def test_includes_history_then_new_turn(self) -> None:
        session = ChatSession()
        session.add("user", "hi")
        session.add("assistant", "hello")
        payload = session_input(session, "next", None)
        roles = [item["role"] for item in payload]
        self.assertEqual(roles, ["system", "user", "assistant", "user"])
        self.assertEqual(payload[-1]["content"], "next")


class ExtractTextTests(unittest.TestCase):
    def test_output_text_parts(self) -> None:
        part = SimpleNamespace(type="output_text", text="  hi  ")
        msg = SimpleNamespace(type="message", content=[part])
        resp = SimpleNamespace(output=[msg], output_text=None)
        self.assertEqual(extract_output_text(resp), "hi")


class CompleteChatTests(unittest.TestCase):
    def test_appends_turns(self) -> None:
        part = SimpleNamespace(type="output_text", text="On Notes.")
        msg = SimpleNamespace(type="message", content=[part])
        client = MagicMock()
        client.responses.create.return_value = SimpleNamespace(output=[msg])
        session = ChatSession()
        reply = complete_chat(client, session, "What's open?", None)
        self.assertEqual(reply, "On Notes.")
        self.assertEqual([t.role for t in session.turns], ["user", "assistant"])
        client.responses.create.assert_called_once()
        kwargs = client.responses.create.call_args.kwargs
        self.assertEqual(kwargs["model"], CHAT_MODEL)

    def test_deepseek_uses_vision_model_when_screenshot(self) -> None:
        part = SimpleNamespace(type="output_text", text="Notes.")
        msg = SimpleNamespace(type="message", content=[part])
        client = MagicMock()
        client.responses.create.return_value = SimpleNamespace(output=[msg])
        complete_chat(client, ChatSession(), "what", b"png", backend="deepseek")
        self.assertEqual(
            client.responses.create.call_args.kwargs["model"],
            CHAT_DEEPSEEK_VISION_MODEL,
        )


class ChatBackendTests(unittest.TestCase):
    def test_aliases(self) -> None:
        self.assertEqual(chat_backend("ds"), "deepseek")
        self.assertEqual(chat_backend("openai"), "openai")

    def test_models(self) -> None:
        self.assertEqual(chat_model("openai", has_image=True), CHAT_MODEL)
        self.assertNotEqual(
            chat_model("deepseek", has_image=True),
            chat_model("deepseek", has_image=False),
        )
        self.assertEqual(chat_model("deepseek", has_image=True), CHAT_DEEPSEEK_VISION_MODEL)

    def test_catalog(self) -> None:
        models = list_chat_models()
        self.assertGreaterEqual(len(models), 4)
        ids = {m.id for m in models}
        self.assertTrue(any(i.startswith("openai:") for i in ids))
        self.assertTrue(any(i.startswith("deepseek:") for i in ids))

    def test_api_model_upgrade(self) -> None:
        info = get_model("deepseek:deepseek-v4-flash")
        self.assertFalse(info.vision)
        self.assertEqual(api_model_name(info, has_image=True), CHAT_DEEPSEEK_VISION_MODEL)

    def test_make_client_deepseek(self) -> None:
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-test"}, clear=False):
            with patch("openai.OpenAI") as ctor:
                make_chat_client("deepseek")
                ctor.assert_called_once()
                kwargs = ctor.call_args.kwargs
                self.assertEqual(kwargs["api_key"], "sk-test")
                self.assertEqual(kwargs["base_url"], "https://api.deepseek.com")

    def test_title_from_text(self) -> None:
        self.assertEqual(title_from_text("hello"), "hello")
        self.assertTrue(title_from_text("x" * 60).endswith("…"))

    def test_clean_title_strips_quotes(self) -> None:
        self.assertEqual(_clean_title('"Notes app status"'), "Notes app status")
        self.assertEqual(_clean_title("## Hello world"), "Hello world")

    def test_generate_chat_title_uses_model(self) -> None:
        part = SimpleNamespace(type="output_text", text='"Desktop notes"')
        msg = SimpleNamespace(type="message", content=[part])
        client = MagicMock()
        client.responses.create.return_value = SimpleNamespace(output=[msg])
        title = generate_chat_title(
            client,
            model_id="openai:gpt-4o-mini",
            user_text="what's on screen",
            assistant_text="Notes is open.",
        )
        self.assertEqual(title, "Desktop notes")
        client.responses.create.assert_called_once()

    def test_generate_chat_title_falls_back(self) -> None:
        client = MagicMock()
        client.responses.create.side_effect = RuntimeError("nope")
        title = generate_chat_title(
            client, model_id="openai:gpt-4o-mini", user_text="open calendar"
        )
        self.assertEqual(title, "open calendar")


class ChatStoreTests(unittest.TestCase):
    def test_chat_roundtrip_and_screenshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ChatStore(Path(tmp) / "t.sqlite3")
            chat = store.create_chat(title="New chat", model_id="openai:gpt-4o-mini")
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
