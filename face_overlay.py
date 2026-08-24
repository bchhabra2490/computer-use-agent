"""Top-center face overlay (macOS) — blobatar-inspired blob by session mood.

Soft geometric body + two capsule eyes (no mouth), in the spirit of
https://blobatar.dev/ — a pebble silhouette, high-contrast capsules, and
poses that only move parts the blob already has.

Any string is a blobatar. ``pebble`` / ``droplet`` / ``cloud`` / ``sun`` are
curated shortcuts; every other name hashes to a stable silhouette (same
shape bands as blobatar gen2). Switch with ``cua face NAME``.

Click-through NSPanel with ``NSWindowSharingNone`` so it stays out of
screenshots when possible; ``pause_overlay_for_capture`` also hides it.

Moods (from ``status.json`` state / live TTS):
  sleep   — waiting / idle (sleepy lids, sunk body)
  listen  — listening (open capsules, blink + glance)
  unsure  — ask_user (one eye squeezed, pair barely moved)
  speak   — TTS playing (tall happy capsules, bounce)
  think   — thinking / agent (seesaw eye heights)
"""

from __future__ import annotations

import math
import os
import time
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app_status import RUNTIME_DIR, read_status

FACE_WIDTH = int(os.environ.get("FACE_OVERLAY_WIDTH", "128"))
FACE_HEIGHT = int(os.environ.get("FACE_OVERLAY_HEIGHT", "128"))
FACE_MARGIN_TOP = int(os.environ.get("FACE_OVERLAY_MARGIN_TOP", "10"))
FACE_FPS = float(os.environ.get("FACE_OVERLAY_FPS", "20"))
FACE_HUE = float(os.environ.get("FACE_OVERLAY_HUE", "198"))

# Default organic outline (pebble). Other blobatars carry their own.
_BLOB_PERTURB = (0.08, -0.12, 0.05, 0.14, -0.07, 0.10, -0.10, 0.04)

PRESET_PATH = RUNTIME_DIR / "face_preset"


@dataclass(frozen=True)
class BlobatarSpec:
    """One selectable creature. ``extras`` are extra ovals (dx, dy, w, h) in body units."""

    id: str
    title: str
    blurb: str
    hue: float
    sat: float
    rx: float
    ry: float
    perturb: tuple[float, ...]
    extras: tuple[tuple[float, float, float, float], ...] = ()
    pair_dx: float = 0.30
    pair_dy: float = 0.0
    shape: str = "organic"  # organic | round | boxy | capsule
    rot: float = 0.0


BLOBATARS: dict[str, BlobatarSpec] = {
    "pebble": BlobatarSpec(
        id="pebble",
        title="Pebble",
        blurb="teal round pebble",
        hue=198,
        sat=0.52,
        rx=0.38,
        ry=0.36,
        perturb=_BLOB_PERTURB,
        extras=((-0.64, 0.36, 0.62, 0.62),),
    ),
    "droplet": BlobatarSpec(
        id="droplet",
        title="Droplet",
        blurb="coral teardrop",
        hue=18,
        sat=0.58,
        rx=0.32,
        ry=0.42,
        perturb=(0.04, -0.06, 0.02, 0.08, 0.22, 0.08, 0.02, -0.06),
        extras=((0.0, -0.62, 0.42, 0.36),),
        pair_dx=0.28,
        pair_dy=-0.06,
    ),
    "cloud": BlobatarSpec(
        id="cloud",
        title="Cloud",
        blurb="lavender cloud",
        hue=268,
        sat=0.42,
        rx=0.36,
        ry=0.30,
        perturb=(0.06, -0.04, 0.10, -0.02, 0.08, -0.05, 0.09, -0.03),
        extras=(
            (-0.58, 0.06, 0.72, 0.62),
            (0.52, 0.10, 0.68, 0.58),
            (0.0, -0.48, 0.70, 0.55),
        ),
        pair_dx=0.26,
        pair_dy=0.04,
    ),
    "sun": BlobatarSpec(
        id="sun",
        title="Sun",
        blurb="amber sun with petals",
        hue=42,
        sat=0.62,
        rx=0.30,
        ry=0.30,
        perturb=(0.02, -0.02, 0.03, -0.01, 0.02, -0.02, 0.03, -0.01),
        extras=tuple(
            (
                0.92 * math.cos(i * math.pi / 4.0),
                0.92 * math.sin(i * math.pi / 4.0),
                0.30,
                0.30,
            )
            for i in range(8)
        ),
        pair_dx=0.27,
        pair_dy=-0.02,
    ),
}

_PRESET_ALIASES = {
    "pebble": "pebble",
    "kiwi": "pebble",
    "teal": "pebble",
    "droplet": "droplet",
    "drop": "droplet",
    "coral": "droplet",
    "cloud": "cloud",
    "lavender": "cloud",
    "sun": "sun",
    "solar": "sun",
    "amber": "sun",
}

# Blobatar gen2 shape bands (https://blobatar.dev) — round/organic everyday, louder shapes rarer.
_SHAPE_BANDS: tuple[tuple[str, float], ...] = (
    ("round", 0.22),
    ("organic", 0.48),
    ("boxy", 0.6),
    ("capsule", 0.7),
    ("nub", 0.79),
    ("cloud", 0.86),
    ("droplet", 0.915),
    ("hexagon", 0.95),
    ("sun", 0.98),
    ("triangle", 1.0),
)
_SHAPE_CORE = {
    "round": 1.0,
    "organic": 0.98,
    "boxy": 0.86,
    "capsule": 1.02,
    "nub": 0.88,
    "cloud": 0.78,
    "droplet": 0.78,
    "hexagon": 1.05,
    "sun": 0.70,
    "triangle": 1.15,
}
_MAX_SEED_LEN = 128
_RESERVED_FACE_ARGS = frozenset({"list", "ls", "status"})


def blobatar_ids() -> tuple[str, ...]:
    return tuple(BLOBATARS)


def _normalize_seed(name: str) -> str:
    return unicodedata.normalize("NFC", str(name)).strip().lower()


def _valid_seed(name: str) -> bool:
    if not name or len(name) > _MAX_SEED_LEN:
        return False
    if any(ch in name for ch in ("\n", "\r", "\0", "/", "\\")):
        return False
    return True


def _i32(n: int) -> int:
    n &= 0xFFFFFFFF
    return n - 0x100000000 if n >= 0x80000000 else n


def _u32(n: int) -> int:
    return n & 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    return _i32(a * b)


def _feed(h: int, data: bytes) -> int:
    for byte in data:
        h = _imul(h ^ byte, 3432918353)
        h = _i32((h << 13) | (_u32(h) >> 19))
    return h


def _finalize(h: int) -> int:
    h = _imul(h ^ (_u32(h) >> 16), 2246822507)
    h = _imul(h ^ (_u32(h) >> 13), 3266489909)
    return _u32(h ^ (_u32(h) >> 16))


def _seed_state(name: str) -> int:
    return _feed(1779033703 ^ len(name), name.encode("utf-8"))


def _trait(state: int, key: str) -> float:
    return _finalize(_feed(_feed(state, b"\xff"), key.encode("utf-8"))) / 4294967296.0


def _num(state: int, key: str, lo: float, hi: float) -> float:
    return lo + _trait(state, key) * (hi - lo)


def _int(state: int, key: str, lo: int, hi: int) -> int:
    return lo + int(_trait(state, key) * (hi - lo + 1))


def _jitter(state: int, key: str, amount: float) -> float:
    return (_trait(state, key) * 2.0 - 1.0) * amount


def _pick_shape(value: float) -> str:
    for name, up_to in _SHAPE_BANDS:
        if value < up_to:
            return name
    return "triangle"


def _extras_circle(dx: float, dy: float, radius: float) -> tuple[float, float, float, float]:
    span = max(0.16, radius * 2.0)
    return (dx, dy, span, span)


@lru_cache(maxsize=64)
def _hashed_blobatar(name: str) -> BlobatarSpec:
    """Deterministic silhouette from any seed, using blobatar gen2 bands."""
    state = _seed_state(name)
    kind = _pick_shape(_trait(state, "shape"))
    hue = _trait(state, "hue") * 360.0
    sat = _num(state, "tone", 0.40, 0.62)
    core = _SHAPE_CORE[kind]
    r = 0.36 * core
    ratio = _num(state, "body.ratio", 0.92, 1.08)
    rx, ry = r, r * ratio
    perturb: tuple[float, ...] = _BLOB_PERTURB
    extras: tuple[tuple[float, float, float, float], ...] = ()
    pair_dx = 0.24 + _trait(state, "eye.gap") * 0.12
    pair_dy = _num(state, "gaze.y", -0.08, 0.06)
    rot = 0.0
    draw = "organic"

    if kind == "round":
        draw = "round"
        perturb = (0.0,) * 8
    elif kind == "organic":
        n = _int(state, "body.pts", 6, 8)
        perturb = tuple(_jitter(state, f"body.r{i}", 0.16) for i in range(n))
    elif kind == "boxy":
        draw = "boxy"
        rot = _num(state, "body.rot", -20.0, 20.0)
        perturb = (0.02, -0.01, 0.02, -0.01, 0.02, -0.01, 0.02, -0.01)
    elif kind == "capsule":
        draw = "capsule"
        ry *= _num(state, "capsule.squat", 0.55, 0.68)
        perturb = (0.0,) * 8
        pair_dy = 0.0
    elif kind == "nub":
        draw = "round"
        count = _int(state, "nub.n", 1, 2)
        extras = tuple(
            _extras_circle(
                math.cos(_num(state, f"nub.a{i}", 0.0, 2.0 * math.pi)) * 0.88,
                math.sin(_num(state, f"nub.a{i}", 0.0, 2.0 * math.pi)) * 0.88,
                _num(state, f"nub.r{i}", 0.24, 0.40),
            )
            for i in range(count)
        )
    elif kind == "cloud":
        n = _int(state, "body.pts", 6, 8)
        perturb = tuple(_jitter(state, f"body.r{i}", 0.10) for i in range(n))
        count = _int(state, "cloud.n", 4, 6)
        extras = tuple(
            _extras_circle(
                math.cos(math.pi + (math.pi * (i + 0.5)) / count) * 0.80,
                math.sin(math.pi + (math.pi * (i + 0.5)) / count) * 0.50,
                _num(state, f"cloud.r{i}", 0.44, 0.62),
            )
            for i in range(count)
        )
        pair_dy = 0.04
    elif kind == "droplet":
        ry *= 1.12
        rx *= 0.88
        perturb = (0.04, -0.06, 0.02, 0.08, 0.22, 0.08, 0.02, -0.06)
        extras = ((0.0, -0.62, 0.42, 0.36),)
        pair_dy = -0.06
    elif kind == "hexagon":
        perturb = tuple(_jitter(state, f"body.r{i}", 0.04) for i in range(6))
        rot = _num(state, "body.rot", -12.0, 12.0)
        pair_dy = 0.02
    elif kind == "sun":
        draw = "round"
        rx = ry = 0.30 * core / 0.70
        count = _int(state, "sun.n", 6, 9)
        dist = _num(state, "sun.dist", 1.0, 1.08)
        pr = _num(state, "sun.r", 0.20, 0.26)
        off = _num(state, "sun.rot", 0.0, 2.0 * math.pi)
        extras = tuple(
            _extras_circle(
                dist * math.cos(off + 2.0 * math.pi * i / count),
                dist * math.sin(off + 2.0 * math.pi * i / count),
                pr,
            )
            for i in range(count)
        )
        pair_dy = -0.02
    else:  # triangle
        perturb = tuple(_jitter(state, f"body.r{i}", 0.05) for i in range(3))
        rot = _num(state, "body.rot", -5.0, 5.0)
        pair_dx = 0.22
        pair_dy = 0.10

    return BlobatarSpec(
        id=name,
        title=name,
        blurb=f"hashed {kind}",
        hue=hue,
        sat=sat,
        rx=rx,
        ry=ry,
        perturb=perturb,
        extras=extras,
        pair_dx=pair_dx,
        pair_dy=pair_dy,
        shape=draw,
        rot=rot,
    )


def resolve_blobatar(name: str | None) -> BlobatarSpec | None:
    if not name:
        return None
    key = _normalize_seed(name)
    if not key:
        return None
    alias = _PRESET_ALIASES.get(key)
    if alias is not None:
        return BLOBATARS[alias]
    if not _valid_seed(key):
        return None
    return _hashed_blobatar(key)


def _read_preset_file() -> str | None:
    try:
        raw = PRESET_PATH.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return None
    return raw or None


def current_blobatar(data: dict[str, Any] | None = None) -> BlobatarSpec:
    """Preset from status / runtime file / env, falling back to pebble."""
    candidates: list[str] = []
    snap = data if data is not None else None
    if snap is None:
        try:
            snap = read_status()
        except Exception:
            snap = None
    if snap:
        raw = snap.get("face_preset")
        if isinstance(raw, str) and raw.strip():
            candidates.append(raw)
    file_id = _read_preset_file()
    if file_id:
        candidates.append(file_id)
    env_id = (os.environ.get("FACE_OVERLAY_PRESET") or "").strip()
    if env_id:
        candidates.append(env_id)
    for name in candidates:
        spec = resolve_blobatar(name)
        if spec is not None:
            return spec
    return BLOBATARS["pebble"]


def set_blobatar(name: str) -> BlobatarSpec:
    spec = resolve_blobatar(name)
    if spec is None:
        raise ValueError(f"invalid blobatar name {name!r}")
    PRESET_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRESET_PATH.write_text(spec.id + "\n", encoding="utf-8")
    try:
        from app_status import set_face_preset

        set_face_preset(spec.id)
    except Exception:
        pass
    return spec


def format_blobatar_list() -> str:
    current = current_blobatar()
    lines = ["Blobatars (switch with: cua face NAME)", ""]
    for spec in BLOBATARS.values():
        mark = "*" if spec.id == current.id else " "
        lines.append(f"  {mark} {spec.id:<8}  {spec.blurb}")
    lines.append("")
    lines.append("any other name hashes to a unique blobatar (same seed → same face)")
    if current.id not in BLOBATARS:
        lines.append(f"  * {current.id:<8}  {current.blurb}")
    lines.append("")
    lines.append(f"current: {current.id}")
    return "\n".join(lines)


def cmd_face(parts: list[str] | None = None) -> int:
    args = [str(p).strip() for p in (parts or []) if str(p).strip()]
    if args and args[0] == "set":
        args = args[1:]
    if not args or args[0] in _RESERVED_FACE_ARGS:
        print(format_blobatar_list())
        return 0
    try:
        spec = set_blobatar(" ".join(args))
    except ValueError as e:
        print(e)
        print()
        print(format_blobatar_list())
        return 2
    print(f"blobatar: {spec.id} — {spec.blurb}")
    print("the overlay updates on the next tray poll if cua is running")
    return 0


_SLEEP_STATES = frozenset({"idle", "ready", "waiting", "done", "error"})
_LISTEN_STATES = frozenset({"listening"})
_ASK_STATES = frozenset({"ask"})
_SPEAK_STATES = frozenset({"speaking"})
_THINK_STATES = frozenset({"thinking", "agent", "running"})


def face_overlay_env_enabled() -> bool:
    return os.environ.get("FACE_OVERLAY", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def face_overlay_enabled(data: dict[str, Any] | None = None) -> bool:
    """True unless tray toggle / env turned the face off (default on)."""
    if not face_overlay_env_enabled():
        return False
    snap = data if data is not None else read_status()
    val = snap.get("face_overlay_enabled")
    if val is None:
        return True
    return bool(val)


def face_mood_for_state(
    state: str | None,
    data: dict[str, Any] | None = None,
) -> str:
    """Map session phase → face mood.

    Prefer live TTS playback over session phase — async speak_later / streaming
    TTS often leaves the session on waiting while audio is still playing.
    Mic capture (``stt_active``, including Fn dictation) maps to listen.
    ``ask`` / ``ask_user`` stays unsure for the whole question, including TTS.
    """
    snap = data if data is not None else None
    key = (state or "idle").strip().lower()
    if key in _ASK_STATES or key.startswith("ask"):
        return "unsure"
    if snap is not None and snap.get("tts_playing"):
        return "speak"
    if snap is not None and snap.get("stt_active"):
        return "listen"
    if key in _SPEAK_STATES or key.startswith("speaking"):
        return "speak"
    if key in _LISTEN_STATES or key.startswith("listen"):
        return "listen"
    if key in _THINK_STATES or key.startswith("think") or key.startswith("agent"):
        return "think"
    if key in _SLEEP_STATES or key.startswith("wait") or key.startswith("idle"):
        return "sleep"
    return "sleep"


def face_should_show(data: dict[str, Any] | None = None) -> bool:
    """Visible while the face toggle is on and not mid-screenshot hide.

    Does not require orchestrator_pid — the tray owns the panel, and requiring
    a live owner raced with startup (face flashed then stayed hidden).
    """
    snap = data if data is not None else read_status()
    if not face_overlay_enabled(snap):
        return False
    if snap.get("overlay_hidden"):
        return False
    return True


def face_frame_top_center(
    monitor: dict[str, Any],
    *,
    width: int = FACE_WIDTH,
    height: int = FACE_HEIGHT,
    margin_top: int = FACE_MARGIN_TOP,
) -> dict[str, int]:
    """Top-center of ``monitor`` in top-left desktop coordinates."""
    w = min(width, max(64, int(monitor["width"]) - 40))
    h = min(height, max(56, int(monitor["height"]) - 40))
    x = int(monitor["x"]) + (int(monitor["width"]) - w) // 2
    y = int(monitor["y"]) + margin_top
    return {"x": x, "y": y, "width": w, "height": h}


def hsl_to_rgb(h: float, s: float, l: float) -> tuple[float, float, float]:
    """H in degrees, S/L in 0–1 → RGB in 0–1."""
    h = (float(h) % 360.0) / 360.0
    s = max(0.0, min(1.0, float(s)))
    l = max(0.0, min(1.0, float(l)))
    if s <= 0.0:
        return l, l, l

    def _hue(p: float, q: float, t: float) -> float:
        if t < 0.0:
            t += 1.0
        if t > 1.0:
            t -= 1.0
        if t < 1.0 / 6.0:
            return p + (q - p) * 6.0 * t
        if t < 0.5:
            return q
        if t < 2.0 / 3.0:
            return p + (q - p) * (2.0 / 3.0 - t) * 6.0
        return p

    q = l * (1.0 + s) if l < 0.5 else l + s - l * s
    p = 2.0 * l - q
    r = _hue(p, q, h + 1.0 / 3.0)
    g = _hue(p, q, h)
    b = _hue(p, q, h - 1.0 / 3.0)
    return r, g, b


def blob_outline_points(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    *,
    n: int = 8,
    perturb: tuple[float, ...] = _BLOB_PERTURB,
) -> list[tuple[float, float]]:
    """Closed pebble silhouette (polar radii, start at top)."""
    pts: list[tuple[float, float]] = []
    for i in range(max(3, n)):
        ang = -math.pi / 2.0 + 2.0 * math.pi * i / n
        p = perturb[i % len(perturb)]
        pts.append((cx + rx * (1.0 + p) * math.cos(ang), cy + ry * (1.0 + p * 0.85) * math.sin(ang)))
    return pts


def mood_eye_pose(mood: str, t: float) -> dict[str, float]:
    """Capsule-eye pose for a blobatar-style expression. No mouth."""
    body_dy = 1.7 * math.sin(t * 1.45)
    body_scale = 1.0 + 0.03 * math.sin(t * 2.15)
    eye_w = 0.12
    eye_h = 0.20
    pair_dx = 0.30
    pair_dy = -0.05
    left_dy = 0.0
    right_dy = 0.0
    left_tilt = 0.0
    right_tilt = 0.0
    glance = 0.0
    blink = 0.0
    hue_shift = 0.0
    light = 0.58

    left_eye_w = eye_w
    left_eye_h = eye_h
    right_eye_w = eye_w
    right_eye_h = eye_h

    if mood == "sleep":
        body_dy = 5.0 + 1.1 * math.sin(t * 0.85)
        body_scale = 0.97 + 0.018 * math.sin(t * 1.05)
        eye_w = 0.15
        eye_h = 0.048
        pair_dy = 0.07
        light = 0.50
    elif mood == "listen":
        period = 3.4
        phase = t % period
        if phase < 0.08:
            blink = phase / 0.08
        elif phase < 0.16:
            blink = 1.0 - (phase - 0.08) / 0.08
        eye_h = 0.22
        pair_dy = -0.07
        glance = 2.4 * math.sin(t * 0.42)
    elif mood == "unsure":
        # blobatar unsure: one eye squeezed, the pair barely moved.
        body_dy = 0.6 * math.sin(t * 1.05)
        body_scale = 1.0 + 0.012 * math.sin(t * 1.35)
        pair_dx = 0.31
        pair_dy = -0.02
        left_tilt = 4.0
        right_tilt = -22.0
        left_dy = -0.02
        right_dy = 0.01
        left_eye_w = 0.114
        left_eye_h = 0.204
        right_eye_w = 0.143
        right_eye_h = 0.116
        eye_w = left_eye_w
        eye_h = left_eye_h
        light = 0.56
    elif mood == "speak":
        pulse = 0.05 * abs(math.sin(t * 9.5))
        eye_w = 0.09
        eye_h = 0.27 + pulse
        pair_dy = -0.11
        left_tilt = 14.0
        right_tilt = 14.0
        body_dy = -2.2 + 1.5 * math.sin(t * 6.2)
        body_scale = 1.02 + 0.025 * abs(math.sin(t * 6.2))
        hue_shift = 8.0
        light = 0.62
    elif mood == "think":
        swing = math.sin(t * (2.0 * math.pi / 0.9))
        left_dy = -0.11 * swing
        right_dy = 0.11 * swing
        eye_w = 0.10
        eye_h = 0.16
        pair_dy = -0.08
        glance = 1.4
        hue_shift = -12.0

    if mood != "unsure":
        left_eye_w = right_eye_w = eye_w
        left_eye_h = right_eye_h = eye_h

    lid = 1.0 - 0.90 * blink
    eye_h *= lid
    left_eye_h *= lid
    right_eye_h *= lid
    return {
        "body_dy": body_dy,
        "body_scale": body_scale,
        "eye_w": eye_w,
        "eye_h": max(0.03, eye_h),
        "left_eye_w": left_eye_w,
        "left_eye_h": max(0.03, left_eye_h),
        "right_eye_w": right_eye_w,
        "right_eye_h": max(0.03, right_eye_h),
        "pair_dx": pair_dx,
        "pair_dy": pair_dy,
        "left_dy": left_dy,
        "right_dy": right_dy,
        "left_tilt": left_tilt,
        "right_tilt": right_tilt,
        "glance": glance,
        "hue_shift": hue_shift,
        "light": light,
    }


class FaceOverlay:
    """Animated face NSPanel. Construct only on the AppKit main thread."""

    def __init__(self) -> None:
        self.panel = None
        self.view = None
        self._timer = None
        self._timer_target = None
        self._mood = "sleep"
        self._t0 = time.monotonic()
        self._NSBezierPath = None
        self._NSColor = None
        self._NSMakeRect = None
        self._NSAffineTransform = None
        self._preset_id = current_blobatar().id
        self._build()

    def _build(self) -> None:
        import objc
        from AppKit import (  # type: ignore
            NSAffineTransform,
            NSBackingStoreBuffered,
            NSBezierPath,
            NSColor,
            NSMakeRect,
            NSObject,
            NSPanel,
            NSStatusWindowLevel,
            NSView,
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorFullScreenAuxiliary,
            NSWindowCollectionBehaviorIgnoresCycle,
            NSWindowSharingNone,
            NSWindowStyleMaskBorderless,
            NSWindowStyleMaskNonactivatingPanel,
        )
        from Foundation import NSTimer  # type: ignore

        owner = self

        class FaceView(NSView):
            def initWithFrame_(self, frame):  # noqa: N802
                self = objc.super(FaceView, self).initWithFrame_(frame)
                if self is None:
                    return None
                return self

            def isFlipped(self) -> bool:  # noqa: N802
                return True

            def drawRect_(self, _rect) -> None:  # noqa: N802
                try:
                    owner._draw(self)
                except Exception:
                    pass

        class _AnimTarget(NSObject):
            def tickAnim_(self, _timer) -> None:  # noqa: N802
                view = owner.view
                if view is None:
                    return
                try:
                    view.setNeedsDisplay_(True)
                except Exception:
                    pass

        frame = self._cocoa_frame()
        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            style,
            NSBackingStoreBuffered,
            False,
        )
        panel.setLevel_(NSStatusWindowLevel + 1)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setIgnoresMouseEvents_(True)
        panel.setAcceptsMouseMovedEvents_(False)
        panel.setHidesOnDeactivate_(False)
        panel.setFloatingPanel_(True)
        panel.setBecomesKeyOnlyIfNeeded_(True)
        panel.setHasShadow_(False)
        panel.setReleasedWhenClosed_(False)
        panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorIgnoresCycle
        )
        try:
            panel.setSharingType_(NSWindowSharingNone)
        except Exception:
            pass

        view = FaceView.alloc().initWithFrame_(panel.contentView().bounds())
        view.setAutoresizingMask_(18)  # width + height flexible
        panel.setContentView_(view)

        target = _AnimTarget.alloc().init()
        interval = max(0.04, 1.0 / max(8.0, FACE_FPS))
        timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            interval,
            target,
            "tickAnim:",
            None,
            True,
        )

        # Do not orderFront here — apply_status decides visibility (avoids flash-then-hide).
        self.panel = panel
        self.view = view
        self._timer = timer
        self._timer_target = target
        self._NSBezierPath = NSBezierPath
        self._NSColor = NSColor
        self._NSMakeRect = NSMakeRect
        self._NSAffineTransform = NSAffineTransform
        self.apply_status(read_status())

    def _cocoa_frame(self):
        from AppKit import NSMakeRect, NSScreen  # type: ignore

        screens = list(NSScreen.screens() or [])
        if not screens:
            return NSMakeRect(100, 700, float(FACE_WIDTH), float(FACE_HEIGHT))
        main = NSScreen.mainScreen() or screens[0]
        vis = main.visibleFrame()
        width = min(float(FACE_WIDTH), max(64.0, vis.size.width - 40.0))
        height = min(float(FACE_HEIGHT), max(56.0, vis.size.height - 40.0))
        x = vis.origin.x + (vis.size.width - width) / 2.0
        y = vis.origin.y + vis.size.height - height - float(FACE_MARGIN_TOP)
        return NSMakeRect(x, y, width, height)

    def _body_path(self, cx: float, cy: float, rx: float, ry: float, spec: BlobatarSpec):
        NSBezierPath = self._NSBezierPath
        NSMakeRect = self._NSMakeRect
        kind = spec.shape
        if kind == "round":
            path = NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(cx - rx, cy - ry, rx * 2.0, ry * 2.0)
            )
        elif kind in {"boxy", "capsule"}:
            rad = min(rx, ry) * (0.95 if kind == "capsule" else 0.28)
            path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(cx - rx, cy - ry, rx * 2.0, ry * 2.0),
                rad,
                rad,
            )
        else:
            path = self._closed_spline(
                blob_outline_points(
                    cx,
                    cy,
                    rx,
                    ry,
                    n=max(3, len(spec.perturb)),
                    perturb=spec.perturb,
                )
            )
        if abs(spec.rot) > 0.2:
            xf = self._NSAffineTransform.transform()
            xf.translateXBy_yBy_(cx, cy)
            xf.rotateByDegrees_(spec.rot)
            xf.translateXBy_yBy_(-cx, -cy)
            path.transformUsingAffineTransform_(xf)
        return path

    def _closed_spline(self, points: list[tuple[float, float]]):
        NSBezierPath = self._NSBezierPath
        n = len(points)
        path = NSBezierPath.bezierPath()
        path.moveToPoint_(points[0])
        for i in range(n):
            p0 = points[(i - 1) % n]
            p1 = points[i]
            p2 = points[(i + 1) % n]
            p3 = points[(i + 2) % n]
            c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
            c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
            path.curveToPoint_controlPoint1_controlPoint2_(p2, c1, c2)
        path.closePath()
        return path

    def _fill_capsule(
        self,
        cx: float,
        cy: float,
        hw: float,
        hh: float,
        tilt_deg: float,
        color,
    ) -> None:
        NSBezierPath = self._NSBezierPath
        NSMakeRect = self._NSMakeRect
        if hw <= 0.4 or hh <= 0.4:
            return
        rect = NSMakeRect(cx - hw, cy - hh, hw * 2.0, hh * 2.0)
        rad = min(hw, hh)
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, rad, rad)
        if abs(tilt_deg) > 0.2:
            xf = self._NSAffineTransform.transform()
            xf.translateXBy_yBy_(cx, cy)
            xf.rotateByDegrees_(tilt_deg)
            xf.translateXBy_yBy_(-cx, -cy)
            path.transformUsingAffineTransform_(xf)
        color.setFill()
        path.fill()

    def _draw(self, view) -> None:
        NSBezierPath = self._NSBezierPath
        NSColor = self._NSColor
        NSMakeRect = self._NSMakeRect
        if NSBezierPath is None or NSColor is None or NSMakeRect is None:
            return

        bounds = view.bounds()
        w = float(bounds.size.width)
        h = float(bounds.size.height)
        t = time.monotonic() - self._t0
        spec = resolve_blobatar(self._preset_id) or current_blobatar()
        pose = mood_eye_pose(self._mood, t)

        cx = w / 2.0
        cy = h / 2.0 + pose["body_dy"]
        span = min(w, h)
        rx = span * spec.rx * pose["body_scale"]
        ry = span * spec.ry * pose["body_scale"]

        hue = spec.hue + pose["hue_shift"]
        env_hue = (os.environ.get("FACE_OVERLAY_HUE") or "").strip()
        if env_hue:
            try:
                hue = float(env_hue) + pose["hue_shift"]
            except ValueError:
                pass
        br, bg, bb = hsl_to_rgb(hue, spec.sat, pose["light"])
        lum = 0.2126 * br + 0.7152 * bg + 0.0722 * bb
        if lum > 0.45:
            er, eg, eb = 0.12, 0.13, 0.16
        else:
            er, eg, eb = 0.96, 0.97, 0.98

        # Soft ground shadow (keeps the pebble readable on light desktops).
        shadow = NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(cx - rx * 0.72, cy + ry * 0.55, rx * 1.44, ry * 0.38)
        )
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.08, 0.10, 0.14, 0.22).setFill()
        shadow.fill()

        fill = NSColor.colorWithCalibratedRed_green_blue_alpha_(br, bg, bb, 1.0)
        body = self._body_path(cx, cy, rx, ry, spec)
        fill.setFill()
        body.fill()

        rot = spec.rot
        for dx, dy, ew, eh in spec.extras:
            ex = cx + dx * rx
            ey = cy + dy * ry
            if abs(rot) > 0.2:
                ang = math.radians(rot)
                ox, oy = ex - cx, ey - cy
                ex = cx + ox * math.cos(ang) - oy * math.sin(ang)
                ey = cy + ox * math.sin(ang) + oy * math.cos(ang)
            extra = NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(ex - (ew * rx) / 2.0, ey - (eh * ry) / 2.0, ew * rx, eh * ry)
            )
            fill.setFill()
            extra.fill()

        shine = NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(cx - rx * 0.42, cy - ry * 0.62, rx * 0.38, ry * 0.28)
        )
        NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 1.0, 1.0, 0.22).setFill()
        shine.fill()

        eye_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(er, eg, eb, 1.0)
        base_y = cy + ry * (pose["pair_dy"] + spec.pair_dy)
        glance = pose["glance"]
        pair_dx = pose["pair_dx"] + spec.pair_dx - 0.30
        for side, tilt, extra_dy, ew, eh in (
            (-1.0, pose["left_tilt"], pose["left_dy"], pose["left_eye_w"], pose["left_eye_h"]),
            (1.0, pose["right_tilt"], pose["right_dy"], pose["right_eye_w"], pose["right_eye_h"]),
        ):
            ex = cx + side * rx * pair_dx + glance
            ey = base_y + extra_dy * ry
            self._fill_capsule(ex, ey, rx * ew, ry * eh, tilt, eye_color)

    def hide(self) -> None:
        if self.panel is not None:
            self.panel.orderOut_(None)

    def show(self) -> None:
        if self.panel is None:
            return
        try:
            self.panel.setFrame_display_(self._cocoa_frame(), False)
        except Exception:
            pass
        try:
            self.panel.orderFrontRegardless()
        except Exception:
            pass

    def destroy(self) -> None:
        timer = self._timer
        self._timer = None
        self._timer_target = None
        if timer is not None:
            try:
                timer.invalidate()
            except Exception:
                pass
        panel = self.panel
        self.panel = None
        self.view = None
        if panel is None:
            return
        try:
            panel.orderOut_(None)
        except Exception:
            pass
        try:
            panel.setReleasedWhenClosed_(True)
            panel.close()
        except Exception:
            pass

    def apply_status(self, data: dict[str, Any]) -> None:
        if self.panel is None:
            return
        mood = face_mood_for_state(str(data.get("state") or "idle"), data)
        preset = current_blobatar(data).id
        if mood != self._mood:
            self._mood = mood
            if mood == "listen":
                self._t0 = time.monotonic()
        self._preset_id = preset
        if not face_should_show(data):
            self.hide()
            return
        self.show()
        if self.view is not None:
            try:
                self.view.setNeedsDisplay_(True)
            except Exception:
                pass
