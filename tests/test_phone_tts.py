"""Phone reply sink: synthesize on Mac, skip afplay, publish WAV."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app_status as st  # noqa: E402
import tts  # noqa: E402


def _silence_wav(*, frames: int = 80, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"\x00\x00" * frames)
    return buf.getvalue()


class PhoneTtsSinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.status = Path(self.tmp.name) / "status.json"
        self.speech = Path(self.tmp.name) / "phone-tts.wav"
        self.patches = [
            patch.object(st, "STATUS_PATH", self.status),
            patch.object(st, "PHONE_SPEECH_PATH", self.speech),
            patch.object(st, "RUNTIME_DIR", Path(self.tmp.name)),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def test_play_wav_phone_publishes_and_skips_speakers(self) -> None:
        wav = _silence_wav()
        st.set_reply_sink("phone")
        with (
            patch.object(tts, "_play_afplay") as afplay,
            patch.object(tts, "_play_sounddevice") as sd,
        ):
            interrupted = tts.play_wav(wav)
        self.assertFalse(interrupted)
        afplay.assert_not_called()
        sd.assert_not_called()
        self.assertEqual(st.read_phone_speech(), wav)
        self.assertTrue(st.read_status().get("speech_at"))
        self.assertFalse(st.utterance_pending())

    def test_play_wav_mac_uses_player(self) -> None:
        wav = _silence_wav()
        st.set_reply_sink("mac")
        with (
            patch.object(tts, "_play_afplay", return_value=False) as afplay,
            patch.object(tts, "_play_sounddevice", return_value=False) as sd,
        ):
            tts.play_wav(wav)
        self.assertTrue(afplay.called or sd.called)
        self.assertIsNone(st.read_status().get("speech_at"))

    def test_concat_wavs_joins_frames(self) -> None:
        a = _silence_wav(frames=10)
        b = _silence_wav(frames=20)
        joined = tts.concat_wavs([a, b])
        with wave.open(io.BytesIO(joined), "rb") as src:
            self.assertEqual(src.getnframes(), 30)


if __name__ == "__main__":
    unittest.main()
