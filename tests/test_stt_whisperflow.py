"""Local WhisperFlow STT provider dispatch."""

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
from stt import whisperflow as wf  # noqa: E402


def _silence_wav(*, frames: int = 80, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"\x00\x00" * frames)
    return buf.getvalue()


class WhisperflowProviderTests(unittest.TestCase):
    def test_aliases(self) -> None:
        for name in ("whisperflow", "whisper-flow", "whisper", "mlx"):
            with patch.object(stt, "STT_PROVIDER", name):
                self.assertTrue(stt._use_whisperflow())
                self.assertTrue(stt._use_file_stt())
        with patch.object(stt, "STT_PROVIDER", "openai"):
            self.assertFalse(stt._use_whisperflow())

    def test_http_backend_when_url_set(self) -> None:
        with (
            patch.object(wf, "WHISPERFLOW_URL", "http://127.0.0.1:7777/v1"),
            patch.object(wf, "WHISPERFLOW_BACKEND", "auto"),
        ):
            self.assertEqual(wf.resolve_backend(), "http")

    def test_missing_backend_explains_install(self) -> None:
        with (
            patch.object(wf, "WHISPERFLOW_URL", ""),
            patch.object(wf, "WHISPERFLOW_BACKEND", "auto"),
            patch.dict(
                "sys.modules",
                {"mlx_whisper": None, "faster_whisper": None, "whisper": None},
            ),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                wf.resolve_backend()
        self.assertIn("mlx-whisper", str(ctx.exception))

    def test_auto_skips_incomplete_mlx_snapshot(self) -> None:
        with (
            patch.object(wf, "WHISPERFLOW_URL", ""),
            patch.object(wf, "WHISPERFLOW_BACKEND", "auto"),
            patch.object(wf, "WHISPERFLOW_MODEL", "mlx-community/whisper-large-v3-turbo"),
            patch.object(wf, "mlx_model_ready", return_value=False),
            patch.object(wf, "_whisper_importable", return_value=True),
        ):
            self.assertEqual(wf.resolve_backend(), "whisper")

    def test_mlx_connection_error_falls_back_to_whisper(self) -> None:
        wav = _silence_wav()
        fake_model = MagicMock()
        fake_model.transcribe.return_value = {"text": "  open notes  "}
        with (
            patch.object(wf, "WHISPERFLOW_URL", ""),
            patch.object(wf, "WHISPERFLOW_BACKEND", "auto"),
            patch.object(wf, "resolve_backend", return_value="mlx"),
            patch.object(wf, "_transcribe_mlx", side_effect=ConnectionError("Connection error.")),
            patch.object(wf, "_whisper_importable", return_value=True),
            patch.object(wf, "_transcribe_whisper", return_value="open notes") as local,
        ):
            text = wf.transcribe_wav(wav)
        self.assertEqual(text, "open notes")
        local.assert_called_once()

    def test_transcribe_http(self) -> None:
        wav = _silence_wav()
        fake = MagicMock()
        fake.audio.transcriptions.create.return_value = MagicMock(text="  open notes  ")
        with (
            patch.object(wf, "WHISPERFLOW_URL", "http://127.0.0.1:7777"),
            patch.object(wf, "WHISPERFLOW_BACKEND", "http"),
            patch("openai.OpenAI", return_value=fake),
        ):
            text = wf.transcribe_wav(wav, model="whisper-1")
        self.assertEqual(text, "open notes")
        fake.audio.transcriptions.create.assert_called_once()

    def test_stt_transcribe_dispatches(self) -> None:
        wav = _silence_wav()
        with (
            patch.object(stt, "STT_PROVIDER", "whisperflow"),
            patch("stt.whisperflow.transcribe_wav", return_value="hello locally") as inner,
        ):
            heard = stt.transcribe(MagicMock(), wav_bytes=wav)
        self.assertEqual(heard, "hello locally")
        inner.assert_called_once()

    def test_listen_realtime_uses_whisperflow_path(self) -> None:
        with (
            patch.object(stt, "STT_PROVIDER", "whisperflow"),
            patch("stt._listen_whisperflow", return_value=("hi", b"RIFF")) as path,
            patch("stt._listen_realtime_body") as realtime,
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

    def test_dictation_provider_auto_whisperflow(self) -> None:
        with patch.object(stt, "STT_PROVIDER", "whisperflow"):
            self.assertEqual(stt._dictation_provider(), "whisperflow")

    def test_dictation_provider_auto_openai(self) -> None:
        with patch.object(stt, "STT_PROVIDER", "openai"):
            self.assertEqual(stt._dictation_provider(), "realtime")

    def test_listen_dictation_uses_whisperflow_hold(self) -> None:
        partials: list[str] = []
        with (
            patch.object(stt, "DICTATION_STT", "auto"),
            patch.object(stt, "STT_PROVIDER", "whisperflow"),
            patch(
                "stt._listen_whisperflow_hold",
                return_value=("hello world", b"RIFF"),
            ) as hold,
            patch("stt.save_recording"),
        ):
            heard = stt.listen_dictation(
                MagicMock(),
                on_partial=partials.append,
            )
        self.assertEqual(heard, "hello world")
        hold.assert_called_once()


class SttTimingTests(unittest.TestCase):
    def test_timed_writes_function_and_ms(self) -> None:
        from tempfile import TemporaryDirectory

        from stt.timing import timed

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "stt_latency.log"
            with (
                patch("stt.timing.STT_TIMING", True),
                patch("stt.timing._LOG_PATH", path),
            ):
                with timed("load_model", model="small.en"):
                    pass
            text = path.read_text(encoding="utf-8")
        self.assertIn("load_model", text)
        self.assertIn("ms", text)
        self.assertIn("model=small.en", text)


if __name__ == "__main__":
    unittest.main()
