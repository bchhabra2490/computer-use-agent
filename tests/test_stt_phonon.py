"""Phonon-1 STT provider dispatch."""

from __future__ import annotations

import io
import sys
import unittest
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import stt  # noqa: E402
from stt import phonon as ph  # noqa: E402


def _silence_wav(*, frames: int = 80, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"\x00\x00" * frames)
    return buf.getvalue()


class PhononProviderTests(unittest.TestCase):
    def test_aliases(self) -> None:
        for name in ("phonon", "phonon-1", "fermion"):
            with patch.object(stt, "STT_PROVIDER", name):
                self.assertTrue(stt._use_phonon())
                self.assertTrue(stt._use_file_stt())
                self.assertTrue(stt._use_local_file_stt())
        with patch.object(stt, "STT_PROVIDER", "whisperflow"):
            self.assertFalse(stt._use_phonon())
            self.assertTrue(stt._use_file_stt())

    def test_http_backend_when_url_set(self) -> None:
        with (
            patch.object(ph, "PHONON_URL", "http://127.0.0.1:8000/v1"),
            patch.object(ph, "PHONON_BACKEND", "auto"),
        ):
            self.assertEqual(ph.resolve_backend(), "http")

    def test_missing_backend_explains_install(self) -> None:
        with (
            patch.object(ph, "PHONON_URL", ""),
            patch.object(ph, "PHONON_BACKEND", "auto"),
            patch.object(ph, "_fermion_importable", return_value=False),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                ph.resolve_backend()
        self.assertIn("fermion-research", str(ctx.exception))
        self.assertIn("PHONON_URL", str(ctx.exception))

    def test_local_backend_when_runtime_ready(self) -> None:
        with (
            patch.object(ph, "PHONON_URL", ""),
            patch.object(ph, "PHONON_BACKEND", "auto"),
            patch.object(ph, "_fermion_importable", return_value=True),
            patch.object(ph, "_speech_runtime_ready", return_value=True),
        ):
            self.assertEqual(ph.resolve_backend(), "local")

    def test_transcribe_http(self) -> None:
        wav = _silence_wav()
        fake = MagicMock()
        fake.audio.transcriptions.create.return_value = MagicMock(text="  open notes  ")
        with (
            patch.object(ph, "PHONON_URL", "http://127.0.0.1:8000"),
            patch.object(ph, "PHONON_BACKEND", "http"),
            patch("openai.OpenAI", return_value=fake),
        ):
            text = ph.transcribe_wav(wav, model="FermionResearch/Phonon-1")
        self.assertEqual(text, "open notes")
        fake.audio.transcriptions.create.assert_called_once()

    def test_transcribe_local_uses_worker(self) -> None:
        wav = _silence_wav()
        fake_pool = MagicMock()
        fake_pool.submit.return_value.result.return_value = "hi"
        with (
            patch.object(ph, "PHONON_URL", ""),
            patch.object(ph, "PHONON_BACKEND", "local"),
            patch.object(ph, "_fermion_importable", return_value=True),
            patch.object(ph, "_pool_worker", return_value=fake_pool),
        ):
            text = ph.transcribe_wav(wav)
        self.assertEqual(text, "hi")
        fake_pool.submit.assert_called_once()

    def test_stt_transcribe_dispatches(self) -> None:
        wav = _silence_wav()
        with (
            patch.object(stt, "STT_PROVIDER", "phonon"),
            patch("stt.phonon.transcribe_wav", return_value="hello phonon") as inner,
        ):
            heard = stt.transcribe(MagicMock(), wav_bytes=wav)
        self.assertEqual(heard, "hello phonon")
        inner.assert_called_once()

    def test_listen_realtime_uses_phonon_path(self) -> None:
        with (
            patch.object(stt, "STT_PROVIDER", "phonon"),
            patch("stt._listen_phonon", return_value=("hi", b"RIFF")) as path,
            patch("stt._listen_realtime_body") as realtime,
            patch("stt._listen_whisperflow") as whisper,
            patch("wake.pause_persistent_wake"),
            patch("wake.resume_persistent_wake"),
            patch("wake.reset_over_and_out_chime"),
            patch("app_status.set_stt_listening"),
        ):
            heard, wav = stt.listen_realtime(MagicMock())
        self.assertEqual(heard, "hi")
        self.assertEqual(wav, b"RIFF")
        path.assert_called_once()
        realtime.assert_not_called()
        whisper.assert_not_called()

    def test_dictation_provider_auto_phonon(self) -> None:
        with patch.object(stt, "STT_PROVIDER", "phonon"):
            self.assertEqual(stt._dictation_provider(), "phonon")

    def test_listen_dictation_uses_phonon_hold(self) -> None:
        with (
            patch.object(stt, "DICTATION_STT", "auto"),
            patch.object(stt, "STT_PROVIDER", "phonon"),
            patch("stt._listen_phonon", return_value=("hello world", b"RIFF")) as hold,
            patch("stt.save_recording"),
        ):
            heard = stt.listen_dictation(MagicMock())
        self.assertEqual(heard, "hello world")
        hold.assert_called_once()
        self.assertTrue(hold.call_args.kwargs.get("hold_mode"))


if __name__ == "__main__":
    unittest.main()
