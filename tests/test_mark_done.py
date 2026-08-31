"""Tests for mark-done utterances and status flags."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app_status as st  # noqa: E402


class UtteranceTests(unittest.TestCase):
    def test_positive(self) -> None:
        for text in (
            "Mark it done",
            "mark done",
            "that's done",
            "no other action is required",
            "no further actions required",
            "nothing else needed",
            "that's all",
            "stop the task",
            "stop",
            "Stop!",
            "pause",
            "cancel",
        ):
            self.assertTrue(st.is_mark_done_utterance(text), text)

    def test_negative(self) -> None:
        for text in (
            "open notes",
            "mark this unread",
            "I'm not done yet",
            "continue the task",
            "stop listening",
            "stop the music",
            "don't stop",
        ):
            self.assertFalse(st.is_mark_done_utterance(text), text)


class FlagTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "status.json"
        self.patcher = patch.object(st, "STATUS_PATH", self.path)
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()
        self.tmp.cleanup()

    def test_request_and_consume(self) -> None:
        self.assertFalse(st.mark_done_pending("abc"))
        st.request_mark_done("abc")
        self.assertTrue(st.mark_done_pending("abc"))
        self.assertTrue(st.mark_done_pending())
        self.assertFalse(st.mark_done_pending("other"))
        self.assertTrue(st.consume_mark_done("abc"))
        self.assertFalse(st.mark_done_pending("abc"))

    def test_all_agents(self) -> None:
        st.request_mark_done(None)
        self.assertTrue(st.consume_mark_done("any-id"))

    def test_send_request_and_consume(self) -> None:
        self.assertFalse(st.send_pending())
        st.request_send()
        self.assertTrue(st.send_pending())
        self.assertTrue(st.consume_send())
        self.assertFalse(st.send_pending())
        self.assertFalse(st.consume_send())

    def test_stt_listening_clears_send_on_stop(self) -> None:
        st.request_send()
        st.set_stt_listening(True)
        self.assertFalse(st.send_pending())
        st.request_send()
        self.assertTrue(st.send_pending())
        st.set_stt_listening(False)
        self.assertFalse(st.send_pending())

    def test_cancel_request_and_consume(self) -> None:
        self.assertFalse(st.cancel_pending())
        st.request_cancel()
        self.assertTrue(st.cancel_pending())
        self.assertTrue(st.consume_cancel())
        self.assertFalse(st.cancel_pending())

    def test_cancel_clears_send_and_pending_utterances(self) -> None:
        st.enqueue_utterance("ignore me")
        st.request_send()
        st.request_cancel()
        self.assertFalse(st.send_pending())
        self.assertTrue(st.cancel_pending())
        self.assertIsNone(st.consume_utterance())

    def test_enqueue_and_consume_utterance(self) -> None:
        self.assertFalse(st.utterance_pending())
        st.enqueue_utterance("  play a song  ")
        self.assertTrue(st.utterance_pending())
        self.assertEqual(st.consume_utterance(), "play a song")
        self.assertEqual(st.reply_sink(), "mac")
        self.assertFalse(st.utterance_pending())
        self.assertIsNone(st.consume_utterance())

    def test_enqueue_with_sink_sets_reply_on_consume(self) -> None:
        st.enqueue_utterance("play a song", sink="phone")
        self.assertEqual(st.consume_utterance(), "play a song")
        self.assertEqual(st.reply_sink(), "phone")

    def test_enqueue_without_sink_switches_back_to_mac(self) -> None:
        st.set_reply_sink("phone")
        st.enqueue_utterance("from chat")
        self.assertEqual(st.consume_utterance(), "from chat")
        self.assertEqual(st.reply_sink(), "mac")

    def test_enqueue_tts_false_disables_reply_tts(self) -> None:
        st.set_reply_tts(True)
        st.enqueue_utterance("quiet chat", tts=False)
        self.assertEqual(st.consume_utterance(), "quiet chat")
        self.assertFalse(st.reply_tts_enabled())
        st.enqueue_utterance("speak please", tts=True)
        self.assertEqual(st.consume_utterance(), "speak please")
        self.assertTrue(st.reply_tts_enabled())

    def test_consume_speak_reenables_reply_tts(self) -> None:
        st.set_reply_tts(False)
        st.enqueue_speak("timer ding")
        self.assertEqual(st.consume_speak(), "timer ding")
        self.assertTrue(st.reply_tts_enabled())

    def test_utterance_queue_is_fifo(self) -> None:
        st.enqueue_utterance("one")
        st.enqueue_utterance("two")
        self.assertEqual(st.consume_utterance(), "one")
        self.assertEqual(st.consume_utterance(), "two")

    def test_log_llm_stores_full_reply(self) -> None:
        body = "A" * 500
        st.log_llm(body, source="llm")
        snap = st.read_status()
        self.assertEqual(snap["last_llm"], body)
        self.assertTrue(any("[llm]" in line and body[:80] in line for line in snap["logs"]))

    def test_write_phone_photo(self) -> None:
        photo = Path(self.tmp.name) / "phone-photo.jpg"
        with patch.object(st, "PHONE_PHOTO_PATH", photo):
            st.write_phone_photo(b"\xff\xd8\xff" + b"x" * 40, width=32, height=24)
            self.assertTrue(st.phone_photo_pending())
            blob = st.phone_photo_jpeg(consume_pending=True)
        self.assertEqual(blob[:3], b"\xff\xd8\xff")
        self.assertFalse(st.phone_photo_pending())
        snap = st.read_status()
        self.assertEqual(snap["phone_photo_width"], 32)
        self.assertTrue(snap["phone_photo_at"])

    def test_write_phone_speech_does_not_enqueue_utterance(self) -> None:
        speech = Path(self.tmp.name) / "phone-tts.wav"
        with patch.object(st, "PHONE_SPEECH_PATH", speech):
            st.write_phone_speech(b"RIFF" + b"xxxx" + b"WAVE")
            blob = st.read_phone_speech()
        self.assertTrue(blob.startswith(b"RIFF"))
        self.assertFalse(st.utterance_pending())
        self.assertTrue(st.read_status().get("speech_at"))

    def test_chat_inbox_from_spoken_when_overlay_on(self) -> None:
        st.set_chat_overlay_enabled(True)
        st.set_last_spoken("hello there")
        st.set_last_spoken("hello there")
        self.assertEqual(st.consume_chat_inbox(), ["hello there"])
        self.assertEqual(st.consume_chat_inbox(), [])

    def test_chat_inbox_skipped_when_overlay_off(self) -> None:
        st.set_chat_overlay_enabled(False)
        st.set_last_spoken("secret")
        self.assertEqual(st.consume_chat_inbox(), [])

    def test_concurrent_writes_use_unique_temp_files(self) -> None:
        import concurrent.futures

        def bump(i: int) -> None:
            with st._lock:
                data = st._read()
                data["detail"] = f"n={i}"
                st._write(data)

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(bump, range(60)))
        self.assertIn("detail", st.read_status())


if __name__ == "__main__":
    unittest.main()
