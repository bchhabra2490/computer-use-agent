"""
Shared live status + recent log lines for the macOS menu-bar tray.

Orchestrator / agent write here; `status_tray.py` polls and shows hover tooltip
+ click menu. State lives in a JSON file so separate processes can share it.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

RUNTIME_DIR = Path(
    os.environ.get(
        "AGENT_RUNTIME_DIR",
        str(Path(__file__).resolve().parent / ".runtime"),
    )
)
STATUS_PATH = RUNTIME_DIR / "status.json"
PHONE_SCREEN_PATH = RUNTIME_DIR / "phone-screen.jpg"
PHONE_SCREEN_MAX_WIDTH = int(os.environ.get("PHONE_SCREEN_MAX_WIDTH", "1080"))
PHONE_SCREEN_QUALITY = int(os.environ.get("PHONE_SCREEN_QUALITY", "60"))
PHONE_PHOTO_PATH = RUNTIME_DIR / "phone-photo.jpg"
PHONE_PHOTO_TTL_SEC = float(os.environ.get("PHONE_PHOTO_TTL_SEC", str(30 * 60)))
PHONE_SPEECH_PATH = RUNTIME_DIR / "phone-tts.wav"
CHAT_SCREENSHOTS_DIR = RUNTIME_DIR / "chat-shots"
MAX_LOG_LINES = int(os.environ.get("STATUS_LOG_LINES", "40"))

_lock = threading.Lock()


def _default_state() -> dict[str, Any]:
    return {
        "state": "idle",
        "detail": "",
        "updated_at": 0.0,
        "logs": [],
        "log_dir": None,
        "task": None,
        "orchestrator_pid": None,
        "agent_pid": None,
        "tray_pid": None,
        "quit_requested": False,
        "done_requested": False,
        "done_agent_id": None,
        "send_requested": False,
        "listen_requested": False,
        "cancel_requested": False,
        "stt_active": False,
        "agents": [],  # active subagents / computer-agent jobs
        "overlay_hidden": False,
        "overlay_ack_hidden": False,
        "overlay_enabled": True,
        "face_overlay_enabled": True,
        "chat_overlay_enabled": False,
        "sleep_mode": False,
        "face_preset": "pebble",
        "tts_playing": False,
        "tts_play_depth": 0,
        "phone_gateway_pid": None,
        "chat_bridge_pid": None,
        "chat_app_pid": None,
        "pending_utterances": [],
        "pending_speaks": [],
        "chat_inbox": [],
        "last_spoken": None,
        "last_llm": None,
        "reply_sink": "mac",
        "reply_tts": True,
        "speech_at": None,
        "speech_bytes": None,
        "screen_at": None,
        "screen_width": None,
        "screen_height": None,
        "phone_photo_at": None,
        "phone_photo_pending": False,
        "phone_photo_width": None,
        "phone_photo_height": None,
        "turn_chat_screenshot": None,
        "turn_source": None,
        "chat_stream": None,
    }


def _ensure_dir() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def _read() -> dict[str, Any]:
    if not STATUS_PATH.exists():
        return _default_state()
    try:
        data = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _default_state()
        base = _default_state()
        base.update(data)
        if not isinstance(base.get("logs"), list):
            base["logs"] = []
        if not isinstance(base.get("agents"), list):
            base["agents"] = []
        if not isinstance(base.get("pending_utterances"), list):
            base["pending_utterances"] = []
        if not isinstance(base.get("pending_speaks"), list):
            base["pending_speaks"] = []
        if not isinstance(base.get("chat_inbox"), list):
            base["chat_inbox"] = []
        return base
    except Exception:
        return _default_state()


def _write(data: dict[str, Any]) -> None:
    _ensure_dir()
    data["updated_at"] = time.time()
    payload = json.dumps(data, indent=2) + "\n"
    # Per-write temp path — a shared ``status.tmp`` races when tray, bridge, and
    # orchestrator replace in parallel (one writer's tmp is already moved).
    tmp = RUNTIME_DIR / f"status.{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.tmp"
    try:
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, STATUS_PATH)
    except FileNotFoundError:
        _ensure_dir()
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, STATUS_PATH)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def read_status() -> dict[str, Any]:
    """Snapshot for the tray (or callers)."""
    with _lock:
        return _read()


def set_state(state: str, detail: str = "", *, task: str | None = None, log_dir: str | None = None) -> None:
    """Update high-level status shown in the menu bar."""
    state = (state or "idle").strip() or "idle"
    detail = (detail or "").strip()
    with _lock:
        data = _read()
        data["state"] = state
        data["detail"] = detail
        if task is not None:
            data["task"] = task
        if log_dir is not None:
            data["log_dir"] = log_dir
        _write(data)


def log(message: str, *, also_print: bool = False) -> None:
    """Append a line to the ring buffer shown on hover / in the menu."""
    message = (message or "").strip()
    if not message:
        return
    if also_print:
        print(message, flush=True)
    stamp = time.strftime("%H:%M:%S")
    line = f"{stamp} {message}"
    with _lock:
        data = _read()
        logs = list(data.get("logs") or [])
        logs.append(line)
        if len(logs) > MAX_LOG_LINES:
            logs = logs[-MAX_LOG_LINES:]
        data["logs"] = logs
        _write(data)


LLM_LOG_CHARS = 2000
LLM_STORE_CHARS = 4000


def log_llm(text: str, *, source: str = "llm") -> None:
    """Put an LLM reply in the status log (and ``last_llm``) for the phone / tray."""
    text = (text or "").strip()
    if not text:
        return
    source = (source or "llm").strip() or "llm"
    one_line = " ".join(text.split())
    stamp = time.strftime("%H:%M:%S")
    line = f"{stamp} [{source}] {one_line[:LLM_LOG_CHARS]}"
    with _lock:
        data = _read()
        logs = list(data.get("logs") or [])
        logs.append(line)
        if len(logs) > MAX_LOG_LINES:
            logs = logs[-MAX_LOG_LINES:]
        data["logs"] = logs
        data["last_llm"] = text[:LLM_STORE_CHARS]
        _write(data)


def set_and_log(state: str, message: str, *, detail: str | None = None, **kwargs: Any) -> None:
    """Set state and append the same message to the log ring."""
    detail = message if detail is None else detail
    set_state(state, detail, **kwargs)
    log(message)


def clear_logs() -> None:
    with _lock:
        data = _read()
        data["logs"] = []
        _write(data)


def set_overlay_hidden(hidden: bool) -> None:
    """Ask the tray overlay to hide (True) or show (False) for a screenshot."""
    with _lock:
        data = _read()
        data["overlay_hidden"] = bool(hidden)
        data["overlay_ack_hidden"] = False
        _write(data)


def set_overlay_enabled(enabled: bool) -> None:
    """Show or hide the on-screen log panel (tray menu toggle)."""
    with _lock:
        data = _read()
        data["overlay_enabled"] = bool(enabled)
        _write(data)


def set_face_overlay_enabled(enabled: bool) -> None:
    """Show or hide the top-center face panel (tray menu toggle)."""
    with _lock:
        data = _read()
        data["face_overlay_enabled"] = bool(enabled)
        _write(data)


def set_chat_overlay_enabled(enabled: bool) -> None:
    """Show or hide the desktop chat window (tray menu / cua chat)."""
    with _lock:
        data = _read()
        data["chat_overlay_enabled"] = bool(enabled)
        _write(data)


def sleep_mode_enabled(data: dict[str, Any] | None = None) -> bool:
    """When True, wake word is ignored (Sleep)."""
    snap = data if data is not None else read_status()
    return bool(snap.get("sleep_mode"))


def set_sleep_mode(enabled: bool) -> bool:
    """Enable/disable Sleep (ignore wake). Returns the new value."""
    on = bool(enabled)
    with _lock:
        data = _read()
        data["sleep_mode"] = on
        _write(data)
    try:
        from wake import on_sleep_mode_changed

        on_sleep_mode_changed(on)
    except Exception:
        pass
    return on


def toggle_sleep_mode() -> bool:
    """Flip Sleep mode; returns True when Sleep is now on."""
    now = not sleep_mode_enabled()
    set_sleep_mode(now)
    return now


def cmd_sleep(mode: str | None) -> int:
    """``cua sleep`` / ``on`` / ``off`` / ``toggle``."""
    key = (mode or "status").strip().lower()
    if key in {"on", "sleep", "1", "true"}:
        set_sleep_mode(True)
        print("sleep on — wake word ignored (⌘⌃S to wake)")
        return 0
    if key in {"off", "wake", "0", "false"}:
        set_sleep_mode(False)
        print("sleep off — listening for wake word")
        return 0
    if key in {"toggle", ""}:
        on = toggle_sleep_mode()
        print("sleep on — wake word ignored" if on else "sleep off — listening for wake word")
        return 0
    if key == "status":
        print("on" if sleep_mode_enabled() else "off")
        return 0
    print("usage: cua sleep [on|off|toggle|status]")
    return 2


def set_face_preset(name: str) -> None:
    """Which blobatar the overlay draws (tray picks this up on the next poll)."""
    with _lock:
        data = _read()
        data["face_preset"] = str(name).strip().lower()
        _write(data)


def begin_tts_playback() -> None:
    """Mark that Jarvis audio is synthesizing or playing (nested-safe)."""
    with _lock:
        data = _read()
        depth = max(0, int(data.get("tts_play_depth") or 0)) + 1
        data["tts_play_depth"] = depth
        data["tts_playing"] = True
        _write(data)


def end_tts_playback() -> None:
    """Clear TTS activity when a synth/play scope exits."""
    with _lock:
        data = _read()
        depth = max(0, int(data.get("tts_play_depth") or 0) - 1)
        data["tts_play_depth"] = depth
        data["tts_playing"] = depth > 0
        _write(data)


def tts_playing(data: dict[str, Any] | None = None) -> bool:
    snap = data if data is not None else read_status()
    return bool(snap.get("tts_playing"))


def ack_overlay_hidden(hidden: bool) -> None:
    """Tray confirms the panel is actually off-screen (or back)."""
    with _lock:
        data = _read()
        data["overlay_ack_hidden"] = bool(hidden)
        _write(data)


def set_tray_pid(pid: int | None) -> None:
    with _lock:
        data = _read()
        data["tray_pid"] = pid
        _write(data)


def set_phone_gateway_pid(pid: int | None) -> None:
    with _lock:
        data = _read()
        data["phone_gateway_pid"] = pid
        _write(data)


def set_chat_bridge_pid(pid: int | None) -> None:
    with _lock:
        data = _read()
        data["chat_bridge_pid"] = pid
        _write(data)


def set_chat_app_pid(pid: int | None) -> None:
    with _lock:
        data = _read()
        data["chat_app_pid"] = pid
        _write(data)


def enqueue_utterance(
    text: str,
    *,
    source: str = "phone",
    photo: bool = False,
    sink: str | None = None,
    tts: bool | None = None,
    screenshot_file: str | None = None,
    chat_id: str | None = None,
) -> None:
    """Queue a text command (chat, phone, or API). Orchestrator consumes it like STT.

    ``tts``: when False, the orchestrator still answers in chat but skips speaking.
    ``None`` means speak (default).

    ``screenshot_file``: basename under ``CHAT_SCREENSHOTS_DIR`` for a chat-attached
    PNG. When set, the orchestrator should use that image and skip live desktop/AX.
    """
    text = (text or "").strip()
    if not text:
        return
    source = (source or "phone").strip() or "phone"
    item: dict[str, Any] = {
        "text": text,
        "source": source,
        "ts": time.time(),
        "photo": bool(photo),
        "tts": True if tts is None else bool(tts),
    }
    if sink is not None:
        item["sink"] = _normalize_sink(sink)
    shot = (screenshot_file or "").strip()
    if shot:
        item["screenshot_file"] = Path(shot).name
    cid = (chat_id or "").strip()
    if cid:
        item["chat_id"] = cid
    with _lock:
        data = _read()
        pending = list(data.get("pending_utterances") or [])
        pending.append(item)
        data["pending_utterances"] = pending[-20:]
        _write(data)
    kind = "photo" if photo else ("chat-shot" if shot else "queued")
    log(f"[{source}] {kind}: {text[:160]}")


def save_chat_screenshot_png(png: bytes) -> str:
    """Write a chat-attached PNG for the orchestrator; return basename for enqueue."""
    if not png:
        raise ValueError("empty screenshot")
    CHAT_SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"shot-{time.time_ns()}.png"
    path = CHAT_SCREENSHOTS_DIR / name
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(png)
    tmp.replace(path)
    # Keep the directory from growing forever.
    try:
        shots = sorted(CHAT_SCREENSHOTS_DIR.glob("shot-*.png"), key=lambda p: p.stat().st_mtime)
        for old in shots[:-30]:
            old.unlink(missing_ok=True)
    except OSError:
        pass
    return name


def take_turn_chat_screenshot() -> bytes | None:
    """Read and clear the chat PNG attached to the utterance just consumed."""
    with _lock:
        data = _read()
        name = str(data.get("turn_chat_screenshot") or "").strip()
        data["turn_chat_screenshot"] = None
        _write(data)
    if not name:
        return None
    path = CHAT_SCREENSHOTS_DIR / Path(name).name
    try:
        png = path.read_bytes()
    except OSError:
        return None
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    return png or None


def utterance_pending() -> bool:
    with _lock:
        pending = _read().get("pending_utterances") or []
        return bool(pending)


def _normalize_sink(sink: str | None) -> str:
    return "phone" if (sink or "").strip().lower() == "phone" else "mac"


def parse_reply_sink_param(value: Any) -> str | None:
    """Parse optional API ``sink`` / ``speaker``.

    ``None`` / empty means this request does not select a speaker; consuming the
    utterance switches ``reply_sink`` back to Mac.
    """
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    return _normalize_sink(s)


def set_reply_sink(sink: str) -> None:
    """Where the next TTS line should play: Mac speakers or the phone."""
    value = _normalize_sink(sink)
    with _lock:
        data = _read()
        data["reply_sink"] = value
        _write(data)


def reply_sink() -> str:
    with _lock:
        return _normalize_sink(_read().get("reply_sink"))


def set_reply_tts(enabled: bool) -> None:
    """Whether the current turn should speak replies (vs chat text only)."""
    with _lock:
        data = _read()
        data["reply_tts"] = bool(enabled)
        _write(data)


def reply_tts_enabled() -> bool:
    with _lock:
        return bool(_read().get("reply_tts", True))


def consume_utterance() -> str | None:
    """Pop the next queued text command, or None."""
    with _lock:
        data = _read()
        pending = list(data.get("pending_utterances") or [])
        if not pending:
            return None
        item = pending.pop(0)
        data["pending_utterances"] = pending
        data["turn_chat_screenshot"] = None
        if isinstance(item, dict):
            # Per-turn speaker: phone only when this item requested it.
            if item.get("sink") is not None:
                data["reply_sink"] = _normalize_sink(str(item.get("sink")))
            else:
                data["reply_sink"] = "mac"
            data["reply_tts"] = bool(item.get("tts", True))
            data["turn_source"] = str(item.get("source") or "phone").strip() or "phone"
            data["turn_chat_id"] = str(item.get("chat_id") or "").strip() or None
            shot = str(item.get("screenshot_file") or "").strip()
            if shot:
                data["turn_chat_screenshot"] = Path(shot).name
        else:
            data["reply_tts"] = True
            data["turn_source"] = "stt"
            data["turn_chat_id"] = None
        if str(data.get("turn_source") or "").lower() == "chat":
            data["chat_stream"] = None
        _write(data)
    if isinstance(item, str):
        text = item.strip()
        return text or None
    text = str((item or {}).get("text") or "").strip()
    return text or None


def enqueue_speak(
    text: str,
    *,
    source: str = "timer",
    sink: str | None = None,
) -> None:
    """Queue a line for the orchestrator to speak (timer reminders, not user STT)."""
    text = (text or "").strip()
    if not text:
        return
    source = (source or "timer").strip() or "timer"
    with _lock:
        data = _read()
        pending = list(data.get("pending_speaks") or [])
        pending.append(
            {
                "text": text,
                "source": source,
                "ts": time.time(),
                "sink": _normalize_sink(sink if sink is not None else data.get("reply_sink")),
            }
        )
        data["pending_speaks"] = pending[-20:]
        _write(data)
    log(f"[{source}] speak: {text[:160]}")


def speak_pending() -> bool:
    with _lock:
        pending = _read().get("pending_speaks") or []
        return bool(pending)


def consume_speak() -> str | None:
    """Pop the next queued TTS line, or None."""
    with _lock:
        data = _read()
        pending = list(data.get("pending_speaks") or [])
        if not pending:
            return None
        item = pending.pop(0)
        data["pending_speaks"] = pending
        if isinstance(item, dict):
            data["reply_sink"] = _normalize_sink(item.get("sink"))
        # Timer / queued speaks always play audio.
        data["reply_tts"] = True
        _write(data)
    if isinstance(item, str):
        text = item.strip()
        return text or None
    text = str((item or {}).get("text") or "").strip()
    return text or None


def set_turn_source(source: str) -> None:
    """Tag the current orchestrator turn (chat / voice / phone / …)."""
    value = (source or "").strip() or "voice"
    with _lock:
        data = _read()
        data["turn_source"] = value
        if value.lower() != "chat":
            data["chat_stream"] = None
        _write(data)


def turn_source() -> str:
    with _lock:
        return str(_read().get("turn_source") or "").strip()


def reply_to_chat() -> bool:
    """True when this turn was queued from the Electron chat app."""
    return turn_source().lower() == "chat"


def turn_chat_id() -> str | None:
    """Chat that owns the currently executing queued turn."""
    with _lock:
        value = str(_read().get("turn_chat_id") or "").strip()
    return value or None


def chat_text_only() -> bool:
    """Chat turn with speaker off — reply in the UI, not via TTS or status blurbs."""
    return reply_to_chat() and not reply_tts_enabled()


_chat_stream_last_write = 0.0
_CHAT_STREAM_MIN_INTERVAL = 0.05


def set_chat_stream(text: str | None, *, done: bool = False, force: bool = False) -> None:
    """Publish progressive assistant text for the chat UI (chat-origin turns)."""
    global _chat_stream_last_write
    if text is None:
        with _lock:
            data = _read()
            data["chat_stream"] = None
            _write(data)
        return
    full_text = str(text)
    now = time.monotonic()
    if (
        not force
        and not done
        and now - _chat_stream_last_write < _CHAT_STREAM_MIN_INTERVAL
    ):
        return
    _chat_stream_last_write = now
    chat_id = turn_chat_id()
    with _lock:
        data = _read()
        data["chat_stream"] = {
            "text": full_text,
            "done": bool(done),
            "ts": time.time(),
            "chat_id": chat_id,
        }
        _write(data)


def chat_stream_payload() -> dict[str, Any] | None:
    with _lock:
        raw = _read().get("chat_stream")
    if not isinstance(raw, dict):
        return None
    text = str(raw.get("text") or "")
    if not text and not raw.get("done"):
        return None
    return {
        "text": text,
        "done": bool(raw.get("done")),
        "ts": raw.get("ts"),
        "chat_id": raw.get("chat_id"),
    }


def set_last_spoken(text: str, *, enqueue_chat: bool = True) -> None:
    text = (text or "").strip()
    if not text:
        return
    with _lock:
        data = _read()
        data["last_spoken"] = text
        if enqueue_chat and data.get("chat_overlay_enabled"):
            inbox = list(data.get("chat_inbox") or [])
            prev = inbox[-1].get("text") if inbox and isinstance(inbox[-1], dict) else None
            if prev != text:
                inbox.append(
                    {
                        "text": text,
                        "ts": time.time(),
                        "chat_id": data.get("turn_chat_id"),
                    }
                )
                data["chat_inbox"] = inbox[-50:]
        # Final line replaces the live stream so the UI can settle on history.
        if str(data.get("turn_source") or "").lower() == "chat":
            data["chat_stream"] = {
                "text": text,
                "done": True,
                "ts": time.time(),
                "chat_id": data.get("turn_chat_id"),
            }
        _write(data)


def consume_chat_inbox_items() -> list[dict[str, Any]]:
    """Pop assistant replies while preserving their originating chat IDs."""
    with _lock:
        data = _read()
        items = list(data.get("chat_inbox") or [])
        data["chat_inbox"] = []
        _write(data)
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, str):
            line = item.strip()
            chat_id = None
        else:
            line = str((item or {}).get("text") or "").strip()
            chat_id = str((item or {}).get("chat_id") or "").strip() or None
        if line:
            out.append({"text": line, "chat_id": chat_id})
    return out


def consume_chat_inbox() -> list[str]:
    """Backward-compatible text-only view of queued assistant replies."""
    return [item["text"] for item in consume_chat_inbox_items()]


def write_phone_speech(wav_bytes: bytes) -> None:
    """Publish a Mac-synthesized WAV for the phone to play locally."""
    if not wav_bytes:
        return
    _ensure_dir()
    tmp = PHONE_SPEECH_PATH.with_suffix(".tmp")
    tmp.write_bytes(wav_bytes)
    tmp.replace(PHONE_SPEECH_PATH)
    with _lock:
        data = _read()
        data["speech_at"] = time.time()
        data["speech_bytes"] = len(wav_bytes)
        _write(data)


def read_phone_speech() -> bytes | None:
    try:
        if not PHONE_SPEECH_PATH.is_file():
            return None
        data = PHONE_SPEECH_PATH.read_bytes()
    except OSError:
        return None
    return data or None


def write_phone_photo(jpeg: bytes, *, width: int, height: int) -> None:
    """Store the latest phone-camera JPEG for the orchestrator to attach."""
    if not jpeg:
        raise ValueError("empty photo")
    _ensure_dir()
    tmp = PHONE_PHOTO_PATH.with_suffix(".tmp")
    tmp.write_bytes(jpeg)
    tmp.replace(PHONE_PHOTO_PATH)
    with _lock:
        data = _read()
        data["phone_photo_at"] = time.time()
        data["phone_photo_pending"] = True
        data["phone_photo_width"] = int(width)
        data["phone_photo_height"] = int(height)
        _write(data)


def phone_photo_pending() -> bool:
    with _lock:
        return bool(_read().get("phone_photo_pending"))


def phone_photo_jpeg(*, consume_pending: bool = False, max_age: float | None = None) -> bytes | None:
    """Return the latest phone JPEG if it is still fresh, else None."""
    ttl = PHONE_PHOTO_TTL_SEC if max_age is None else max_age
    with _lock:
        data = _read()
        at = data.get("phone_photo_at")
        if consume_pending and data.get("phone_photo_pending"):
            data["phone_photo_pending"] = False
            _write(data)
    if not at:
        return None
    try:
        age = time.time() - float(at)
    except (TypeError, ValueError):
        return None
    if ttl and ttl > 0 and age > ttl:
        return None
    try:
        blob = PHONE_PHOTO_PATH.read_bytes()
    except OSError:
        return None
    return blob or None


def clear_phone_photo() -> None:
    with _lock:
        data = _read()
        data["phone_photo_at"] = None
        data["phone_photo_pending"] = False
        data["phone_photo_width"] = None
        data["phone_photo_height"] = None
        _write(data)
    try:
        PHONE_PHOTO_PATH.unlink(missing_ok=True)
    except OSError:
        pass


_phone_screen_gen = 0
_phone_screen_lock = threading.Lock()


def set_phone_screen(*, at: float, width: int, height: int) -> None:
    with _lock:
        data = _read()
        data["screen_at"] = float(at)
        data["screen_width"] = int(width)
        data["screen_height"] = int(height)
        _write(data)


def _encode_phone_jpeg(png_bytes: bytes) -> tuple[bytes, int, int]:
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(png_bytes))
    if img.mode not in {"RGB", "L"}:
        img = img.convert("RGB")
    max_w = max(320, PHONE_SCREEN_MAX_WIDTH)
    if img.width > max_w:
        ratio = max_w / img.width
        img = img.resize((max_w, max(1, round(img.height * ratio))))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=max(30, min(PHONE_SCREEN_QUALITY, 90)))
    return buf.getvalue(), img.width, img.height


def write_phone_screen(png_bytes: bytes) -> bool:
    """Synchronously encode the agent's PNG and replace ``phone-screen.jpg``."""
    if not png_bytes:
        return False
    jpeg, width, height = _encode_phone_jpeg(png_bytes)
    _ensure_dir()
    tmp = PHONE_SCREEN_PATH.with_suffix(".tmp")
    tmp.write_bytes(jpeg)
    tmp.replace(PHONE_SCREEN_PATH)
    set_phone_screen(at=time.time(), width=width, height=height)
    return True


def publish_phone_screen(png_bytes: bytes, *, background: bool = True) -> None:
    """Share the latest computer-use screenshot with the phone gateway."""
    if not png_bytes:
        return
    if not background:
        write_phone_screen(png_bytes)
        return
    global _phone_screen_gen
    with _phone_screen_lock:
        _phone_screen_gen += 1
        gen = _phone_screen_gen

    def _run() -> None:
        try:
            jpeg, width, height = _encode_phone_jpeg(png_bytes)
            with _phone_screen_lock:
                if gen != _phone_screen_gen:
                    return
                _ensure_dir()
                tmp = PHONE_SCREEN_PATH.with_suffix(".tmp")
                tmp.write_bytes(jpeg)
                tmp.replace(PHONE_SCREEN_PATH)
            set_phone_screen(at=time.time(), width=width, height=height)
        except Exception:
            pass

    threading.Thread(target=_run, name="phone-screen", daemon=True).start()


def read_phone_screen() -> bytes | None:
    try:
        if not PHONE_SCREEN_PATH.is_file():
            return None
        data = PHONE_SCREEN_PATH.read_bytes()
    except OSError:
        return None
    return data or None


# Backward-compatible public facade for the split control/presentation domain.
from status_control import (  # noqa: E402
    register_orchestrator,
    unregister_orchestrator,
    register_agent_process,
    unregister_agent_process,
    request_quit,
    clear_quit_request,
    quit_requested,
    is_mark_done_utterance,
    request_mark_done,
    mark_done_pending,
    consume_mark_done,
    clear_mark_done,
    set_stt_listening,
    request_listen,
    listen_pending,
    consume_listen,
    request_send,
    send_pending,
    consume_send,
    clear_send,
    request_cancel,
    cancel_pending,
    consume_cancel,
    clear_cancel,
    pid_alive,
    signal_quit_orchestrator,
    upsert_agent,
    remove_agent,
    active_agents,
    format_tooltip,
    status_label,
)
