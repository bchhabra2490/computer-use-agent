"""Load a local .env into os.environ (no external dependency)."""

from __future__ import annotations

import os
from pathlib import Path


def configure_native_threads() -> None:
    """
    Cap BLAS/OpenMP threads before numpy/OpenBLAS loads.

    Unbounded OpenBLAS threading is a common macOS SIGSEGV
    (``gemm_thread_n`` stack overflow) during orchestrator startup.
    """
    for key in (
        "OPENBLAS_NUM_THREADS",
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ.setdefault(key, "1")


def load_dotenv(path: str | Path | None = None, *, override: bool = False) -> Path | None:
    """
    Parse KEY=VALUE lines from `.env` into the process environment.

    By default does not override variables already set in the shell.
    Always applies :func:`configure_native_threads` afterward.
    Returns the path loaded, or None if missing.
    """
    env_path = Path(path) if path else Path(__file__).resolve().parent / ".env"
    loaded: Path | None = None
    if env_path.is_file():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if not key:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            if not override and key in os.environ:
                continue
            os.environ[key] = value
        loaded = env_path
    configure_native_threads()
    return loaded
