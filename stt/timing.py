"""Wall-clock + duration lines so STT steps can be compared.

Lines look like::

    [stt-timing] 14:43:01.250 load_model 3214ms model=small.en cold=1

``STT_TIMING=0`` disables console and file. File: ``stt_latency.log`` in the repo root.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_OFF = {"0", "false", "no", "off"}
STT_TIMING = os.environ.get("STT_TIMING", "1").strip().lower() not in _OFF
_LOG_PATH = Path(__file__).resolve().parent.parent / "stt_latency.log"


def wall_clock() -> str:
    t = time.time()
    return time.strftime("%H:%M:%S", time.localtime(t)) + f".{int((t % 1) * 1000):03d}"


def log_timing(fn: str, ms: float, **fields: object) -> None:
    if not STT_TIMING:
        return
    extra = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None and v != "")
    line = f"[stt-timing] {wall_clock()} {fn} {ms:.0f}ms"
    if extra:
        line = f"{line} {extra}"
    print(line, flush=True)
    try:
        with _LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


@contextmanager
def timed(fn: str, **fields: object) -> Iterator[None]:
    """Log how long ``fn`` took. Timestamp is when the step finished."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        log_timing(fn, (time.perf_counter() - t0) * 1000.0, **fields)
