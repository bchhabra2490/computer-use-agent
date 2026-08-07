"""
Local wake-word detection for the voice orchestrator.

Two modes (WAKE_MODE):
  - model  — openWakeWord ONNX classifier (pretrained or your custom .onnx)
  - phrase — any phrase via STT matching (no model training; uses the STT API)

Examples:
  WAKE_MODEL=hey_jarvis WAKE_PHRASE="Hey Jarvis"          # default
  WAKE_MODEL=alexa WAKE_PHRASE=Alexa
  WAKE_MODEL=/path/to/hey_bob.onnx WAKE_PHRASE="Hey Bob" # custom ONNX
  WAKE_MODE=phrase WAKE_PHRASE="Okay Computer"           # any phrase
"""

from __future__ import annotations

import os
import re
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import sounddevice as sd

WAKE_RATE = 16_000
# openWakeWord expects 80 ms frames (1280 samples @ 16 kHz).
CHUNK_SAMPLES = 1280
DEFAULT_THRESHOLD = float(os.environ.get("WAKE_THRESHOLD", "0.5"))
# Slightly higher bar while TTS is playing (reduce echo false triggers).
BARGE_IN_THRESHOLD = float(os.environ.get("WAKE_BARGE_THRESHOLD", "0.6"))
WAKE_MODEL_DIR = Path(
    os.environ.get(
        "WAKE_MODEL_DIR",
        str(Path(__file__).resolve().parent / "models" / "wake"),
    )
)
WAKE_MODE = (os.environ.get("WAKE_MODE") or "model").strip().lower()
# Comma-separated aliases, filenames, or paths. Default: hey jarvis.
WAKE_MODEL = (os.environ.get("WAKE_MODEL") or "hey_jarvis").strip()

# Shared feature extractors always required for model mode.
_FEATURE_MODELS = (
    "embedding_model.onnx",
    "melspectrogram.onnx",
)

# Alias → release asset + default spoken phrase.
PRETRAINED: dict[str, tuple[str, str]] = {
    "hey_jarvis": ("hey_jarvis_v0.1.onnx", "Hey Jarvis"),
    "jarvis": ("hey_jarvis_v0.1.onnx", "Hey Jarvis"),
    "alexa": ("alexa_v0.1.onnx", "Alexa"),
    "hey_mycroft": ("hey_mycroft_v0.1.onnx", "Hey Mycroft"),
    "mycroft": ("hey_mycroft_v0.1.onnx", "Hey Mycroft"),
    "hey_rhasspy": ("hey_rhasspy_v0.1.onnx", "Hey Rhasspy"),
    "rhasspy": ("hey_rhasspy_v0.1.onnx", "Hey Rhasspy"),
    "timer": ("timer_v0.1.onnx", "Timer"),
    "weather": ("weather_v0.1.onnx", "Weather"),
}

_RELEASE_BASE = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1"

_model = None
_model_keys: list[str] = []
_last_wake_remainder: str | None = None


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


_MODEL_SPECS = _parse_model_specs()
WAKE_PHRASE = (os.environ.get("WAKE_PHRASE") or "").strip() or (
    _default_phrase_for_models(_MODEL_SPECS) if WAKE_MODE != "phrase" else "Hey Jarvis"
)
if WAKE_MODE == "phrase" and not (os.environ.get("WAKE_PHRASE") or "").strip():
    # Phrase mode with no phrase set — keep a sensible default the user can override.
    WAKE_PHRASE = os.environ.get("WAKE_PHRASE", "Hey Jarvis").strip() or "Hey Jarvis"


def get_wake_remainder() -> str | None:
    """Command text captured with the wake utterance (phrase mode), if any."""
    global _last_wake_remainder
    rem = _last_wake_remainder
    _last_wake_remainder = None
    return rem


def _set_wake_remainder(text: str | None) -> None:
    global _last_wake_remainder
    _last_wake_remainder = (text or "").strip() or None


def play_wake_chime() -> None:
    """Short local cue that the wake word was heard (no API)."""
    if os.environ.get("WAKE_CHIME", "1").strip().lower() in {"0", "false", "no", "off"}:
        return

    if sys.platform == "darwin":
        sound = os.environ.get(
            "WAKE_CHIME_SOUND",
            "/System/Library/Sounds/Tink.aiff",
        )
        try:
            import subprocess

            subprocess.run(
                ["afplay", sound],
                check=False,
                timeout=3,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception as e:
            print(f"[wake] afplay chime failed ({e}); trying tone", file=sys.stderr)

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
        sd.play(audio, sr, blocking=True)
        sd.wait()
    except Exception as e:
        print(f"[wake] chime failed: {e}", file=sys.stderr)


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


def matches_wake_phrase(transcript: str, phrase: str | None = None) -> bool:
    """True if transcript starts with (or equals) the wake phrase."""
    text = (transcript or "").strip().lower()
    target = (phrase or WAKE_PHRASE).strip().lower()
    if not text or not target:
        return False
    # Allow light punctuation between words.
    norm_text = re.sub(r"[^\w\s]", " ", text)
    norm_text = re.sub(r"\s+", " ", norm_text).strip()
    norm_phrase = re.sub(r"[^\w\s]", " ", target)
    norm_phrase = re.sub(r"\s+", " ", norm_phrase).strip()
    if not norm_phrase:
        return False
    return norm_text == norm_phrase or norm_text.startswith(norm_phrase + " ")


def strip_wake_phrase(utterance: str, phrase: str | None = None) -> str:
    """Remove a leading wake phrase from a transcript."""
    text = (utterance or "").strip()
    target = (phrase or WAKE_PHRASE).strip()
    if not text or not target:
        return text
    # Build a flexible regex from the phrase words.
    words = [re.escape(w) for w in re.findall(r"\w+", target)]
    if not words:
        return text
    pattern = r"^\s*" + r"[\s,:\-]+".join(words) + r"\b[\s,:\-]*(.*)$"
    match = re.match(pattern, text, flags=re.IGNORECASE)
    if not match:
        return text
    return match.group(1).strip()


def _ensure_model():
    global _model, _model_keys
    if _model is not None:
        return _model

    for fname in _FEATURE_MODELS:
        _download_file(fname, WAKE_MODEL_DIR / fname)
    # Optional VAD asset (not required when vad_threshold=0).
    try:
        _download_file("silero_vad.onnx", WAKE_MODEL_DIR / "silero_vad.onnx")
    except Exception:
        pass

    paths = [_resolve_model_path(spec) for spec in _MODEL_SPECS]
    from openwakeword.model import Model

    _model = Model(
        wakeword_models=[str(p) for p in paths],
        inference_framework="onnx",
        melspec_model_path=str(WAKE_MODEL_DIR / "melspectrogram.onnx"),
        embedding_model_path=str(WAKE_MODEL_DIR / "embedding_model.onnx"),
        vad_threshold=0.0,
    )
    _model_keys = list(_model.models.keys())
    print(
        f"[wake] model mode — say '{WAKE_PHRASE}' " f"(models={_model_keys}, threshold={DEFAULT_THRESHOLD:g})",
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
    keys = _model_keys or list(model.models.keys())
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
            for key in keys:
                raw = scores.get(key, 0.0)
                try:
                    score = float(np.asarray(raw).reshape(-1)[0])
                except Exception:
                    score = 0.0
                if score >= threshold:
                    hit_key = key
                    hit_score = score
                    detected = True
                    break
            if detected:
                try:
                    model.reset()
                except Exception:
                    pass
                break

    if detected:
        print(
            f"[wake] detected '{WAKE_PHRASE}' via {hit_key} (score={hit_score:.2f})",
            flush=True,
        )
        if play_chime:
            play_wake_chime()
        return True
    return False


def _wait_for_wake_phrase(
    *,
    should_stop: Callable[[], bool] | None,
    prompt: str,
    play_chime: bool,
) -> bool:
    """
    Any wake phrase via STT: listen for an utterance, wake if it starts with WAKE_PHRASE.
    Remainder (if any) is stored for get_wake_remainder().
    """
    from openai import OpenAI

    from stt import NoSpeechError, listen_for_utterance

    client = OpenAI()
    print(f"[wake] {prompt} [phrase/STT mode]", flush=True)
    print(
        f"[wake] matching phrase {WAKE_PHRASE!r} — speak it to activate "
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
                prompt=f"Listening for '{WAKE_PHRASE}'…",
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
        if matches_wake_phrase(text, WAKE_PHRASE):
            remainder = strip_wake_phrase(text, WAKE_PHRASE)
            _set_wake_remainder(remainder)
            print(
                f"[wake] detected phrase '{WAKE_PHRASE}'" + (f" — remainder: {remainder!r}" if remainder else ""),
                flush=True,
            )
            if play_chime:
                play_wake_chime()
            return True
        print(f"[wake] ignored (does not start with '{WAKE_PHRASE}')", flush=True)


def wait_for_wake(
    *,
    threshold: float | None = None,
    should_stop: Callable[[], bool] | None = None,
    poll_hz: float = 20.0,
    prompt: str | None = None,
    play_chime: bool = True,
) -> bool:
    """
    Block until the configured wake word/phrase is detected.

    Returns True on wake, False if should_stop() became true first.
    """
    _set_wake_remainder(None)
    thresh = DEFAULT_THRESHOLD if threshold is None else float(threshold)
    if prompt is None:
        prompt = f"Waiting for '{WAKE_PHRASE}'…"

    mode = WAKE_MODE
    if mode in {"phrase", "stt", "text", "any"}:
        return _wait_for_wake_phrase(
            should_stop=should_stop,
            prompt=prompt,
            play_chime=play_chime,
        )
    return _wait_for_wake_model(
        threshold=thresh,
        should_stop=should_stop,
        poll_hz=poll_hz,
        prompt=prompt,
        play_chime=play_chime,
    )


class WakeMonitor:
    """
    Background wake-word listener for TTS barge-in.

    Start while speaking; if the wake word is heard, `woken` is set and the chime plays.
    Call stop() when playback ends (whether interrupted or not).
    """

    def __init__(self, *, threshold: float | None = None):
        self.threshold = BARGE_IN_THRESHOLD if threshold is None else float(threshold)
        self.woken = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
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
        self._thread = threading.Thread(
            target=self._run,
            name="wake-barge-in",
            daemon=True,
        )
        self._thread.start()
        print(f"[wake] barge-in armed (threshold={self.threshold:g})", flush=True)

    def _run(self) -> None:
        try:
            hit = wait_for_wake(
                threshold=self.threshold,
                should_stop=lambda: self._stop.is_set() or self.woken.is_set(),
                prompt=f"Barge-in: say '{WAKE_PHRASE}' to interrupt…",
                play_chime=False,
            )
            if hit:
                self.woken.set()
                print("[wake] barge-in triggered — stopping TTS", flush=True)
                time.sleep(0.08)
                play_wake_chime()
        except Exception as e:
            print(f"[wake] barge-in monitor error: {e}", file=sys.stderr)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None


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
    if not wait_for_wake(
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
