"""
Local wake-word detection for the voice orchestrator.

Uses openWakeWord's pretrained "hey jarvis" model. The mic stays on locally
(no cloud STT) until the wake word fires, then the caller opens full STT.
"""

from __future__ import annotations

import os
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
# Phrase users should say (pretrained openWakeWord model).
WAKE_PHRASE = os.environ.get("WAKE_PHRASE", "Hey Jarvis")

_REQUIRED = (
    "hey_jarvis_v0.1.onnx",
    "embedding_model.onnx",
    "melspectrogram.onnx",
)

_model = None
_model_key: str | None = None


def play_wake_chime() -> None:
    """Short local cue that Jarvis heard the wake word and is listening (no API)."""
    if os.environ.get("WAKE_CHIME", "1").strip().lower() in {"0", "false", "no", "off"}:
        return

    # Prefer macOS system sound — reliable right after closing the mic stream.
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


def _download_models(target: Path) -> None:
    """Fetch ONNX assets into target (idempotent)."""
    import urllib.request

    base = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1"
    files = list(_REQUIRED) + ["silero_vad.onnx"]
    target.mkdir(parents=True, exist_ok=True)
    for name in files:
        path = target / name
        if path.exists() and path.stat().st_size > 0:
            continue
        url = f"{base}/{name}"
        print(f"[wake] downloading {name}…", flush=True)
        urllib.request.urlretrieve(url, path)


def _ensure_model():
    global _model, _model_key
    if _model is not None:
        return _model

    missing = [n for n in _REQUIRED if not (WAKE_MODEL_DIR / n).exists()]
    if missing:
        try:
            _download_models(WAKE_MODEL_DIR)
        except Exception as e:
            raise RuntimeError(
                f"Wake-word models missing under {WAKE_MODEL_DIR} ({', '.join(missing)}). "
                f"Auto-download failed: {e}"
            ) from e
        missing = [n for n in _REQUIRED if not (WAKE_MODEL_DIR / n).exists()]
        if missing:
            raise RuntimeError(f"Wake-word models still missing: {', '.join(missing)} in {WAKE_MODEL_DIR}")

    from openwakeword.model import Model

    wake_path = str(WAKE_MODEL_DIR / "hey_jarvis_v0.1.onnx")
    # vad_threshold=0 skips Silero VAD (avoids needing silero in the package tree).
    _model = Model(
        wakeword_models=[wake_path],
        inference_framework="onnx",
        melspec_model_path=str(WAKE_MODEL_DIR / "melspectrogram.onnx"),
        embedding_model_path=str(WAKE_MODEL_DIR / "embedding_model.onnx"),
        vad_threshold=0.0,
    )
    _model_key = next(iter(_model.models.keys()))
    print(
        f"[wake] ready — say '{WAKE_PHRASE}' (model={_model_key}, " f"threshold={DEFAULT_THRESHOLD:g})",
        flush=True,
    )
    return _model


def wait_for_wake(
    *,
    threshold: float | None = None,
    should_stop: Callable[[], bool] | None = None,
    poll_hz: float = 20.0,
    prompt: str | None = None,
    play_chime: bool = True,
) -> bool:
    """
    Block until the Jarvis wake word is detected.

    Returns True on wake, False if should_stop() became true first.
    Local-only — does not call the cloud STT API.
    """
    model = _ensure_model()
    key = _model_key or next(iter(model.models.keys()))
    thresh = DEFAULT_THRESHOLD if threshold is None else float(threshold)
    if prompt is None:
        prompt = f"Waiting for '{WAKE_PHRASE}'…"
    print(f"[wake] {prompt}", flush=True)

    # Reset streaming state between waits.
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
            # openWakeWord expects int16 PCM.
            clipped = np.clip(pcm, -1.0, 1.0)
            audio = (clipped * 32767.0).astype(np.int16)

            scores = model.predict(audio)
            frames += 1
            raw = scores.get(key, 0.0)
            try:
                score = float(np.asarray(raw).reshape(-1)[0])
            except Exception:
                score = 0.0
            if score >= thresh:
                print(f"[wake] detected '{WAKE_PHRASE}' (score={score:.2f})", flush=True)
                try:
                    model.reset()
                except Exception:
                    pass
                detected = True
                break

    if detected:
        # Play after closing the mic stream so output doesn't fight the input device.
        if play_chime:
            play_wake_chime()
        return True
    return False


class WakeMonitor:
    """
    Background wake-word listener for TTS barge-in.

    Start while speaking; if Hey Jarvis is heard, `woken` is set and the chime plays.
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
            # No chime until TTS is stopped — set woken first so playback ends ASAP.
            hit = wait_for_wake(
                threshold=self.threshold,
                should_stop=lambda: self._stop.is_set() or self.woken.is_set(),
                prompt=f"Barge-in: say '{WAKE_PHRASE}' to interrupt…",
                play_chime=False,
            )
            if hit:
                self.woken.set()
                print("[wake] barge-in triggered — stopping TTS", flush=True)
                # Brief pause so sd.stop() can release the output device.
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
    # Chime already played in wait_for_wake; brief gap before STT.
    time.sleep(0.05)
    try:
        return listen_fn(
            client,
            prompt=listen_prompt or "Listening…",
        )
    except Exception as e:
        print(f"[wake] listen failed after wake: {e}", file=sys.stderr)
        return None
