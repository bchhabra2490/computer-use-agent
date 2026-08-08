"""Unit tests for low-latency streaming TTS public API and helpers."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["TTS_CHUNK_MIN_CHARS"] = "20"
os.environ["TTS_CHUNK_MAX_CHARS"] = "100"
os.environ["TTS_WARMUP"] = "0"
os.environ["TTS_KEYBOARD_BARGE"] = "0"

from low_latency_tts import (  # noqa: E402
    LowLatencyTTS,
    decoded_message_prefix,
    extract_message_field,
)


def _engine() -> LowLatencyTTS:
    return LowLatencyTTS(MagicMock(), ROOT)


class DecodedMessagePrefixTests(unittest.TestCase):
    def test_partial_and_complete(self) -> None:
        self.assertEqual(decoded_message_prefix(""), "")
        self.assertEqual(
            decoded_message_prefix('{"message":"Hello, how are'),
            "Hello, how are",
        )
        self.assertEqual(
            extract_message_field('{"message":"All set.","end_session":false}'),
            "All set.",
        )


class PublicApiTests(unittest.TestCase):
    @patch("low_latency_tts.play_wav")
    @patch("low_latency_tts.synthesize", return_value=b"RIFF....")
    def test_start_add_stop(self, _synth, play) -> None:
        eng = _engine()
        try:
            self.assertTrue(callable(eng.start_stream))
            self.assertTrue(callable(eng.add_text_chunk))
            self.assertTrue(callable(eng.stop_stream))
            eng.start_stream("r1")
            eng.bind_call("r1", "c1")
            eng.add_text_chunk("This is a longer first sentence. ")
            eng.add_text_chunk("And more text follows here.")
            eng.stop_stream()
            self.assertTrue(eng.took_call("c1"))
            eng.wait_call("c1", timeout=2.0)
            eng.acknowledge_call("c1")
            self.assertTrue(play.called)
        finally:
            eng.close()

    @patch("low_latency_tts.play_wav")
    @patch("low_latency_tts.synthesize", return_value=b"RIFF....")
    def test_abandon_clears_streamed_flag(self, _synth, _play) -> None:
        eng = _engine()
        try:
            eng.start_stream("r2")
            eng.bind_call("r2", "c2")
            eng.add_text_chunk("This is a longer first sentence. And more.")
            eng.abandon("r2")
            self.assertFalse(eng.took_call("c2"))
        finally:
            eng.close()

    @patch("low_latency_tts.play_wav")
    @patch("low_latency_tts.synthesize", return_value=b"RIFF....")
    def test_close_joins_workers(self, _synth, _play) -> None:
        eng = _engine()
        eng.close()
        self.assertFalse(eng._synth_thread.is_alive())
        self.assertFalse(eng._play_thread.is_alive())

    @patch("low_latency_tts.play_wav")
    @patch("low_latency_tts.synthesize", return_value=b"RIFF....")
    def test_logs_chunk_available_and_first_audio(self, _synth, play) -> None:
        log_dir = ROOT / ".runtime" / "tts-test"
        log_dir.mkdir(parents=True, exist_ok=True)
        eng = LowLatencyTTS(MagicMock(), log_dir)
        try:
            if eng.log_path.exists():
                eng.log_path.unlink()
            eng.start_stream("r3")
            eng.bind_call("r3", "c3")
            msg = "Hello there, this is enough text for one chunk already!"
            # Stream like the Responses API (growing deltas).
            prev = 0
            for i in range(12, len(msg) + 1, 10):
                eng.add_text_chunk(msg[prev:i])
                prev = i
            if prev < len(msg):
                eng.add_text_chunk(msg[prev:])
            eng.stop_stream()
            eng.wait_call("c3", timeout=2.0)
            eng.acknowledge_call("c3")
            self.assertTrue(play.called)
            text = eng.log_path.read_text(encoding="utf-8")
            self.assertIn("event=chunk_available", text)
            self.assertIn("event=first_audio_play", text)
        finally:
            eng.close()


if __name__ == "__main__":
    unittest.main()
