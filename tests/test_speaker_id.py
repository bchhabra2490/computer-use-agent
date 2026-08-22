"""Speaker ID unit tests (no microphone)."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import speaker_id as sid  # noqa: E402


def _sine_wav(freq: float = 220.0, seconds: float = 1.0, rate: int = 24000) -> bytes:
    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
    pcm = (0.3 * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def _mock_embed(wav_bytes: bytes) -> np.ndarray:
    """Deterministic fake embeddings: low freqs = speaker A, high = speaker B."""
    audio, rate = sid._wav_bytes_to_mono_float(wav_bytes)
    spec = np.abs(np.fft.rfft(audio))
    freqs = np.fft.rfftfreq(len(audio), 1 / float(rate))
    peak = float(freqs[int(np.argmax(spec))]) if spec.size else 0.0
    vec = np.zeros(192, dtype=np.float32)
    if peak < 500:
        vec[0] = 1.0
        vec[2] = peak / 1000.0
    else:
        vec[1] = 1.0
        vec[3] = peak / 1000.0
    return vec / (np.linalg.norm(vec) + 1e-9)


class SpeakerIdTests(unittest.TestCase):
    def setUp(self) -> None:
        self._embed_patch = patch.object(sid, "embed_wav_bytes", side_effect=_mock_embed)
        self._embed_patch.start()

    def tearDown(self) -> None:
        self._embed_patch.stop()

    def test_slug_name(self) -> None:
        self.assertEqual(sid.slug_name("Bharat Chhabra"), "bharat-chhabra")

    def test_embed_and_match_same_tone(self) -> None:
        a = sid.embed_wav_bytes(_sine_wav(220.0))
        b = sid.embed_wav_bytes(_sine_wav(220.0))
        self.assertGreater(sid.cosine_similarity(a, b), 0.95)

    def test_enroll_and_identify(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(sid, "SPEAKERS_DIR", root):
                samples = [_sine_wav(300.0 + i * 10) for i in range(3)]
                sid.enroll_speaker("Alice", samples)
                match = sid.identify(_sine_wav(305.0))
                self.assertIsNotNone(match)
                assert match is not None
                self.assertEqual(match.name, "alice")
                self.assertEqual(match.display_name, "Alice")

    def test_profile_saved_with_three_samples(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(sid, "SPEAKERS_DIR", root):
                samples = [_sine_wav(300.0 + i * 10) for i in range(3)]
                out = sid.enroll_speaker("Alice", samples)
                self.assertTrue((out / "profile.json").is_file())
                for i in range(1, 4):
                    self.assertTrue((out / f"sample-{i}.wav").is_file())
                data = json.loads((out / "profile.json").read_text(encoding="utf-8"))
                self.assertEqual(len(data.get("embeddings") or []), 3)
                self.assertEqual(data.get("display_name"), "Alice")
                self.assertEqual(data.get("backend"), "speakeronnx")

    def test_score_speakers_ranks_by_similarity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(sid, "SPEAKERS_DIR", root):
                samples = [_sine_wav(300.0 + i * 10) for i in range(3)]
                sid.enroll_speaker("Alice", samples)
                sid.enroll_speaker("Bob", [_sine_wav(800.0 + i * 10) for i in range(3)])
                scored = sid.score_speakers(_sine_wav(305.0))
                self.assertEqual(len(scored), 2)
                self.assertEqual(scored[0].display_name, "Alice")
                self.assertGreater(scored[0].score, scored[1].score)

    def test_identify_wav_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(sid, "SPEAKERS_DIR", root):
                samples = [_sine_wav(300.0 + i * 10) for i in range(3)]
                sid.enroll_speaker("Alice", samples)
                match, scored = sid._identify_wav_bytes(_sine_wav(305.0))
                self.assertIsNotNone(match)
                assert match is not None
                self.assertEqual(match.display_name, "Alice")
                self.assertGreater(len(scored), 0)

    def test_rejects_different_speaker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(sid, "SPEAKERS_DIR", root):
                sid.enroll_speaker("Alice", [_sine_wav(300.0 + i * 10) for i in range(3)])
                match = sid.identify(_sine_wav(850.0))
                self.assertIsNone(match)

    def test_skips_legacy_mfcc_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(sid, "SPEAKERS_DIR", root):
                stale = root / "bharat"
                stale.mkdir()
                stale.joinpath("profile.json").write_text(
                    json.dumps(
                        {
                            "slug": "bharat",
                            "display_name": "Bharat",
                            "backend": "mfcc",
                            "centroid": [1.0] + [0.0] * 59,
                            "embeddings": [[1.0] + [0.0] * 59],
                            "threshold": 0.82,
                        }
                    ),
                    encoding="utf-8",
                )
                scored = sid.score_speakers(_sine_wav(300.0))
                self.assertEqual(scored, [])

    def test_three_passages_defined(self) -> None:
        self.assertEqual(len(sid.ENROLLMENT_PASSAGES), 3)
        for title, body in sid.ENROLLMENT_PASSAGES:
            self.assertIn("Passage", title)
            self.assertGreaterEqual(len(body.splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
