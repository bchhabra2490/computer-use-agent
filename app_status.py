"""
Shared live status + recent log lines for the macOS menu-bar tray.

Orchestrator / agent write here; `status_tray.py` polls and shows hover tooltip
+ click menu. State lives in a JSON file so separate processes can share it.
"""

from __future__ import annotations

import json
import os
import re
import signal
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
        "cancel_requested": False,
        "stt_active": False,
        "agents": [],  # active subagents / computer-agent jobs
        "overlay_hidden": False,
        "overlay_ack_hidden": False,
        "overlay_enabled": True,
        "face_overlay_enabled": True,
        "tts_playing": False,
        "tts_play_depth": 0,
        "phone_gateway_pid": None,
        "pending_utterances": [],
        "pending_speaks": [],
        "last_spoken": None,
        "last_llm": None,
        "reply_sink": "mac",
        "speech_at": None,
        "speech_bytes": None,
        "screen_at": None,
        "screen_width": None,
        "screen_height": None,
        "phone_photo_at": None,
        "phone_photo_pending": False,
        "phone_photo_width": None,
        "phone_photo_height": None,
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
        return base
    except Exception:
        return _default_state()


def _write(data: dict[str, Any]) -> None:
    _ensure_dir()
    data["updated_at"] = time.time()
    tmp = STATUS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATUS_PATH)


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


def enqueue_utterance(text: str, *, source: str = "phone", photo: bool = False) -> None:
    """Queue a text command (phone gateway). Orchestrator consumes it like STT."""
    text = (text or "").strip()
    if not text:
        return
    source = (source or "phone").strip() or "phone"
    with _lock:
        data = _read()
        pending = list(data.get("pending_utterances") or [])
        pending.append(
            {
                "text": text,
                "source": source,
                "ts": time.time(),
                "photo": bool(photo),
            }
        )
        data["pending_utterances"] = pending[-20:]
        _write(data)
    kind = "photo" if photo else "queued"
    log(f"[phone] {kind}: {text[:160]}")


def utterance_pending() -> bool:
    with _lock:
        pending = _read().get("pending_utterances") or []
        return bool(pending)


def _normalize_sink(sink: str | None) -> str:
    return "phone" if (sink or "").strip().lower() == "phone" else "mac"


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


def consume_utterance() -> str | None:
    """Pop the next queued text command, or None."""
    with _lock:
        data = _read()
        pending = list(data.get("pending_utterances") or [])
        if not pending:
            return None
        item = pending.pop(0)
        data["pending_utterances"] = pending
        if isinstance(item, str):
            data["reply_sink"] = "phone"
        else:
            src = str((item or {}).get("source") or "phone").strip().lower()
            data["reply_sink"] = "phone" if src == "phone" else "mac"
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
        _write(data)
    if isinstance(item, str):
        text = item.strip()
        return text or None
    text = str((item or {}).get("text") or "").strip()
    return text or None


def set_last_spoken(text: str) -> None:
    text = (text or "").strip()
    if not text:
        return
    with _lock:
        data = _read()
        data["last_spoken"] = text[:2000]
        _write(data)


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


def register_orchestrator(pid: int | None = None) -> None:
    with _lock:
        data = _read()
        data["orchestrator_pid"] = int(pid if pid is not None else os.getpid())
        data["quit_requested"] = False
        data["done_requested"] = False
        data["done_agent_id"] = None
        data["send_requested"] = False
        data["cancel_requested"] = False
        data["stt_active"] = False
        _write(data)


def unregister_orchestrator() -> None:
    with _lock:
        data = _read()
        data["orchestrator_pid"] = None
        data["quit_requested"] = False
        data["agents"] = []
        _write(data)


def register_agent_process(pid: int | None = None) -> None:
    """Standalone `python agent.py` process (not under orchestrator)."""
    with _lock:
        data = _read()
        data["agent_pid"] = int(pid if pid is not None else os.getpid())
        data["quit_requested"] = False
        _write(data)


def unregister_agent_process() -> None:
    with _lock:
        data = _read()
        data["agent_pid"] = None
        _write(data)


def request_quit() -> None:
    """Ask the orchestrator (or standalone agent) to exit."""
    with _lock:
        data = _read()
        data["quit_requested"] = True
        _write(data)
    log("Quit requested from menu bar")


def clear_quit_request() -> None:
    with _lock:
        data = _read()
        data["quit_requested"] = False
        _write(data)


def quit_requested() -> bool:
    with _lock:
        return bool(_read().get("quit_requested"))


_MARK_DONE_RE = re.compile(
    r"\b("
    r"mark (?:it |the task |this |the job )?(?:as )?done"
    r"|mark done"
    r"|that(?:'s| is) done"
    r"|task is done"
    r"|stop (?:the )?(?:task|agent|job|run)"
    r"|pause (?:the )?(?:task|agent|job|run)"
    r"|cancel (?:the )?(?:task|agent|job|run)"
    r"|no (?:other|further) actions?(?: (?:is|are))? required"
    r"|no further action"
    r"|nothing else (?:to do|needed|required)"
    r"|that(?:'s| is) all(?: we need)?"
    r")\b",
    re.IGNORECASE,
)

# Bare stop/pause — what users say when the agent says "say stop anytime".
# Keep these exact so "stop listening" / "stop the music" stay out.
_MARK_DONE_EXACT = frozenset(
    {
        "stop",
        "pause",
        "cancel",
        "abort",
        "halt",
        "done",
        "finished",
        "complete",
        "that's it",
        "thats it",
    }
)


def is_mark_done_utterance(text: str) -> bool:
    """True when the user wants the running computer task marked complete."""
    low = (text or "").strip().lower().rstrip(".!?")
    if not low:
        return False
    if low in _MARK_DONE_EXACT:
        return True
    if _MARK_DONE_RE.search(low):
        return True
    return False


def request_mark_done(agent_id: str | None = None) -> None:
    """Ask the running computer-agent job to finish (menu bar or voice)."""
    agent_id = (agent_id or "").strip() or None
    with _lock:
        data = _read()
        data["done_requested"] = True
        data["done_agent_id"] = agent_id
        _write(data)
    if agent_id:
        log(f"Mark done requested (agent {agent_id})")
    else:
        log("Mark done requested")


def mark_done_pending(agent_id: str | None = None) -> bool:
    """True if mark-done was requested for this agent (or for all agents)."""
    agent_id = (agent_id or "").strip() or None
    with _lock:
        data = _read()
        if not data.get("done_requested"):
            return False
        target = (data.get("done_agent_id") or "").strip() or None
        if target and agent_id and target != agent_id:
            return False
        return True


def consume_mark_done(agent_id: str | None = None) -> bool:
    """Like mark_done_pending, but clears the flag when it matches."""
    agent_id = (agent_id or "").strip() or None
    with _lock:
        data = _read()
        if not data.get("done_requested"):
            return False
        target = (data.get("done_agent_id") or "").strip() or None
        if target and agent_id and target != agent_id:
            return False
        data["done_requested"] = False
        data["done_agent_id"] = None
        _write(data)
        return True


def clear_mark_done() -> None:
    with _lock:
        data = _read()
        data["done_requested"] = False
        data["done_agent_id"] = None
        _write(data)


def set_stt_listening(active: bool) -> None:
    """STT owns the mic — tray Send/Cancel are enabled while this is True."""
    with _lock:
        data = _read()
        data["stt_active"] = bool(active)
        if active:
            data["cancel_requested"] = False
            data["send_requested"] = False
        else:
            data["send_requested"] = False
            data["cancel_requested"] = False
        _write(data)


def request_send() -> None:
    """End the current listen immediately and transcribe what was captured."""
    with _lock:
        data = _read()
        data["send_requested"] = True
        data["cancel_requested"] = False
        _write(data)
    log("Send requested — processing audio")


def send_pending() -> bool:
    with _lock:
        return bool(_read().get("send_requested"))


def consume_send() -> bool:
    """True if Send was clicked; clears the flag so it fires once."""
    with _lock:
        data = _read()
        if not data.get("send_requested"):
            return False
        data["send_requested"] = False
        _write(data)
        return True


def clear_send() -> None:
    with _lock:
        data = _read()
        data["send_requested"] = False
        _write(data)


def request_cancel() -> None:
    """Abort the current listen (no transcript) and stop in-flight agent work.

    While STT is active: discards capture. If computer-use agents are running:
    also requests mark-done so UI actions stop.
    """
    with _lock:
        data = _read()
        data["cancel_requested"] = True
        data["send_requested"] = False
        # Drop queued text/phone commands so they are not processed next.
        data["pending_utterances"] = []
        agents = list(data.get("agents") or [])
        _write(data)
    log("Cancel requested — abort listen / processing")
    if agents:
        request_mark_done()


def cancel_pending() -> bool:
    with _lock:
        return bool(_read().get("cancel_requested"))


def consume_cancel() -> bool:
    """True if Cancel was requested; clears the flag so it fires once."""
    with _lock:
        data = _read()
        if not data.get("cancel_requested"):
            return False
        data["cancel_requested"] = False
        _write(data)
        return True


def clear_cancel() -> None:
    with _lock:
        data = _read()
        data["cancel_requested"] = False
        _write(data)


def pid_alive(pid: Any) -> bool:
    try:
        p = int(pid)
    except (TypeError, ValueError):
        return False
    if p <= 0:
        return False
    try:
        os.kill(p, 0)
        return True
    except OSError:
        return False


def signal_quit_orchestrator() -> bool:
    """
    Soft-quit via flag, then SIGTERM the orchestrator process if known.

    Returns True if a signal was sent (or only the flag was set because no pid).
    """
    request_quit()
    data = read_status()
    pid = data.get("orchestrator_pid")
    if pid_alive(pid):
        try:
            os.kill(int(pid), signal.SIGTERM)
            log(f"Sent SIGTERM to orchestrator (pid={pid})")
            return True
        except OSError as e:
            log(f"Failed to signal orchestrator: {e}")
            return False
    # Standalone agent?
    apid = data.get("agent_pid")
    if pid_alive(apid):
        try:
            os.kill(int(apid), signal.SIGTERM)
            log(f"Sent SIGTERM to agent (pid={apid})")
            return True
        except OSError as e:
            log(f"Failed to signal agent: {e}")
            return False
    return True


def upsert_agent(
    agent_id: str,
    *,
    task: str,
    kind: str = "computer-agent",
    status: str = "running",
    log_dir: str | None = None,
) -> None:
    """Register or refresh an in-progress subagent / computer-agent job."""
    agent_id = (agent_id or "").strip()
    if not agent_id:
        return
    task = (task or "").strip()
    now = time.time()
    with _lock:
        data = _read()
        agents = [a for a in (data.get("agents") or []) if isinstance(a, dict)]
        found = None
        for a in agents:
            if a.get("id") == agent_id:
                found = a
                break
        if found is None:
            found = {
                "id": agent_id,
                "kind": kind,
                "task": task,
                "status": status,
                "started_at": now,
                "log_dir": log_dir,
            }
            agents.append(found)
        else:
            found["kind"] = kind
            found["task"] = task or found.get("task")
            found["status"] = status
            if log_dir is not None:
                found["log_dir"] = log_dir
            found["updated_at"] = now
        data["agents"] = agents
        if task:
            data["task"] = task
        if log_dir is not None:
            data["log_dir"] = log_dir
        _write(data)


def remove_agent(agent_id: str) -> None:
    agent_id = (agent_id or "").strip()
    if not agent_id:
        return
    with _lock:
        data = _read()
        agents = [a for a in (data.get("agents") or []) if isinstance(a, dict) and a.get("id") != agent_id]
        data["agents"] = agents
        if not agents:
            # Clear primary task if nothing left running.
            if data.get("state") == "agent":
                data["detail"] = "No active agents"
        _write(data)


def active_agents(data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = data or read_status()
    agents = [a for a in (data.get("agents") or []) if isinstance(a, dict)]
    return [a for a in agents if (a.get("status") or "running") != "done"]


def format_tooltip(data: dict[str, Any] | None = None, *, max_log_lines: int = 10) -> str:
    """Plain-text tooltip for NSStatusItem hover."""
    data = data or read_status()
    state = data.get("state") or "idle"
    detail = (data.get("detail") or "").strip()
    task = (data.get("task") or "").strip()
    lines = [f"Jarvis · {state}"]
    if detail:
        lines.append(detail[:120])
    agents = active_agents(data)
    if agents:
        lines.append(f"In progress ({len(agents)}):")
        for a in agents[:5]:
            label = (a.get("task") or a.get("id") or "?").strip()
            kind = (a.get("kind") or "agent").strip()
            lines.append(f"  • [{kind}] {label[:90]}")
    elif task:
        lines.append(f"Task: {task[:100]}")
    logs = list(data.get("logs") or [])
    if logs:
        lines.append("─" * 24)
        for entry in logs[-max_log_lines:]:
            lines.append(entry[:140])
    else:
        lines.append("(no recent logs)")
    text = "\n".join(lines)
    if len(text) > 1800:
        text = text[:1800] + "\n…"
    return text


def status_label(data: dict[str, Any] | None = None) -> str:
    data = data or read_status()
    agents = active_agents(data)
    state = data.get("state") or "idle"
    if agents:
        return f"{state} · {len(agents)} agent(s)"[:80]
    detail = (data.get("detail") or "").strip()
    if detail:
        return f"{state}: {detail}"[:80]
    return str(state)
