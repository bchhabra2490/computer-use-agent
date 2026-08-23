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

# Before numpy/OpenBLAS (can SIGSEGV if over-threaded on macOS).
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

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
DEFAULT_SHORT_THRESHOLD = float(os.environ.get("SPEAKER_ID_SHORT_THRESHOLD", "0.35"))
SHORT_THRESHOLD_FLOOR = float(os.environ.get("SPEAKER_ID_SHORT_THRESHOLD_FLOOR", "0.30"))
# Clips shorter than this use short embeddings + threshold_short (and 2× loop before embed).
SHORT_CLIP_SECONDS = float(os.environ.get("SPEAKER_ID_SHORT_SECONDS", "4.0"))
LOOP_SHORT_BELOW_SECONDS = float(os.environ.get("SPEAKER_ID_LOOP_BELOW_SECONDS", "2.0"))
MIN_EMBED_SECONDS = float(os.environ.get("SPEAKER_ID_MIN_SECONDS", "0.15"))
TRIM_TOP_DB = float(os.environ.get("SPEAKER_ID_TRIM_DB", "25"))
LONG_PASSAGE_COUNT = 3
# ONNX speaker embedding model (speakeronnx registry alias).
SPEAKER_ID_MODEL = os.environ.get("SPEAKER_ID_MODEL", "wespeaker-ecapa512").strip()
EMBED_BACKEND = "speakeronnx"

ENROLLMENT_PASSAGES: list[tuple[str, str]] = [
    (
        "Passage 1 of 5",
        "Good morning. Coffee is brewing, and sunlight is filling the kitchen.\n"
        "I'll check my calendar after breakfast, then step outside for a few minutes.\n"
        "The air feels cool and clear after last night's rain.",
    ),
    (
        "Passage 2 of 5",
        "Jarvis, open Google Maps and show Annapurna Base Camp in Nepal.\n"
        "Remind me to check the DeskJet print queue before lunch.\n"
        "Pull up the wiring diagram for the ESP32 board on my desk.",
    ),
    (
        "Passage 3 of 5",
        "Set the volume to forty percent and turn on both monitors.\n"
        "Send Rekha a message: dinner is at seven tonight.\n"
        "I have two meetings tomorrow — one at ten, and another at half past three.",
    ),
    (
        "Passage 4 of 5 (short)",
        "Hey Jarvis.",
    ),
    (
        "Passage 5 of 5 (short)",
        "Yes, go ahead.",
    ),
]


@dataclass(frozen=True)
class ScoredSpeaker:
    slug: str
    display_name: str
    score: float
    threshold: float
    short_clip: bool = False

    @property
    def matched(self) -> bool:
        return self.score >= self.threshold


@dataclass(frozen=True)
class SpeakerMatch:
    name: str
    display_name: str
    score: float

    def line_for_prompt(self) -> str:
        return f"Speaker (voice ID): {self.display_name} " f"(confidence {self.score:.0%})."

    def line_for_agent(self) -> str:
        return (
            f"Speaker (voice ID): {self.display_name} (confidence {self.score:.0%}). "
            "You may use this to personalize ask_user or mark_done wording if helpful; "
            "personalization is optional — never change the task or refuse if unknown."
        )


def agent_speaker_context(match: SpeakerMatch | None) -> str:
    """Optional block for the computer-use agent prompt, or empty string."""
    if match is None:
        return ""
    return match.line_for_agent() + "\n\n"


_last_speaker: SpeakerMatch | None = None


def enabled() -> bool:
    return SPEAKER_ID_ENABLED and SPEAKERS_DIR.is_dir() and any(SPEAKERS_DIR.iterdir())


def set_last_speaker(match: SpeakerMatch | None) -> None:
    global _last_speaker
    _last_speaker = match


def get_last_speaker() -> SpeakerMatch | None:
    return _last_speaker


def clear_last_speaker() -> None:
    set_last_speaker(None)


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


def _trim_silence(
    audio: np.ndarray,
    sample_rate: int,
    *,
    top_db: float = TRIM_TOP_DB,
    frame_ms: float = 25.0,
    hop_ms: float = 10.0,
) -> np.ndarray:
    """Drop leading/trailing silence (energy below peak - top_db)."""
    if audio.size == 0 or sample_rate <= 0:
        return audio
    frame = max(1, int(sample_rate * frame_ms / 1000.0))
    hop = max(1, int(sample_rate * hop_ms / 1000.0))
    if audio.size <= frame:
        return audio

    n_frames = 1 + (len(audio) - frame) // hop
    rms = np.empty(n_frames, dtype=np.float64)
    for i in range(n_frames):
        chunk = audio[i * hop : i * hop + frame].astype(np.float64)
        rms[i] = float(np.sqrt(np.mean(chunk * chunk)) + 1e-12)

    peak = float(rms.max())
    if peak <= 1e-12:
        return audio
    threshold = peak * (10.0 ** (-top_db / 20.0))
    voiced = np.flatnonzero(rms >= threshold)
    if voiced.size == 0:
        return audio

    start = int(voiced[0]) * hop
    end = min(len(audio), int(voiced[-1]) * hop + frame)
    trimmed = audio[start:end]
    min_keep = int(MIN_EMBED_SECONDS * sample_rate)
    if trimmed.size >= min_keep:
        return trimmed.astype(np.float32)
    return audio


def _audio_at_embed_rate(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    audio, rate = _wav_bytes_to_mono_float(wav_bytes)
    embedder = _get_embedder()
    if rate != embedder.sample_rate:
        audio = _resample_linear(audio, rate, embedder.sample_rate)
    return _trim_silence(audio, embedder.sample_rate), embedder.sample_rate


_embedder = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        try:
            from speakeronnx import SpeakerEmbedder
        except ImportError as e:
            raise RuntimeError("speakeronnx is required for speaker ID (pip install speakeronnx)") from e
        _embedder = SpeakerEmbedder(SPEAKER_ID_MODEL)
    return _embedder


def wav_duration_seconds(wav_bytes: bytes) -> float:
    """Speech duration after resample + leading/trailing silence trim."""
    try:
        audio, rate = _audio_at_embed_rate(wav_bytes)
    except (ValueError, RuntimeError):
        return 0.0
    return audio.size / float(rate) if rate > 0 else 0.0


def wav_has_min_speech(
    wav_bytes: bytes,
    *,
    min_seconds: float | None = None,
    min_rms: float = 0.005,
) -> bool:
    """True when trimmed speech has enough duration and energy to embed."""
    try:
        audio, rate = _audio_at_embed_rate(wav_bytes)
    except (ValueError, RuntimeError):
        return False
    if rate <= 0 or audio.size == 0:
        return False
    floor = MIN_EMBED_SECONDS if min_seconds is None else min_seconds
    if audio.size / float(rate) < floor:
        return False
    rms = float(np.sqrt(np.mean(np.square(audio.astype(np.float64)))))
    return rms >= min_rms


def _prepare_audio_for_embed(audio: np.ndarray, target_rate: int) -> np.ndarray:
    audio = _trim_silence(audio, target_rate)
    dur = audio.size / float(target_rate) if target_rate > 0 else 0.0
    if 0.0 < dur < LOOP_SHORT_BELOW_SECONDS:
        audio = np.concatenate([audio, audio])
    min_samples = int(MIN_EMBED_SECONDS * target_rate)
    if audio.size < min_samples:
        raise ValueError("Audio too short for speaker embedding")
    return audio.astype(np.float32)


def embed_wav_bytes(wav_bytes: bytes) -> np.ndarray:
    """Return an L2-normalized speaker embedding vector."""
    if not wav_bytes:
        raise ValueError("Empty audio")
    audio, rate = _wav_bytes_to_mono_float(wav_bytes)
    embedder = _get_embedder()
    if rate != embedder.sample_rate:
        audio = _resample_linear(audio, rate, embedder.sample_rate)
    audio = _prepare_audio_for_embed(audio, embedder.sample_rate)
    return np.asarray(embedder.embed(audio), dtype=np.float32)


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


def _best_similarity(
    embedding: np.ndarray,
    centroid: np.ndarray | list[float] | None,
    rows: list[list[float]] | list[np.ndarray],
) -> float:
    best = -1.0
    if centroid is not None:
        vec = np.asarray(centroid, dtype=np.float32)
        if vec.size:
            best = max(best, cosine_similarity(embedding, vec))
    for row in rows:
        vec = np.asarray(row, dtype=np.float32)
        if vec.size:
            best = max(best, cosine_similarity(embedding, vec))
    return max(best, 0.0)


def _pairwise_min(embs: list[np.ndarray]) -> float | None:
    if len(embs) < 2:
        return None
    scores = [cosine_similarity(embs[i], embs[j]) for i in range(len(embs)) for j in range(i + 1, len(embs))]
    return min(scores) if scores else None


def _threshold_from_pairwise(
    min_pair: float | None,
    *,
    default: float,
    floor: float = 0.45,
) -> float:
    if min_pair is None:
        return default
    return max(floor, min(default, min_pair * 0.85))


def _score_profile(embedding: np.ndarray, profile: dict[str, Any], *, short_clip: bool) -> float:
    score, _ = _score_and_threshold(embedding, profile, short_clip=short_clip)
    return score


def _score_and_threshold(
    embedding: np.ndarray,
    profile: dict[str, Any],
    *,
    short_clip: bool,
) -> tuple[float, float]:
    short_rows = profile.get("short_embeddings") or []
    if short_clip and short_rows:
        score = _best_similarity(
            embedding,
            profile.get("short_centroid"),
            short_rows,
        )
        return score, _threshold_short_for_profile(profile)

    long_rows = profile.get("long_embeddings")
    if not long_rows:
        long_rows = profile.get("embeddings") or []
    long_centroid = profile.get("long_centroid") or profile.get("centroid")
    score = _best_similarity(embedding, long_centroid, long_rows)
    threshold = _threshold_for_profile(profile)
    if short_clip and not short_rows:
        threshold = min(threshold, DEFAULT_SHORT_THRESHOLD)
    return score, threshold


def _threshold_for_profile(profile: dict[str, Any]) -> float:
    custom = profile.get("threshold")
    if isinstance(custom, (int, float)) and custom > 0:
        return float(custom)
    return DEFAULT_THRESHOLD


def _threshold_short_for_profile(profile: dict[str, Any]) -> float:
    custom = profile.get("threshold_short")
    if isinstance(custom, (int, float)) and custom > 0:
        return min(float(custom), DEFAULT_SHORT_THRESHOLD)
    return DEFAULT_SHORT_THRESHOLD


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
    clip_seconds = wav_duration_seconds(wav_bytes)
    short_clip = clip_seconds < SHORT_CLIP_SECONDS
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
        score, threshold = _score_and_threshold(
            embedding,
            profile,
            short_clip=short_clip,
        )
        scored.append(
            ScoredSpeaker(
                slug=slug,
                display_name=str(profile.get("display_name") or slug),
                score=score,
                threshold=threshold,
                short_clip=short_clip,
            )
        )
    if skipped:
        print(
            "[speaker] skipped stale profile(s) " f"{', '.join(skipped)} — re-run: cua speaker enroll --name …",
            flush=True,
        )
    if short_clip:
        print(
            f"[speaker] short clip ({clip_seconds:.1f}s < {SHORT_CLIP_SECONDS:g}s) " "— using short-profile scoring",
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
            mode = "short" if top.short_clip else "long"
            print(
                f"[speaker] no match ({mode} best={top.score:.3f} < {top.threshold:.3f})",
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

    emb_arr = [np.asarray(row, dtype=np.float32) for row in embeddings]
    long_embs = emb_arr[:LONG_PASSAGE_COUNT]
    short_embs = emb_arr[LONG_PASSAGE_COUNT:] if len(emb_arr) > LONG_PASSAGE_COUNT else []

    def _centroid(vecs: list[np.ndarray]) -> list[float]:
        if not vecs:
            return []
        mat = np.stack(vecs, axis=0)
        c = mat.mean(axis=0)
        c = c / (np.linalg.norm(c) + 1e-9)
        return c.astype(np.float32).tolist()

    long_centroid = _centroid(long_embs)
    short_centroid = _centroid(short_embs)
    centroid = _centroid(emb_arr)

    threshold = _threshold_from_pairwise(_pairwise_min(long_embs), default=DEFAULT_THRESHOLD)
    threshold_short = _threshold_from_pairwise(
        _pairwise_min(short_embs),
        default=DEFAULT_SHORT_THRESHOLD,
        floor=SHORT_THRESHOLD_FLOOR,
    )

    profile = {
        "slug": slug,
        "display_name": display_name.strip(),
        "backend": EMBED_BACKEND,
        "model": SPEAKER_ID_MODEL,
        "embed_dim": len(embeddings[0]) if embeddings else 0,
        "embeddings": embeddings,
        "centroid": centroid,
        "long_embeddings": [e.tolist() for e in long_embs],
        "long_centroid": long_centroid,
        "short_embeddings": [e.tolist() for e in short_embs],
        "short_centroid": short_centroid,
        "short_sample_count": len(short_embs),
        "threshold": round(threshold, 4),
        "threshold_short": round(threshold_short, 4),
        "enrollment_min_score": round(_pairwise_min(long_embs) or 0.0, 4) if long_embs else None,
        "enrollment_min_score_short": round(_pairwise_min(short_embs) or 0.0, 4) if short_embs else None,
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
