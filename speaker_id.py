"""Local speaker enrollment and identification from short mic clips.

Profiles live under ``models/speakers/<name>/`` (WAV samples + ``profile.json``).
Embeddings use ``speakeronnx`` (WeSpeaker ECAPA-TDNN ONNX by default).
"""

from __future__ import annotations

import io
import json
import os
import re
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

SPEAKERS_DIR = Path(__file__).resolve().parent / "models" / "speakers"
TARGET_RATE = 16_000

SPEAKER_ID_ENABLED = os.environ.get("SPEAKER_ID", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
# Cosine similarity floor; auto-tuned per profile from enrollment if possible.
DEFAULT_THRESHOLD = float(os.environ.get("SPEAKER_ID_THRESHOLD", "0.55"))
# ONNX speaker embedding model (speakeronnx registry alias).
SPEAKER_ID_MODEL = os.environ.get("SPEAKER_ID_MODEL", "wespeaker-ecapa512").strip()
EMBED_BACKEND = "speakeronnx"

ENROLLMENT_PASSAGES: list[tuple[str, str]] = [
    (
        "Passage 1 of 3",
        "The morning sun warmed the kitchen as coffee brewed on the counter.\n"
        "I speak clearly so the assistant can learn the sound of my voice.\n"
        "Please read this at your normal pace, not too fast and not too slow.",
    ),
    (
        "Passage 2 of 3",
        "Jarvis, open Google Maps and show Annapurna Base Camp in Nepal.\n"
        "Then remind me to check the print job on the DeskJet printer.\n"
        "I might ask about circuits, diagrams, or the ESP32 on my desk.",
    ),
    (
        "Passage 3 of 3",
        "Numbers mix with names in everyday speech: two monitors, forty percent volume,\n"
        "and a message for Rekha about dinner at seven.\n"
        "This is the third and final voice sample for speaker enrollment.",
    ),
]


@dataclass(frozen=True)
class ScoredSpeaker:
    slug: str
    display_name: str
    score: float
    threshold: float

    @property
    def matched(self) -> bool:
        return self.score >= self.threshold


@dataclass(frozen=True)
class SpeakerMatch:
    name: str
    display_name: str
    score: float

    def line_for_prompt(self) -> str:
        return (
            f"Speaker (voice ID): {self.display_name} "
            f"(confidence {self.score:.0%})."
        )


_last_speaker: SpeakerMatch | None = None


def enabled() -> bool:
    return SPEAKER_ID_ENABLED and SPEAKERS_DIR.is_dir() and any(SPEAKERS_DIR.iterdir())


def set_last_speaker(match: SpeakerMatch | None) -> None:
    global _last_speaker
    _last_speaker = match


def get_last_speaker() -> SpeakerMatch | None:
    return _last_speaker


def slug_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    if not slug:
        raise ValueError("Speaker name must contain at least one letter or digit.")
    return slug


def _wav_bytes_to_mono_float(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        channels = wf.getnchannels()
        rate = wf.getframerate()
        sampwidth = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())
    if sampwidth == 2:
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        audio = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {sampwidth}")
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio.astype(np.float32), int(rate)


def _resample_linear(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or audio.size == 0:
        return audio
    duration = audio.shape[0] / float(src_rate)
    dst_len = max(1, int(round(duration * dst_rate)))
    x_old = np.linspace(0.0, duration, num=audio.shape[0], endpoint=False)
    x_new = np.linspace(0.0, duration, num=dst_len, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


_embedder = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        try:
            from speakeronnx import SpeakerEmbedder
        except ImportError as e:
            raise RuntimeError(
                "speakeronnx is required for speaker ID (pip install speakeronnx)"
            ) from e
        _embedder = SpeakerEmbedder(SPEAKER_ID_MODEL)
    return _embedder


def embed_wav_bytes(wav_bytes: bytes) -> np.ndarray:
    """Return an L2-normalized speaker embedding vector."""
    if not wav_bytes:
        raise ValueError("Empty audio")
    audio, rate = _wav_bytes_to_mono_float(wav_bytes)
    embedder = _get_embedder()
    min_samples = int(0.25 * embedder.sample_rate)
    if audio.size < min_samples:
        raise ValueError("Audio too short for speaker embedding")
    if rate != embedder.sample_rate:
        audio = _resample_linear(audio, rate, embedder.sample_rate)
    return np.asarray(embedder.embed(audio.astype(np.float32)), dtype=np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def _profile_path(slug: str) -> Path:
    return SPEAKERS_DIR / slug / "profile.json"


def list_profiles() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not SPEAKERS_DIR.is_dir():
        return out
    for path in sorted(SPEAKERS_DIR.iterdir()):
        if not path.is_dir():
            continue
        prof = path / "profile.json"
        if not prof.is_file():
            continue
        try:
            data = json.loads(prof.read_text(encoding="utf-8"))
            out.append(data)
        except (OSError, json.JSONDecodeError):
            continue
    return out


def load_profile(slug: str) -> dict[str, Any] | None:
    path = _profile_path(slug)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _score_profile(embedding: np.ndarray, profile: dict[str, Any]) -> float:
    centroid = np.asarray(profile.get("centroid") or [], dtype=np.float32)
    if centroid.size == 0:
        return 0.0
    best = cosine_similarity(embedding, centroid)
    for row in profile.get("embeddings") or []:
        vec = np.asarray(row, dtype=np.float32)
        if vec.size:
            best = max(best, cosine_similarity(embedding, vec))
    return best


def _threshold_for_profile(profile: dict[str, Any]) -> float:
    custom = profile.get("threshold")
    if isinstance(custom, (int, float)) and custom > 0:
        return float(custom)
    return DEFAULT_THRESHOLD


def _profile_backend(profile: dict[str, Any]) -> str:
    return str(profile.get("backend") or "mfcc").strip().lower()


def _profile_compatible(profile: dict[str, Any]) -> bool:
    backend = _profile_backend(profile)
    if backend == EMBED_BACKEND:
        return True
    model = str(profile.get("model") or "").strip()
    return backend == "speakeronnx" and model == SPEAKER_ID_MODEL


def _accept_match(scored: list[ScoredSpeaker]) -> SpeakerMatch | None:
    if not scored:
        return None
    top = scored[0]
    if not top.matched:
        return None
    if len(scored) > 1:
        margin = float(os.environ.get("SPEAKER_ID_MARGIN", "0.08"))
        if top.score - scored[1].score < margin:
            print(
                f"[speaker] no match (margin {top.score - scored[1].score:.3f} "
                f"< {margin:.3f}; top={top.display_name}, "
                f"second={scored[1].display_name})",
                flush=True,
            )
            return None
    return SpeakerMatch(name=top.slug, display_name=top.display_name, score=top.score)


def score_speakers(wav_bytes: bytes) -> list[ScoredSpeaker]:
    """Score ``wav_bytes`` against every enrolled profile (best score first)."""
    embedding = embed_wav_bytes(wav_bytes)
    scored: list[ScoredSpeaker] = []
    skipped: list[str] = []
    for profile in list_profiles():
        slug = str(profile.get("slug") or profile.get("name") or "").strip()
        if not slug:
            continue
        if not _profile_compatible(profile):
            skipped.append(str(profile.get("display_name") or slug))
            continue
        scored.append(
            ScoredSpeaker(
                slug=slug,
                display_name=str(profile.get("display_name") or slug),
                score=_score_profile(embedding, profile),
                threshold=_threshold_for_profile(profile),
            )
        )
    if skipped:
        print(
            "[speaker] skipped stale profile(s) "
            f"{', '.join(skipped)} — re-run: cua speaker enroll --name …",
            flush=True,
        )
    scored.sort(key=lambda row: row.score, reverse=True)
    return scored


def identify(wav_bytes: bytes) -> SpeakerMatch | None:
    """Match ``wav_bytes`` to an enrolled speaker, or None if unknown."""
    if not SPEAKER_ID_ENABLED:
        return None
    if not list_profiles():
        return None
    try:
        scored = score_speakers(wav_bytes)
    except (ValueError, RuntimeError) as e:
        print(f"[speaker] identify skipped: {e}", flush=True)
        return None
    if not scored:
        return None

    match = _accept_match(scored)
    if match is None:
        top = scored[0]
        if not top.matched:
            print(
                f"[speaker] no match (best={top.score:.3f} < {top.threshold:.3f})",
                flush=True,
            )
        return None
    print(f"[speaker] identified {match.display_name} ({match.score:.0%})", flush=True)
    return match


def _identify_wav_bytes(wav_bytes: bytes) -> tuple[SpeakerMatch | None, list[ScoredSpeaker]]:
    """Identify without logging; returns (match or None, ranked scores)."""
    if not SPEAKER_ID_ENABLED:
        return None, []
    try:
        scored = score_speakers(wav_bytes)
    except (ValueError, RuntimeError):
        return None, []
    if not scored:
        return None, []
    match = _accept_match(scored)
    if match is None:
        return None, scored
    return match, scored


def enroll_speaker(
    display_name: str,
    samples: list[bytes],
    *,
    passages: list[str] | None = None,
) -> Path:
    """Save WAV samples + averaged embedding profile for ``display_name``."""
    slug = slug_name(display_name)
    root = SPEAKERS_DIR / slug
    root.mkdir(parents=True, exist_ok=True)

    embeddings: list[list[float]] = []
    for i, wav_bytes in enumerate(samples, start=1):
        (root / f"sample-{i}.wav").write_bytes(wav_bytes)
        embeddings.append(embed_wav_bytes(wav_bytes).tolist())

    mat = np.asarray(embeddings, dtype=np.float32)
    centroid = mat.mean(axis=0)
    centroid = centroid / (np.linalg.norm(centroid) + 1e-9)

    pairwise = []
    min_pair = None
    for i in range(len(embeddings)):
        for j in range(i + 1, len(embeddings)):
            pairwise.append(
                cosine_similarity(
                    np.asarray(embeddings[i], dtype=np.float32),
                    np.asarray(embeddings[j], dtype=np.float32),
                )
            )
    # Require live utterances to be at least this similar to the enrolled voice.
    if pairwise:
        min_pair = min(pairwise)
        threshold = max(0.45, min(DEFAULT_THRESHOLD, min_pair * 0.85))
    else:
        threshold = DEFAULT_THRESHOLD

    profile = {
        "slug": slug,
        "display_name": display_name.strip(),
        "backend": EMBED_BACKEND,
        "model": SPEAKER_ID_MODEL,
        "embed_dim": len(embeddings[0]) if embeddings else 0,
        "embeddings": embeddings,
        "centroid": centroid.tolist(),
        "threshold": round(threshold, 4),
        "enrollment_min_score": round(min_pair, 4) if pairwise else None,
        "enrolled_at": datetime.now(timezone.utc).isoformat(),
        "passages": passages or [p[1] for p in ENROLLMENT_PASSAGES],
        "sample_rate": TARGET_RATE,
    }
    _profile_path(slug).write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    return root


def delete_profile(slug_or_name: str) -> bool:
    slug = slug_name(slug_or_name)
    root = SPEAKERS_DIR / slug
    if not root.is_dir():
        return False
    for path in sorted(root.glob("*"), reverse=True):
        path.unlink(missing_ok=True)
    root.rmdir()
    return True
