"""Optional local Smart Turn v3 endpoint classifier.

The classifier is deliberately lazy and fail-open: importing STT does not load a
model, and callers can keep their existing endpoint policy if setup or inference
fails.
"""

from __future__ import annotations

import threading
import urllib.request
from pathlib import Path
from typing import Callable

import numpy as np

MODEL_RATE = 16_000
MODEL_SECONDS = 8
MODEL_NAME = "smart-turn-v3.2-cpu.onnx"
MODEL_URL = (
    "https://huggingface.co/pipecat-ai/smart-turn-v3/resolve/main/"
    + MODEL_NAME
)


class SmartTurnClassifier:
    """Run Smart Turn ONNX inference on mono float PCM."""

    def __init__(self, model_path: Path, *, threshold: float = 0.5) -> None:
        self.model_path = Path(model_path)
        self.threshold = float(threshold)
        self._session = None
        self._feature_extractor = None
        self._load_lock = threading.Lock()

    def _load(self) -> None:
        if self._session is not None:
            return
        with self._load_lock:
            if self._session is not None:
                return
            import onnxruntime as ort
            from transformers import WhisperFeatureExtractor

            options = ort.SessionOptions()
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            options.inter_op_num_threads = 1
            options.intra_op_num_threads = 1
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self._session = ort.InferenceSession(str(self.model_path), sess_options=options)
            self._feature_extractor = WhisperFeatureExtractor(chunk_length=MODEL_SECONDS)

    @staticmethod
    def prepare_audio(audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """Return the last eight seconds as 16 kHz PCM, left-padded with silence."""
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        if sample_rate != MODEL_RATE and samples.size:
            old_x = np.arange(samples.size, dtype=np.float64)
            new_size = max(1, int(round(samples.size * MODEL_RATE / sample_rate)))
            new_x = np.linspace(0, samples.size - 1, new_size)
            samples = np.interp(new_x, old_x, samples).astype(np.float32)
        target = MODEL_RATE * MODEL_SECONDS
        if samples.size > target:
            samples = samples[-target:]
        elif samples.size < target:
            samples = np.pad(samples, (target - samples.size, 0))
        return samples.astype(np.float32, copy=False)

    def probability(self, audio: np.ndarray, sample_rate: int) -> float:
        self._load()
        prepared = self.prepare_audio(audio, sample_rate)
        inputs = self._feature_extractor(
            prepared,
            sampling_rate=MODEL_RATE,
            return_tensors="np",
            padding="max_length",
            max_length=MODEL_RATE * MODEL_SECONDS,
            truncation=True,
            do_normalize=True,
        )
        features = np.expand_dims(
            inputs.input_features.squeeze(0).astype(np.float32), axis=0
        )
        outputs = self._session.run(None, {"input_features": features})
        return float(np.asarray(outputs[0]).reshape(-1)[0])

    def is_complete(self, audio: np.ndarray, sample_rate: int) -> tuple[bool, float]:
        probability = self.probability(audio, sample_rate)
        return probability >= self.threshold, probability


def ensure_model(
    model_path: Path, *, downloader: Callable[[str, str], object] = urllib.request.urlretrieve
) -> Path:
    """Download the small CPU model once when the optional feature is enabled."""
    path = Path(model_path).expanduser()
    if path.exists() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    try:
        downloader(MODEL_URL, str(partial))
        partial.replace(path)
    finally:
        if partial.exists():
            partial.unlink()
    return path
