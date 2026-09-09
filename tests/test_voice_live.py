"""Persistent CLI live-voice session: wake keeps the Realtime socket open."""
from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from voice_live import (  # noqa: E402
    LiveVoiceSession,
    is_live_shutdown,
    looks_like_tts_echo,
)


class FakeEvent:
    def __init__(self, **fields):
        self.__dict__.update(fields)


class FakeConnection:
    def __init__(self):
        self.events = []
        self.closed = False
        self.session = MagicMock()
        self.input_audio_buffer = MagicMock()
        self._gate = threading.Event()

    def __iter__(self):
        self._gate.wait(2)
        yield from self.events

    def close(self):
        self.closed = True
        self._gate.set()


class LiveVoiceTests(unittest.TestCase):
    def test_shutdown_phrases(self):
        self.assertTrue(is_live_shutdown("Stop listening."))
        self.assertTrue(is_live_shutdown("that's all"))
        self.assertTrue(is_live_shutdown("Go to sleep"))
        self.assertFalse(is_live_shutdown("open notes"))
        self.assertFalse(is_live_shutdown("stop"))

    def test_completed_transcript_is_queued(self):
        conn = FakeConnection()
        conn.events = [
            FakeEvent(type="conversation.item.input_audio_transcription.delta", delta="open "),
            FakeEvent(type="conversation.item.input_audio_transcription.completed", transcript="open notes"),
        ]
        session = LiveVoiceSession(MagicMock(), idle=30)
        with patch("wake.pause_persistent_wake"), patch("wake.resume_persistent_wake"):
            session.start(connection=conn, capture=False)
            conn._gate.set()
            heard = session.wait_utterance()
            session.close()
        self.assertEqual(heard, "open notes")

    def test_shutdown_phrase_closes_without_yielding(self):
        conn = FakeConnection()
        conn.events = [
            FakeEvent(
                type="conversation.item.input_audio_transcription.completed",
                transcript="stop listening",
            )
        ]
        session = LiveVoiceSession(MagicMock(), idle=30)
        with patch("wake.pause_persistent_wake"), patch("wake.resume_persistent_wake"):
            session.start(connection=conn, capture=False)
            conn._gate.set()
            heard = session.wait_utterance()
        self.assertIsNone(heard)
        self.assertFalse(session.alive)

    def test_idle_timeout_closes(self):
        conn = FakeConnection()
        session = LiveVoiceSession(MagicMock(), idle=0.2)
        with patch("wake.pause_persistent_wake"), patch("wake.resume_persistent_wake"):
            session.start(connection=conn, capture=False)
            heard = session.wait_utterance()
        self.assertIsNone(heard)
        self.assertFalse(session.alive)

    def test_speech_started_sets_barge_event(self):
        conn = FakeConnection()
        session = LiveVoiceSession(MagicMock(), idle=30)
        with patch("wake.pause_persistent_wake"), patch("wake.resume_persistent_wake"):
            session.start(connection=conn, capture=False)
            session._on_event(FakeEvent(type="input_audio_buffer.speech_started"))
            self.assertTrue(session.barge.is_set())
            session.close()

    def test_tts_echo_is_not_barge_or_utterance(self):
        self.assertTrue(
            looks_like_tts_echo("The capital of", "The capital of India is New Delhi.")
        )
        self.assertTrue(
            looks_like_tts_echo("India's capital", "The capital of India is New Delhi.")
        )
        self.assertTrue(
            looks_like_tts_echo(
                "I asked the capital of India",
                "The capital of India is New Delhi.",
            )
        )
        self.assertFalse(
            looks_like_tts_echo("stop", "The capital of India is New Delhi.")
        )
        conn = FakeConnection()
        session = LiveVoiceSession(MagicMock(), idle=30)
        with patch("wake.pause_persistent_wake"), patch("wake.resume_persistent_wake"):
            session.start(connection=conn, capture=False)
            session.note_tts("The capital of India is New Delhi.")
            session.on_tts_playback_start()
            session._on_event(FakeEvent(type="input_audio_buffer.speech_started"))
            self.assertFalse(session.barge.is_set())
            session._on_event(
                FakeEvent(
                    type="conversation.item.input_audio_transcription.completed",
                    transcript="The capital of",
                )
            )
            self.assertTrue(session._utterances.empty())
            session._on_event(
                FakeEvent(
                    type="conversation.item.input_audio_transcription.completed",
                    transcript="wait stop talking",
                )
            )
            self.assertTrue(session.barge.is_set())
            self.assertEqual(session._utterances.get_nowait(), "wait stop talking")
            session.close()

    def test_idle_waits_until_after_tts(self):
        conn = FakeConnection()
        session = LiveVoiceSession(MagicMock(), idle=0.25)
        with patch("wake.pause_persistent_wake"), patch("wake.resume_persistent_wake"):
            session.start(connection=conn, capture=False)
            session.on_tts_playback_start()
            session._idle_anchor = time.monotonic() - 5.0
            waiter = threading.Thread(target=session.wait_utterance)
            waiter.start()
            waiter.join(0.4)
            self.assertTrue(session.alive)
            self.assertTrue(waiter.is_alive())
            session.on_tts_playback_end()
            waiter.join(0.15)
            self.assertTrue(session.alive)
            waiter.join(0.4)
            self.assertFalse(session.alive)
            self.assertFalse(waiter.is_alive())


if __name__ == "__main__":
    unittest.main()
