"""Whether media is playing on the Mac — for the computer-use agent.

Reports only playing / not playing (Music.app / Spotify). No track titles,
no Jarvis TTS. Browser YouTube is not probed (needs loopback).

Set ``SPEAKER_OUTPUT_FEEDBACK=0`` to disable.
"""

from __future__ import annotations

import os
import subprocess
import time

_OFF = {"0", "false", "no", "off"}

ENABLED = os.environ.get("SPEAKER_OUTPUT_FEEDBACK", "1").strip().lower() not in _OFF
PROBE_TTL = float(os.environ.get("SPEAKER_OUTPUT_PROBE_TTL", "1.5"))

_cache_at = 0.0
_cache_playing: bool | None = None
_last_block: str | None = None


def _osascript(script: str, *, timeout: float = 1.5) -> str:
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def _app_playing(app: str) -> bool:
    running = _osascript(
        f'tell application "System Events" to (name of processes) contains "{app}"'
    )
    if running.lower() != "true":
        return False
    state = _osascript(f'tell application "{app}" to get player state as string')
    return state.lower() == "playing"


def media_playing(*, force: bool = False) -> bool:
    """True when Music or Spotify reports player state ``playing``."""
    global _cache_at, _cache_playing
    now = time.monotonic()
    if (
        not force
        and _cache_playing is not None
        and (now - _cache_at) < PROBE_TTL
    ):
        return _cache_playing
    playing = False
    for app in ("Music", "Spotify"):
        try:
            if _app_playing(app):
                playing = True
                break
        except Exception:
            continue
    _cache_playing = playing
    _cache_at = now
    return playing


def reset_speaker_output_history() -> None:
    """Forget the last injected line (call at the start of an agent run)."""
    global _last_block
    _last_block = None


def speaker_output_block(*, force_media: bool = False, always: bool = False) -> str:
    """One-line status for the agent, or empty when disabled / unchanged."""
    global _last_block
    if not ENABLED:
        return ""
    try:
        playing = media_playing(force=force_media)
    except Exception:
        playing = False
    block = "Media playing: yes" if playing else "Media playing: no"
    if not always and _last_block == block:
        return ""
    _last_block = block
    return block
