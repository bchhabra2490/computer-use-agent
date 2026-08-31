"""
Local wake-word detection for the voice orchestrator.

Two modes (WAKE_MODE):
  - model  — openWakeWord ONNX classifier (pretrained or your custom .onnx)
  - phrase — any phrase via STT matching (no model training; uses the STT API)

While STT is listening, say **over and out** to end capture and start
processing (like menu Send). Uses `models/wake/over_and_out.onnx` when present
(`WAKE_END_MODEL`), plus transcript matching (`WAKE_END_PHRASE`).

Examples:
  WAKE_MODEL=hey_jarvis,Hey_Rekha.onnx WAKE_PHRASE="Hey Jarvis,Jarvis,Hey Rekha,Rekha"
  WAKE_END_MODEL=over_and_out.onnx WAKE_END_PHRASE="over and out,over n out"
  WAKE_MODEL=/path/to/hey_bob.onnx WAKE_PHRASE="Hey Bob" # custom ONNX
  WAKE_MODE=phrase WAKE_PHRASE="Okay Computer,Computer"  # any phrases via STT
"""

from __future__ import annotations

import os
import re
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Before numpy/OpenBLAS (can SIGSEGV if over-threaded on macOS).
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import numpy as np
import sounddevice as sd

WAKE_RATE = 16_000
# openWakeWord expects 80 ms frames (1280 samples @ 16 kHz).
CHUNK_SAMPLES = 1280
DEFAULT_THRESHOLD = float(os.environ.get("WAKE_THRESHOLD", "0.5"))
# Slightly higher bar while TTS is playing (reduce echo false triggers).
BARGE_IN_THRESHOLD = float(os.environ.get("WAKE_BARGE_THRESHOLD", "0.6"))
# Ignore this many seconds after STT starts (shorter now that end ≠ start word).
WAKE_END_LISTEN_IGNORE = float(os.environ.get("WAKE_END_LISTEN_IGNORE", "0.25"))
WAKE_MODEL_DIR = Path(
    os.environ.get(
        "WAKE_MODEL_DIR",
        str(Path(__file__).resolve().parent / "models" / "wake"),
    )
)
WAKE_MODE = (os.environ.get("WAKE_MODE") or "model").strip().lower()


def _default_wake_model() -> str:
    """hey_jarvis plus bundled custom start models when those files exist."""
    parts = ["hey_jarvis"]
    if (WAKE_MODEL_DIR / "Hey_Rekha.onnx").is_file():
        parts.append("Hey_Rekha.onnx")
    return ",".join(parts)


# Comma-separated aliases, filenames, or paths. Default: hey jarvis (+ Hey Rekha if present).
WAKE_MODEL = (os.environ.get("WAKE_MODEL") or _default_wake_model()).strip()

# Shared feature extractors always required for model mode.
_FEATURE_MODELS = (
    "embedding_model.onnx",
    "melspectrogram.onnx",
)

# Alias → release asset + default spoken phrase.
# End-listen should use a *wake word*, not timer/weather (those are long intents).
PRETRAINED: dict[str, tuple[str, str]] = {
    "hey_jarvis": ("hey_jarvis_v0.1.onnx", "Hey Jarvis"),
    "jarvis": ("hey_jarvis_v0.1.onnx", "Hey Jarvis"),
    "alexa": ("alexa_v0.1.onnx", "Alexa"),
    "hey_mycroft": ("hey_mycroft_v0.1.onnx", "Hey Mycroft"),
    "mycroft": ("hey_mycroft_v0.1.onnx", "Hey Mycroft"),
    "hey_rhasspy": ("hey_rhasspy_v0.1.onnx", "Hey Rhasspy"),
    "rhasspy": ("hey_rhasspy_v0.1.onnx", "Hey Rhasspy"),
    "timer": ("timer_v0.1.onnx", "set a timer"),
    "weather": ("weather_v0.1.onnx", "what's the weather"),
}

_RELEASE_BASE = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1"

_model = None
_model_keys: list[str] = []
_start_model_keys: list[str] = []
_end_model_keys: list[str] = []
_last_wake_remainder: str | None = None
_last_wake: WakeHit | None = None


@dataclass(frozen=True)
class WakeHit:
    """Which start-wake fired. `key` is the ONNX model id (None in phrase mode)."""

    label: str
    key: str | None = None
    score: float | None = None
    source: str = "model"  # "model" | "phrase"


def _default_phrase_for_models(specs: list[str]) -> str:
    for spec in specs:
        key = Path(spec).stem.lower().replace("-", "_")
        # hey_jarvis_v0.1 → hey_jarvis
        for alias, (fname, phrase) in PRETRAINED.items():
            if key == alias or key.startswith(Path(fname).stem.lower()):
                return phrase
        # Custom file: turn hey_bob_v1 → "Hey Bob"
        cleaned = re.sub(r"_v?\d+(\.\d+)?$", "", key)
        cleaned = cleaned.replace("_", " ").strip()
        if cleaned:
            return cleaned.title()
    return "Hey Jarvis"


def _parse_model_specs() -> list[str]:
    parts = [p.strip() for p in WAKE_MODEL.split(",") if p.strip()]
    return parts or ["hey_jarvis"]


def _parse_wake_phrases(raw: str) -> list[str]:
    """Comma-separated wake phrases; longest-first friendly, case-preserving."""
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(part)
    return out


_MODEL_SPECS = _parse_model_specs()
_DEFAULT_PHRASES = "Hey Jarvis,Jarvis"
if any(Path(spec).stem.lower().replace("-", "_") in {"hey_rekha", "rekha"} for spec in _MODEL_SPECS):
    _DEFAULT_PHRASES = "Hey Jarvis,Jarvis,Hey Rekha,Rekha"


def _default_end_model_spec() -> str:
    """Prefer the bundled over-and-out ONNX when present."""
    candidate = WAKE_MODEL_DIR / "over_and_out.onnx"
    if candidate.is_file():
        return "over_and_out.onnx"
    return ""


def _parse_end_model_specs() -> list[str]:
    """ONNX for ending a listen. Default: over_and_out.onnx if that file exists."""
    raw = (os.environ.get("WAKE_END_MODEL") or "").strip()
    if raw.lower() in {"0", "false", "no", "off", "none", "phrase"}:
        return []
    if not raw:
        default = _default_end_model_spec()
        return [default] if default else []
    if raw.lower() in {"same", "start", "wake"}:
        return list(_MODEL_SPECS)
    return [p.strip() for p in raw.split(",") if p.strip()]


_END_MODEL_SPECS = _parse_end_model_specs()
_wake_phrase_env = (os.environ.get("WAKE_PHRASE") or "").strip()
if _wake_phrase_env:
    WAKE_PHRASES = _parse_wake_phrases(_wake_phrase_env)
else:
    # Default: accept both full and short forms for Jarvis (and Rekha if loaded).
    WAKE_PHRASES = _parse_wake_phrases(_DEFAULT_PHRASES)
    extra = [
        _default_phrase_for_models([spec])
        for spec in _MODEL_SPECS
        if WAKE_MODE != "phrase"
    ]
    for phrase in extra:
        if phrase and phrase.lower() not in {p.lower() for p in WAKE_PHRASES}:
            WAKE_PHRASES.append(phrase)
if not WAKE_PHRASES:
    WAKE_PHRASES = _parse_wake_phrases(_DEFAULT_PHRASES)

# Primary phrase (first) kept for backward-compatible imports / single-string APIs.
WAKE_PHRASE = WAKE_PHRASES[0]

_END_PHRASE_DEFAULT = "over and out,over n out"
_end_phrase_env = (os.environ.get("WAKE_END_PHRASE") or "").strip()
if _end_phrase_env:
    END_LISTEN_PHRASES = _parse_wake_phrases(_end_phrase_env)
else:
    END_LISTEN_PHRASES = _parse_wake_phrases(_END_PHRASE_DEFAULT)
if not END_LISTEN_PHRASES:
    END_LISTEN_PHRASES = ["over and out"]


def _format_phrase_list(phrases: list[str]) -> str:
    if len(phrases) == 1:
        return f"'{phrases[0]}'"
    if len(phrases) == 2:
        return f"'{phrases[0]}' or '{phrases[1]}'"
    head = ", ".join(f"'{p}'" for p in phrases[:-1])
    return f"{head}, or '{phrases[-1]}'"


def format_wake_phrases() -> str:
    """Human-readable wake list, e.g. \"'Hey Jarvis' or 'Jarvis'\"."""
    return _format_phrase_list(WAKE_PHRASES)


def format_end_listen_phrases() -> str:
    primary = END_LISTEN_PHRASES[0] if END_LISTEN_PHRASES else "over and out"
    return _format_phrase_list([primary])


def format_listen_end_hint() -> str:
    """Menu Send + end-listen phrase, for STT prompts."""
    if not listen_end_enabled():
        return "Send"
    return f"Send, or {format_end_listen_phrases()}"


def _phrases_to_check(phrase: str | None) -> list[str]:
    if phrase is not None and str(phrase).strip():
        # Allow callers to pass a single phrase or a comma-list.
        parsed = _parse_wake_phrases(str(phrase))
        return parsed or [str(phrase).strip()]
    return list(WAKE_PHRASES)

def get_wake_remainder() -> str | None:
    """Command text captured with the wake utterance (phrase mode), if any."""
    global _last_wake_remainder
    rem = _last_wake_remainder
    _last_wake_remainder = None
    return rem


def _set_wake_remainder(text: str | None) -> None:
    global _last_wake_remainder
    _last_wake_remainder = (text or "").strip() or None


def get_last_wake() -> WakeHit | None:
    """Which start-wake just fired (model key + spoken label). Not consumed."""
    return _last_wake


def _set_last_wake(hit: WakeHit | None) -> None:
    global _last_wake
    _last_wake = hit


def label_for_wake_key(key: str) -> str:
    """Map an openWakeWord model id (e.g. hey_jarvis_v0.1) to a spoken label."""
    raw = (key or "").strip()
    if not raw:
        return WAKE_PHRASE
    k = raw.lower().replace("-", "_")
    k_base = re.sub(r"_v\d+(?:\.\d+)?$", "", k)
    for alias, (fname, phrase) in PRETRAINED.items():
        stem = Path(fname).stem.lower().replace("-", "_")
        stem_base = re.sub(r"_v\d+(?:\.\d+)?$", "", stem)
        if k == stem or k_base in {alias, stem_base} or k.startswith(stem):
            return phrase
    for phrase in WAKE_PHRASES:
        pkey = re.sub(r"[^\w]+", "_", phrase.lower()).strip("_")
        if k_base == pkey or k_base.replace("_", "") == pkey.replace("_", ""):
            return phrase
    cleaned = re.sub(r"_v?\d+(\.\d+)?$", "", k_base)
    cleaned = cleaned.replace("_", " ").strip()
    return cleaned.title() if cleaned else raw


def matched_wake_phrase(transcript: str, phrase: str | None = None) -> str | None:
    """Longest configured wake phrase that starts `transcript`, or None."""
    text = (transcript or "").strip().lower()
    if not text:
        return None
    norm_text = re.sub(r"[^\w\s]", " ", text)
    norm_text = re.sub(r"\s+", " ", norm_text).strip()
    best: str | None = None
    for target in sorted(_phrases_to_check(phrase), key=lambda p: len(p), reverse=True):
        norm_phrase = re.sub(r"[^\w\s]", " ", target.lower())
        norm_phrase = re.sub(r"\s+", " ", norm_phrase).strip()
        if not norm_phrase:
            continue
        if norm_text == norm_phrase or norm_text.startswith(norm_phrase + " "):
            if best is None or len(target) > len(best):
                best = target
    return best


def _afplay(sound: str, *, blocking: bool) -> bool:
    """Play a macOS system sound. Returns True if afplay was started."""
    if sys.platform != "darwin":
        return False
    try:
        import subprocess

        def _run() -> None:
            try:
                subprocess.run(
                    ["afplay", sound],
                    check=False,
                    timeout=3,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except (subprocess.TimeoutExpired, OSError):
                # afplay can hang if the output device is busy (TTS). Do not
                # dump an uncaught exception from the chime daemon thread.
                return

        if blocking:
            _run()
        else:
            threading.Thread(target=_run, name="chime", daemon=True).start()
        return True
    except Exception:
        return False


_over_and_out_chimed = threading.Event()


def reset_over_and_out_chime() -> None:
    _over_and_out_chimed.clear()


def play_wake_chime(*, force: bool = False, blocking: bool = True) -> None:
    """Tink. Off on wake-detect unless WAKE_CHIME=1; over-and-out uses force=True."""
    if not force and os.environ.get("WAKE_CHIME", "0").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return

    if _afplay(
        os.environ.get("WAKE_CHIME_SOUND", "/System/Library/Sounds/Tink.aiff"),
        blocking=blocking,
    ):
        return

    try:
        sr = 24_000
        t1 = np.linspace(0, 0.09, int(sr * 0.09), endpoint=False)
        t2 = np.linspace(0, 0.11, int(sr * 0.11), endpoint=False)
        env1 = np.linspace(1.0, 0.25, t1.size)
        env2 = np.linspace(1.0, 0.15, t2.size)
        tone1 = (0.28 * np.sin(2 * np.pi * 880.0 * t1) * env1).astype(np.float32)
        tone2 = (0.24 * np.sin(2 * np.pi * 1318.5 * t2) * env2).astype(np.float32)
        gap = np.zeros(int(sr * 0.025), dtype=np.float32)
        audio = np.concatenate([tone1, gap, tone2])
        if blocking:
            sd.play(audio, sr, blocking=True)
            sd.wait()
        else:
            sd.play(audio, sr, blocking=False)
    except Exception as e:
        print(f"[wake] chime failed: {e}", file=sys.stderr)


def play_over_and_out_chime() -> None:
    """Tink when the listen-end closer is heard. Independent of WAKE_CHIME=0."""
    if _over_and_out_chimed.is_set():
        return
    _over_and_out_chimed.set()
    play_wake_chime(force=True, blocking=False)


def play_listen_end_chime() -> None:
    """Short local cue that listening stopped and audio will be processed."""
    if os.environ.get("STT_END_CHIME", "1").strip().lower() in {"0", "false", "no", "off"}:
        return

    if _afplay(
        os.environ.get("STT_END_CHIME_SOUND", "/System/Library/Sounds/Pop.aiff"),
        blocking=True,
    ):
        return

    try:
        sr = 24_000
        t = np.linspace(0, 0.08, int(sr * 0.08), endpoint=False)
        env = np.linspace(1.0, 0.1, t.size)
        # Lower descending blip — distinct from the rising start chime.
        tone = (0.26 * np.sin(2 * np.pi * 660.0 * t) * env).astype(np.float32)
        sd.play(tone, sr, blocking=True)
        sd.wait()
    except Exception as e:
        print(f"[stt] end-chime failed: {e}", file=sys.stderr)


def play_listen_start_chime(*, blocking: bool = False) -> None:
    """Cue that the mic is open. Non-blocking so capture is not delayed."""
    if os.environ.get("STT_START_CHIME", "1").strip().lower() in {"0", "false", "no", "off"}:
        return

    if _afplay(
        os.environ.get("STT_START_CHIME_SOUND", "/System/Library/Sounds/Ping.aiff"),
        blocking=blocking,
    ):
        return

    def _tone() -> None:
        try:
            sr = 24_000
            t = np.linspace(0, 0.07, int(sr * 0.07), endpoint=False)
            env = np.linspace(1.0, 0.12, t.size)
            tone = (0.26 * np.sin(2 * np.pi * 990.0 * t) * env).astype(np.float32)
            sd.play(tone, sr, blocking=True)
            sd.wait()
        except Exception as e:
            print(f"[stt] start-chime failed: {e}", file=sys.stderr)

    if blocking:
        _tone()
    else:
        threading.Thread(target=_tone, name="chime", daemon=True).start()


def _download_file(name: str, target: Path) -> None:
    import urllib.request

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 0:
        return
    url = f"{_RELEASE_BASE}/{name}"
    print(f"[wake] downloading {name}…", flush=True)
    urllib.request.urlretrieve(url, target)


def _resolve_model_path(spec: str) -> Path:
    """Map alias / filename / path → local ONNX path (download pretrained if needed)."""
    raw = spec.strip().strip('"').strip("'")
    path = Path(raw).expanduser()
    if path.is_file():
        return path.resolve()

    # Alias
    alias = raw.lower().replace("-", "_").replace(" ", "_")
    if alias in PRETRAINED:
        fname, _ = PRETRAINED[alias]
        dest = WAKE_MODEL_DIR / fname
        _download_file(fname, dest)
        return dest

    # Filename in model dir
    candidate = WAKE_MODEL_DIR / raw
    if candidate.is_file():
        return candidate.resolve()

    # Looks like a release asset name
    if raw.endswith(".onnx"):
        dest = WAKE_MODEL_DIR / raw
        try:
            _download_file(raw, dest)
            return dest
        except Exception as e:
            raise RuntimeError(f"Could not download wake model {raw!r}: {e}") from e

    raise RuntimeError(
        f"Unknown wake model {raw!r}. Use a pretrained alias "
        f"({', '.join(sorted(set(PRETRAINED)))}), a path to a .onnx file, "
        f"or WAKE_MODE=phrase with WAKE_PHRASE set."
    )


def _spec_stems(spec: str) -> set[str]:
    raw = spec.strip().strip('"').strip("'")
    alias = raw.lower().replace("-", "_").replace(" ", "_")
    stems = {alias, Path(raw).stem.lower()}
    if alias in PRETRAINED:
        fname, _ = PRETRAINED[alias]
        stems.add(Path(fname).stem.lower())
    return {s for s in stems if s}


def keys_matching_specs(specs: list[str], all_keys: list[str]) -> list[str]:
    """Pick openWakeWord output keys that belong to the given model specs."""
    wanted: set[str] = set()
    for spec in specs:
        wanted |= _spec_stems(spec)
    matched: list[str] = []
    seen: set[str] = set()
    for key in all_keys:
        k = key.lower()
        k_base = re.sub(r"_v\d+(?:\.\d+)?$", "", k)
        if k in wanted or k_base in wanted:
            if key not in seen:
                seen.add(key)
                matched.append(key)
            continue
        if any(k.startswith(stem) or stem.startswith(k_base) for stem in wanted if len(stem) >= 4):
            if key not in seen:
                seen.add(key)
                matched.append(key)
    return matched


def _unique_specs(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for spec in group:
            key = spec.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(spec.strip())
    return out


def text_mentions_wake_phrase(text: str, phrase: str | None = None) -> bool:
    """True if `text` contains any configured wake phrase (TTS echo guard)."""
    body = (text or "").strip().lower()
    if not body:
        return False
    norm_body = re.sub(r"[^\w\s]", " ", body)
    norm_body = re.sub(r"\s+", " ", norm_body).strip()
    for target in _phrases_to_check(phrase):
        norm_phrase = re.sub(r"[^\w\s]", " ", target.lower())
        norm_phrase = re.sub(r"\s+", " ", norm_phrase).strip()
        if norm_phrase and norm_phrase in norm_body:
            return True
    return False


def matches_wake_phrase(transcript: str, phrase: str | None = None) -> bool:
    """True if transcript starts with (or equals) any configured wake phrase."""
    text = (transcript or "").strip().lower()
    if not text:
        return False
    norm_text = re.sub(r"[^\w\s]", " ", text)
    norm_text = re.sub(r"\s+", " ", norm_text).strip()
    for target in _phrases_to_check(phrase):
        norm_phrase = re.sub(r"[^\w\s]", " ", target.lower())
        norm_phrase = re.sub(r"\s+", " ", norm_phrase).strip()
        if not norm_phrase:
            continue
        if norm_text == norm_phrase or norm_text.startswith(norm_phrase + " "):
            return True
    return False


def strip_wake_phrase(utterance: str, phrase: str | None = None) -> str:
    """Remove a leading wake phrase from a transcript (tries longest match first)."""
    text = (utterance or "").strip()
    if not text:
        return text
    phrases = sorted(_phrases_to_check(phrase), key=lambda p: len(p), reverse=True)
    for target in phrases:
        words = [re.escape(w) for w in re.findall(r"\w+", target)]
        if not words:
            continue
        pattern = r"^\s*" + r"[\s,:\-]+".join(words) + r"\b[\s,:\-]*(.*)$"
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return text


def strip_trailing_wake_phrase(
    utterance: str,
    phrase: str | None = None,
    *,
    include_short: bool = False,
) -> str:
    """Remove a trailing wake phrase (used when wake ends a listen).

    Single-word phrases like "Jarvis" are only stripped from the end when
    ``include_short`` is True (wake-model hit), so "open Jarvis" stays intact
    on a normal silence-end.
    """
    text = (utterance or "").strip()
    if not text:
        return text
    if matches_wake_phrase(text, phrase):
        return ""
    phrases = sorted(_phrases_to_check(phrase), key=lambda p: len(p), reverse=True)
    for target in phrases:
        words = [re.escape(w) for w in re.findall(r"\w+", target)]
        if not words:
            continue
        if len(words) < 2 and not include_short:
            continue
        pattern = (
            r"^(.*?)(?:[\s,:\-]+)"
            + r"[\s,:\-]+".join(words)
            + r"(?:[.!?]*)\s*$"
        )
        match = re.match(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            kept = match.group(1).strip()
            if kept:
                return kept
    return text


def normalize_speech_text(text: str) -> str:
    """Lowercase, drop punctuation, fold '&' / 'n' to 'and'."""
    t = (text or "").lower().replace("&", " and ")
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\bn\b", "and", t)
    return t


def transcript_has_end_phrase(text: str, phrases: list[str] | None = None) -> bool:
    """True when transcript ends with an end-listen closer (e.g. over and out)."""
    norm = normalize_speech_text(text)
    if not norm:
        return False
    for raw in phrases or END_LISTEN_PHRASES:
        pn = normalize_speech_text(raw)
        if not pn:
            continue
        if norm == pn or norm.endswith(" " + pn):
            return True
    return False


def strip_trailing_end_phrase(utterance: str, phrases: list[str] | None = None) -> str:
    """Remove a trailing end-listen closer, allowing and/n/& variants."""
    text = (utterance or "").strip()
    if not text:
        return text
    targets = list(phrases or END_LISTEN_PHRASES)
    if any(normalize_speech_text(text) == normalize_speech_text(p) for p in targets):
        return ""
    for raw in sorted(targets, key=lambda p: len(normalize_speech_text(p)), reverse=True):
        words = re.findall(r"\w+", raw.lower())
        if not words:
            continue
        parts: list[str] = []
        for w in words:
            if w in {"and", "n"}:
                parts.append(r"(?:and|&|n)")
            else:
                parts.append(re.escape(w))
        pattern = (
            r"^(.*?)(?:[\s,:\-]+)"
            + r"[\s,:\-]+".join(parts)
            + r"(?:[.!?]*)\s*$"
        )
        match = re.match(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            kept = match.group(1).strip()
            if kept:
                return kept
    return text


def _resample_to_wake(pcm: np.ndarray, src_rate: int) -> np.ndarray:
    pcm = np.asarray(pcm, dtype=np.float32).reshape(-1)
    src_rate = int(src_rate)
    if src_rate == WAKE_RATE or pcm.size == 0:
        return pcm
    if src_rate > 0 and src_rate % WAKE_RATE == 0:
        factor = src_rate // WAKE_RATE
        n = (pcm.size // factor) * factor
        if n <= 0:
            return np.zeros(0, dtype=np.float32)
        return pcm[:n].reshape(-1, factor).mean(axis=1).astype(np.float32)
    duration = pcm.size / float(src_rate)
    target_len = max(1, int(round(duration * WAKE_RATE)))
    x_old = np.linspace(0.0, 1.0, num=pcm.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=target_len, endpoint=False)
    return np.interp(x_new, x_old, pcm).astype(np.float32)


def _score_from_predict(raw) -> float:
    try:
        return float(np.asarray(raw).reshape(-1)[0])
    except Exception:
        return 0.0


class WakeSpotter:
    """Run openWakeWord on PCM already captured for STT (no second mic)."""

    def __init__(
        self,
        *,
        threshold: float | None = None,
        ignore_seconds: float | None = None,
        model=None,
        keys: list[str] | None = None,
    ):
        self.threshold = BARGE_IN_THRESHOLD if threshold is None else float(threshold)
        ignore = WAKE_END_LISTEN_IGNORE if ignore_seconds is None else float(ignore_seconds)
        self._ignore_until = time.monotonic() + max(0.0, ignore)
        self.hit = False
        self._buf = np.zeros(0, dtype=np.float32)
        self._keys = list(keys or [])
        self._model = model
        if self._model is None:
            try:
                self._model = _ensure_model()
                self._keys = list(_model_keys or self._model.models.keys())
            except Exception as exc:
                print(f"[wake] listen-end spotter unavailable ({exc})", flush=True)
                self._model = None
                return
        if not self._keys and self._model is not None:
            try:
                self._keys = list(self._model.models.keys())
            except Exception:
                self._keys = []
        try:
            if self._model is not None:
                self._model.reset()
        except Exception:
            pass

    def feed(self, pcm: np.ndarray, sample_rate: int) -> bool:
        """Return True once when a wake phrase is detected on this stream."""
        if self.hit or self._model is None:
            return False
        frame = _resample_to_wake(pcm, sample_rate)
        if frame.size == 0:
            return False
        if time.monotonic() < self._ignore_until:
            return False
        self._buf = np.concatenate([self._buf, frame]) if self._buf.size else frame
        while self._buf.size >= CHUNK_SAMPLES:
            chunk = self._buf[:CHUNK_SAMPLES]
            self._buf = self._buf[CHUNK_SAMPLES:]
            audio = (np.clip(chunk, -1.0, 1.0) * 32767.0).astype(np.int16)
            try:
                scores = self._model.predict(audio)
            except Exception:
                return False
            for key in self._keys:
                score = _score_from_predict(
                    scores.get(key, 0.0) if isinstance(scores, dict) else scores
                )
                if score >= self.threshold:
                    self.hit = True
                    print(
                        f"[wake] listen-end via {key} (score={score:.2f})",
                        flush=True,
                    )
                    try:
                        self._model.reset()
                    except Exception:
                        pass
                    return True
        return False


def listen_end_enabled() -> bool:
    return os.environ.get("WAKE_END_LISTEN", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def listen_end_spotter() -> WakeSpotter | None:
    """Optional ONNX stop-word while listening. Phrase closers do not need this."""
    if not listen_end_enabled() or not _END_MODEL_SPECS:
        return None
    try:
        model = _ensure_model()
    except Exception as exc:
        print(f"[wake] listen-end spotter unavailable ({exc})", flush=True)
        return None
    keys = list(_end_model_keys)
    if not keys:
        return None
    return WakeSpotter(model=model, keys=keys)


def _ensure_model():
    global _model, _model_keys, _start_model_keys, _end_model_keys
    if _model is not None:
        return _model

    for fname in _FEATURE_MODELS:
        _download_file(fname, WAKE_MODEL_DIR / fname)
    # Optional VAD asset (not required when vad_threshold=0).
    try:
        _download_file("silero_vad.onnx", WAKE_MODEL_DIR / "silero_vad.onnx")
    except Exception:
        pass

    specs = _unique_specs(_MODEL_SPECS, _END_MODEL_SPECS if listen_end_enabled() else [])
    paths = [_resolve_model_path(spec) for spec in specs]
    from openwakeword.model import Model

    _model = Model(
        wakeword_models=[str(p) for p in paths],
        inference_framework="onnx",
        melspec_model_path=str(WAKE_MODEL_DIR / "melspectrogram.onnx"),
        embedding_model_path=str(WAKE_MODEL_DIR / "embedding_model.onnx"),
        vad_threshold=0.0,
    )
    _model_keys = list(_model.models.keys())
    _start_model_keys = keys_matching_specs(_MODEL_SPECS, _model_keys) or list(_model_keys)
    _end_model_keys = (
        keys_matching_specs(_END_MODEL_SPECS, _model_keys) if _END_MODEL_SPECS else []
    )
    print(
        f"[wake] model mode — say {format_wake_phrases()} to start "
        f"(models={_start_model_keys}, threshold={DEFAULT_THRESHOLD:g})",
        flush=True,
    )
    if listen_end_enabled():
        extra = f" (onnx={_end_model_keys})" if _end_model_keys else ""
        print(
            f"[wake] say {format_end_listen_phrases()} while listening to send{extra}",
            flush=True,
        )
    return _model


def _wait_for_wake_model(
    *,
    threshold: float,
    should_stop: Callable[[], bool] | None,
    poll_hz: float,
    prompt: str,
    play_chime: bool,
) -> bool:
    model = _ensure_model()
    keys = list(_start_model_keys or _model_keys or model.models.keys())
    print(f"[wake] {prompt}", flush=True)

    try:
        model.reset()
    except Exception:
        pass

    device = os.environ.get("MIC_DEVICE") or None
    if device is not None and str(device).strip().isdigit():
        device = int(str(device).strip())

    chunk_sec = CHUNK_SAMPLES / float(WAKE_RATE)
    check_every = max(1, int(round(poll_hz * chunk_sec)))
    frames = 0
    detected = False
    hit_key = None
    hit_score = 0.0

    with sd.InputStream(
        samplerate=WAKE_RATE,
        channels=1,
        dtype="float32",
        blocksize=CHUNK_SAMPLES,
        device=device,
    ) as stream:
        while True:
            if should_stop is not None and frames % check_every == 0:
                try:
                    if should_stop():
                        return False
                except Exception:
                    return False

            data, overflowed = stream.read(CHUNK_SAMPLES)
            if overflowed:
                print("[wake] mic overflow (continuing)", file=sys.stderr)
            pcm = np.asarray(data, dtype=np.float32).reshape(-1)
            if pcm.size < CHUNK_SAMPLES:
                pad = np.zeros(CHUNK_SAMPLES - pcm.size, dtype=np.float32)
                pcm = np.concatenate([pcm, pad])
            clipped = np.clip(pcm, -1.0, 1.0)
            audio = (clipped * 32767.0).astype(np.int16)

            scores = model.predict(audio)
            frames += 1
            best_key = None
            best_score = -1.0
            for key in keys:
                raw = scores.get(key, 0.0)
                try:
                    score = float(np.asarray(raw).reshape(-1)[0])
                except Exception:
                    score = 0.0
                if score >= threshold and score > best_score:
                    best_key = key
                    best_score = score
            if best_key is not None:
                hit_key = best_key
                hit_score = best_score
                detected = True
            if detected:
                try:
                    model.reset()
                except Exception:
                    pass
                break

    if detected:
        label = label_for_wake_key(hit_key or "")
        _set_last_wake(
            WakeHit(label=label, key=hit_key, score=hit_score, source="model")
        )
        print(
            f"[wake] detected {label} via {hit_key} (score={hit_score:.2f})",
            flush=True,
        )
        return True
    return False


def _wait_for_wake_phrase(
    *,
    should_stop: Callable[[], bool] | None,
    prompt: str,
    play_chime: bool,
) -> bool:
    """
    Any configured wake phrase via STT: listen for an utterance, wake if it
    starts with one of WAKE_PHRASES. Remainder is stored for get_wake_remainder().
    """
    from openai import OpenAI

    from stt import NoSpeechError, listen_for_utterance

    client = OpenAI()
    print(f"[wake] {prompt} [phrase/STT mode]", flush=True)
    print(
        f"[wake] matching {format_wake_phrases()} — speak one to activate "
        "(uses STT; set WAKE_MODE=model + a custom .onnx for offline spotting)",
        flush=True,
    )

    while True:
        if should_stop is not None:
            try:
                if should_stop():
                    return False
            except Exception:
                return False

        try:
            utterance = listen_for_utterance(
                client,
                prompt=f"Listening for {format_wake_phrases()}…",
            )
        except NoSpeechError:
            continue
        except Exception as e:
            print(f"[wake] phrase listen failed: {e}", file=sys.stderr)
            time.sleep(0.3)
            continue

        text = (utterance or "").strip()
        if not text:
            continue
        print(f'[wake] heard: "{text}"', flush=True)
        matched = matched_wake_phrase(text)
        if matched:
            remainder = strip_wake_phrase(text)
            _set_wake_remainder(remainder)
            _set_last_wake(
                WakeHit(label=matched, key=None, score=None, source="phrase")
            )
            print(
                f"[wake] detected {matched}"
                + (f" — remainder: {remainder!r}" if remainder else ""),
                flush=True,
            )
            return True
        print(f"[wake] ignored (does not start with {format_wake_phrases()})", flush=True)


def wait_for_wake(
    *,
    threshold: float | None = None,
    should_stop: Callable[[], bool] | None = None,
    poll_hz: float = 20.0,
    prompt: str | None = None,
    play_chime: bool = False,
) -> bool:
    """
    Block until the configured wake word/phrase is detected.

    Returns True on wake, False if should_stop() became true first.
    When a persistent barge-in monitor is already running, waits on that
    instead of opening a second mic (except from the monitor thread itself).
    While Sleep mode is on, wake hits are ignored until Sleep is toggled off.
    The listen-start chime plays when STT opens the mic, not here.
    """
    _set_wake_remainder(None)
    thresh = DEFAULT_THRESHOLD if threshold is None else float(threshold)
    if prompt is None:
        prompt = f"Waiting for {format_wake_phrases()}…"

    sleeping_announced = False
    while True:
        if should_stop is not None:
            try:
                if should_stop():
                    return False
            except Exception:
                return False
        if _sleep_mode_on():
            if not sleeping_announced:
                print(
                    f"[wake] Sleep — ignoring {format_wake_phrases()} "
                    "(⌘⌃S or cua sleep off)",
                    flush=True,
                )
                sleeping_announced = True
            while _sleep_mode_on():
                if should_stop is not None:
                    try:
                        if should_stop():
                            return False
                    except Exception:
                        return False
                time.sleep(0.15)
            sleeping_announced = False
            continue

        mon = get_persistent_wake()
        if (
            mon is not None
            and not mon._paused.is_set()
            and mon._thread is not None
            and threading.current_thread() is not mon._thread
        ):
            # Keep last_wake from the monitor thread; do not clear a pending hit.
            hit = mon.wait(should_stop=should_stop, prompt=prompt)
        else:
            _set_last_wake(None)
            mode = WAKE_MODE
            if mode in {"phrase", "stt", "text", "any"}:
                hit = _wait_for_wake_phrase(
                    should_stop=should_stop,
                    prompt=prompt,
                    play_chime=play_chime,
                )
            else:
                hit = _wait_for_wake_model(
                    threshold=thresh,
                    should_stop=should_stop,
                    poll_hz=poll_hz,
                    prompt=prompt,
                    play_chime=play_chime,
                )
        if hit and _sleep_mode_on():
            # Race: Sleep flipped on just as a wake landed.
            continue
        return hit


def _sleep_mode_on() -> bool:
    try:
        from app_status import sleep_mode_enabled

        return sleep_mode_enabled()
    except Exception:
        return False


def on_sleep_mode_changed(enabled: bool) -> None:
    """Pause/resume the persistent wake mic when Sleep toggles."""
    mon = get_persistent_wake()
    if mon is None:
        return
    if enabled:
        mon.woken.clear()
        mon.pause()
        print("[wake] Sleep on — mic paused", flush=True)
        return
    try:
        from app_status import read_status

        if read_status().get("stt_active"):
            print("[wake] Sleep off — wake stays paused until STT ends", flush=True)
            return
    except Exception:
        pass
    mon.resume()
    print("[wake] Sleep off — listening again", flush=True)


class WakeMonitor:
    """
    Background wake-word listener for barge-in / idle wait.

    By default runs until stop(): after each wake it stays woken until clear(),
    then listens again. Use pause()/resume() when STT needs exclusive mic access.
    """

    def __init__(self, *, threshold: float | None = None, persistent: bool = True):
        self.threshold = BARGE_IN_THRESHOLD if threshold is None else float(threshold)
        self.persistent = persistent
        self.woken = threading.Event()
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._listening = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_alive:
            return
        # Phrase/STT barge-in would fight TTS echo and burn API — use model mode only.
        if WAKE_MODE in {"phrase", "stt", "text", "any"}:
            print(
                "[wake] barge-in skipped in phrase mode (use WAKE_MODE=model for barge-in)",
                flush=True,
            )
            return
        self.woken.clear()
        self._stop.clear()
        self._paused.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="wake-persistent" if self.persistent else "wake-barge-in",
            daemon=True,
        )
        self._thread.start()
        kind = "persistent" if self.persistent else "one-shot"
        print(
            f"[wake] {kind} barge-in armed (threshold={self.threshold:g})",
            flush=True,
        )

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                while self._paused.is_set() and not self._stop.is_set():
                    self._listening.clear()
                    time.sleep(0.05)
                if self._stop.is_set():
                    break
                # Sleep mode: do not open the mic / fire barge-in.
                if _sleep_mode_on():
                    self._listening.clear()
                    self.woken.clear()
                    time.sleep(0.12)
                    continue
                # Hold here while a wake is already pending acknowledgment.
                while self.woken.is_set() and not self._stop.is_set():
                    self._listening.clear()
                    time.sleep(0.05)
                if self._stop.is_set() or self._paused.is_set() or _sleep_mode_on():
                    continue

                self._listening.set()
                # Call the model waiter directly (not wait_for_wake) to avoid
                # recursing into this persistent monitor.
                hit = _wait_for_wake_model(
                    threshold=self.threshold,
                    should_stop=lambda: (
                        self._stop.is_set()
                        or self._paused.is_set()
                        or self.woken.is_set()
                        or _sleep_mode_on()
                    ),
                    poll_hz=20.0,
                    prompt=f"Listening for {format_wake_phrases()}…",
                    play_chime=False,
                )
                self._listening.clear()
                if self._stop.is_set() or self._paused.is_set() or _sleep_mode_on():
                    continue
                if hit:
                    self.woken.set()
                    print("[wake] barge-in triggered", flush=True)
                    if not self.persistent:
                        break
        except Exception as e:
            print(f"[wake] barge-in monitor error: {e}", file=sys.stderr)
        finally:
            self._listening.clear()

    def pause(self) -> None:
        """Release the mic so STT (or another capture) can use it."""
        self._paused.set()
        # Wait briefly for the wake loop to drop the input stream.
        deadline = time.monotonic() + 2.0
        while self._listening.is_set() and time.monotonic() < deadline:
            time.sleep(0.02)

    def resume(self) -> None:
        """Resume wake listening after STT (clears a stale woken flag)."""
        self.woken.clear()
        self._paused.clear()

    def clear(self) -> None:
        """Acknowledge a wake so listening can continue (persistent mode)."""
        self.woken.clear()

    def wait(
        self,
        *,
        should_stop: Callable[[], bool] | None = None,
        prompt: str | None = None,
        timeout: float | None = None,
    ) -> bool:
        """
        Block until woken (or should_stop / timeout).

        Assumes this monitor is already started and not paused.
        """
        if prompt:
            print(f"[wake] {prompt}", flush=True)
        started = time.monotonic()
        while True:
            if self.woken.is_set():
                return True
            if should_stop is not None:
                try:
                    if should_stop():
                        return False
                except Exception:
                    return False
            if timeout is not None and (time.monotonic() - started) >= timeout:
                return False
            time.sleep(0.05)

    def stop(self) -> None:
        self._stop.set()
        self._paused.clear()
        self.woken.set()  # unblock waiters / inner wait_for_wake
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        self.woken.clear()


_persistent_wake: WakeMonitor | None = None
_persistent_lock = threading.Lock()


def ensure_persistent_wake(*, threshold: float | None = None) -> WakeMonitor | None:
    """
    Start (or return) the process-wide wake monitor.

    Call before the first TTS so barge-in is armed during synthesis + playback.
    Returns None in phrase/STT wake mode.
    """
    global _persistent_wake
    with _persistent_lock:
        if _persistent_wake is not None and _persistent_wake.is_alive:
            return _persistent_wake
        monitor = WakeMonitor(threshold=threshold, persistent=True)
        monitor.start()
        if not monitor.is_alive:
            return None
        _persistent_wake = monitor
        return _persistent_wake


def get_persistent_wake() -> WakeMonitor | None:
    with _persistent_lock:
        if _persistent_wake is not None and _persistent_wake.is_alive:
            return _persistent_wake
        return None


def pause_persistent_wake() -> None:
    mon = get_persistent_wake()
    if mon is not None:
        mon.pause()


def resume_persistent_wake() -> None:
    mon = get_persistent_wake()
    if mon is not None:
        if _sleep_mode_on():
            return
        mon.resume()


def stop_persistent_wake() -> None:
    global _persistent_wake
    with _persistent_lock:
        mon = _persistent_wake
        _persistent_wake = None
    if mon is not None:
        mon.stop()


def listen_after_wake(
    client,
    *,
    listen_fn,
    should_stop: Callable[[], bool] | None = None,
    threshold: float | None = None,
    wake_prompt: str | None = None,
    listen_prompt: str | None = None,
) -> str | None:
    """
    Wait for wake word, then capture one utterance via listen_fn(client, ...).

    Returns the transcript, or None if stopped before wake / listen failed empty.
    """
    mon = get_persistent_wake()
    if mon is not None and not mon._paused.is_set():
        if not mon.wait(should_stop=should_stop, prompt=wake_prompt):
            return None
        mon.clear()
    elif not wait_for_wake(
        threshold=threshold,
        should_stop=should_stop,
        prompt=wake_prompt,
    ):
        return None
    rem = get_wake_remainder()
    if rem:
        return rem
    time.sleep(0.05)
    try:
        return listen_fn(
            client,
            prompt=listen_prompt or "Listening…",
        )
    except Exception as e:
        print(f"[wake] listen failed after wake: {e}", file=sys.stderr)
        return None
