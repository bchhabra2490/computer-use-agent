"""Local Piper / Kokoro TTS adapters."""

from __future__ import annotations

import io
import sys
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tts import piper as piper_mod  # noqa: E402
from tts.piper import _voice_hf_path  # noqa: E402
from wake import WakeHit  # noqa: E402


def _read_wav_frames(blob: bytes) -> tuple[int, int]:
    with wave.open(io.BytesIO(blob), "rb") as wf:
        return wf.getnframes(), wf.getframerate()


class PiperVoicePathTests(unittest.TestCase):
    def test_hf_layout(self) -> None:
        self.assertEqual(
            _voice_hf_path("en_US-lessac-medium"),
            "en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        )
        self.assertEqual(
            _voice_hf_path("en_GB-alan-medium"),
            "en/en_GB/alan/medium/en_GB-alan-medium.onnx",
        )


class PiperSynthesizeTests(unittest.TestCase):
    def tearDown(self) -> None:
        piper_mod._voices.clear()

    def test_synthesize_wav_writes_headers(self) -> None:
        fake = MagicMock()

        def write_wav(_text, wf, **_kwargs):
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            wf.writeframes(b"\x00\x00" * 40)

        fake.synthesize_wav.side_effect = write_wav
        with (
            patch.object(piper_mod, "_load", return_value=fake),
            patch.object(piper_mod, "_syn_config", return_value=None),
        ):
            wav = piper_mod.synthesize_wav("Hello there.")
        frames, rate = _read_wav_frames(wav)
        self.assertEqual(rate, 22050)
        self.assertEqual(frames, 40)
        fake.synthesize_wav.assert_called_once()


class KokoroSynthesizeTests(unittest.TestCase):
    def test_mlx_concatenates_chunks(self) -> None:
        from tts import kokoro as kokoro_mod

        chunk = SimpleNamespace(audio=np.ones(8, dtype=np.float32) * 0.1, sample_rate=24000)
        model = MagicMock()
        model.generate.return_value = [chunk, chunk]
        with (
            patch.object(kokoro_mod, "_mlx_available", return_value=True),
            patch.object(kokoro_mod, "KOKORO_ONNX_MODEL", ""),
            patch.object(kokoro_mod, "_load_mlx", return_value=model),
        ):
            wav = kokoro_mod.synthesize_wav("Hello.", voice="bm_george")
        frames, rate = _read_wav_frames(wav)
        self.assertEqual(rate, 24000)
        self.assertEqual(frames, 16)
        kwargs = model.generate.call_args.kwargs
        self.assertEqual(kwargs["voice"], "bm_george")
        self.assertEqual(kwargs["lang_code"], "b")


class LocalVoiceMappingTests(unittest.TestCase):
    @patch.dict("os.environ", {"KOKORO_VOICE": "af_heart"}, clear=False)
    @patch("tts._use_kokoro", return_value=True)
    @patch("tts._use_piper", return_value=False)
    @patch("tts._use_sarvam", return_value=False)
    @patch("wake.get_last_wake")
    def test_kokoro_jarvis_keeps_kokoro_voice(self, mock_wake, *_flags) -> None:
        from tts import active_tts_voice

        mock_wake.return_value = WakeHit(
            label="Jarvis Veerey",
            key="jarvis_veerey",
            source="model",
        )
        self.assertEqual(active_tts_voice(), "af_heart")

    @patch.dict(
        "os.environ",
        {"KOKORO_VOICE": "af_heart", "TTS_VOICE_JARVIS": "bm_george"},
        clear=False,
    )
    @patch("tts._use_kokoro", return_value=True)
    @patch("tts._use_piper", return_value=False)
    @patch("tts._use_sarvam", return_value=False)
    @patch("wake.get_last_wake")
    def test_kokoro_jarvis_override(self, mock_wake, *_flags) -> None:
        from tts import active_tts_voice

        mock_wake.return_value = WakeHit(label="Hey Jarvis", key="hey_jarvis", source="model")
        self.assertEqual(active_tts_voice(), "bm_george")

    @patch.dict("os.environ", {"PIPER_VOICE": "en_GB-alan-medium"}, clear=False)
    @patch("tts._use_piper", return_value=True)
    @patch("tts._use_kokoro", return_value=False)
    @patch("tts._use_sarvam", return_value=False)
    @patch("wake.get_last_wake")
    def test_piper_rekha_keeps_piper_voice(self, mock_wake, *_flags) -> None:
        from tts import active_tts_voice

        mock_wake.return_value = WakeHit(label="Hey Rekha", key="Hey_Rekha", source="model")
        self.assertEqual(active_tts_voice(), "en_GB-alan-medium")


if __name__ == "__main__":
    unittest.main()
