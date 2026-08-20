"""Optional LAN/Tailscale HTTP gateway for a companion phone app.

Opt-in: ``PHONE_GATEWAY=1``. Off by default so CUA does not bind a port.

The phone never drives the desktop. It queues text (same path as STT),
accepts a short audio clip (``POST /v1/audio``) that the Mac transcribes,
accepts a camera still (``POST /v1/photo``) for the orchestrator to look at
(optional mic clip is transcribed as the caption),
toggles tray flags (send / mark done / quit), and streams ``status.json``.

TTS is synthesized on the Mac. Phone turns skip ``afplay`` and publish a WAV
at ``GET /v1/speech`` when ``speech_at`` changes; Mac wake-word turns still
play locally.

Auth: Bearer token in ``Authorization`` or ``?token=`` (SSE). Token lives in
``.runtime/phone.token`` (or ``PHONE_GATEWAY_TOKEN``). Max 5 characters so it
is easy to type on a phone.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from email import message_from_bytes
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from app_status import (
    RUNTIME_DIR,
    active_agents,
    enqueue_utterance,
    pid_alive,
    read_phone_screen,
    read_phone_speech,
    read_status,
    request_mark_done,
    request_quit,
    request_send,
    set_phone_gateway_pid,
    write_phone_photo,
)

HOST = os.environ.get("PHONE_GATEWAY_HOST", "0.0.0.0").strip() or "0.0.0.0"
PORT = int(os.environ.get("PHONE_GATEWAY_PORT", "8742"))
TOKEN_PATH = RUNTIME_DIR / "phone.token"
TOKEN_LEN = 5
# Unambiguous for phone typing (no 0/O/1/I/L).
_TOKEN_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_OFF = {"0", "false", "no", "off"}
AUDIO_MAX_BYTES = int(os.environ.get("PHONE_AUDIO_MAX_BYTES", str(2_500_000)))
PHOTO_MAX_BYTES = int(os.environ.get("PHONE_PHOTO_MAX_BYTES", str(6_000_000)))
PHOTO_MAX_WIDTH = int(os.environ.get("PHONE_PHOTO_MAX_WIDTH", "1280"))
PHOTO_JPEG_QUALITY = int(os.environ.get("PHONE_PHOTO_QUALITY", "70"))
JSON_MAX_BYTES = 32_000
DEFAULT_PHOTO_PROMPT = "Look at this photo from my phone. Explain what you see. I may ask follow-up questions."


def phone_gateway_enabled() -> bool:
    return os.environ.get("PHONE_GATEWAY", "0").strip().lower() not in _OFF


def _normalize_token(raw: str) -> str:
    return (raw or "").strip()[:TOKEN_LEN]


def _new_token() -> str:
    return "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(TOKEN_LEN))


def _write_token(token: str) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(token + "\n", encoding="utf-8")
    try:
        TOKEN_PATH.chmod(0o600)
    except OSError:
        pass


def load_or_create_token() -> str:
    env = _normalize_token(os.environ.get("PHONE_GATEWAY_TOKEN") or "")
    if env:
        return env
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if TOKEN_PATH.is_file():
        raw = TOKEN_PATH.read_text(encoding="utf-8").strip()
        if len(raw) == TOKEN_LEN:
            return raw
    token = _new_token()
    _write_token(token)
    return token


def advertise_urls(port: int = PORT) -> list[str]:
    urls = [f"http://127.0.0.1:{port}"]
    seen = {"127.0.0.1", "localhost"}
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM):
            ip = info[4][0]
            if ip in seen or ip.startswith("127."):
                continue
            seen.add(ip)
            urls.append(f"http://{ip}:{port}")
    except OSError:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        ip = probe.getsockname()[0]
        probe.close()
        if ip not in seen and not ip.startswith("127."):
            urls.append(f"http://{ip}:{port}")
    except OSError:
        pass
    return urls


def phone_status_payload(data: dict[str, Any] | None = None) -> dict[str, Any]:
    snap = data if data is not None else read_status()
    agents = active_agents(snap)
    return {
        "state": snap.get("state") or "idle",
        "detail": snap.get("detail") or "",
        "task": snap.get("task"),
        "updated_at": snap.get("updated_at") or 0.0,
        "stt_active": bool(snap.get("stt_active")),
        "logs": list(snap.get("logs") or [])[-40:],
        "agents": agents,
        "last_spoken": snap.get("last_spoken"),
        "last_llm": snap.get("last_llm"),
        "queued": bool(snap.get("pending_utterances")),
        "reply_sink": snap.get("reply_sink") or "mac",
        "speech_at": snap.get("speech_at"),
        "speech_bytes": snap.get("speech_bytes"),
        "screen_at": snap.get("screen_at"),
        "screen_width": snap.get("screen_width"),
        "screen_height": snap.get("screen_height"),
        "photo_at": snap.get("phone_photo_at"),
        "photo_width": snap.get("phone_photo_width"),
        "photo_height": snap.get("phone_photo_height"),
        "photo_pending": bool(snap.get("phone_photo_pending")),
    }


def apply_control(action: str) -> dict[str, Any]:
    key = (action or "").strip().lower()
    if key == "send":
        request_send()
        return {"ok": True, "action": "send"}
    if key in {"mark_done", "done"}:
        request_mark_done()
        return {"ok": True, "action": "mark_done"}
    if key == "quit":
        request_quit()
        return {"ok": True, "action": "quit"}
    return {"ok": False, "error": f"unknown action {key!r}"}


def _is_wav(data: bytes) -> bool:
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


_AUDIO_EXTS = (".wav", ".m4a", ".mp4", ".aac", ".mp3", ".caf", ".webm", ".ogg", ".flac")
_PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".tif", ".tiff")
_PHOTO_FIELD_NAMES = {"photo", "image", "camera", "picture"}
_AUDIO_FIELD_NAMES = {"audio", "voice", "recording", "caption_audio", "mic"}
_TEXT_FIELD_NAMES = {"text", "command", "caption", "prompt", "transcript"}


def _suffix_for_audio(*, filename: str = "", content_type: str = "") -> str:
    name = (filename or "").lower()
    for ext in (".wav", ".m4a", ".mp4", ".aac", ".mp3", ".caf", ".webm", ".ogg", ".flac"):
        if name.endswith(ext):
            return ext
    ctype = (content_type or "").split(";")[0].strip().lower()
    return {
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/wave": ".wav",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/mp4": ".m4a",
        "audio/m4a": ".m4a",
        "audio/x-m4a": ".m4a",
        "audio/aac": ".m4a",
        "audio/x-caf": ".caf",
        "audio/caf": ".caf",
        "audio/webm": ".webm",
        "audio/ogg": ".ogg",
        "audio/flac": ".flac",
    }.get(ctype, ".m4a")


def audio_to_wav(audio: bytes, *, filename: str = "", content_type: str = "") -> bytes:
    """Return WAV bytes. Passthrough if already WAV; otherwise afconvert on macOS."""
    if not audio:
        return audio
    if _is_wav(audio):
        return audio
    suffix = _suffix_for_audio(filename=filename, content_type=content_type)
    if sys.platform != "darwin":
        return audio
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"in{suffix}"
        dst = Path(tmp) / "out.wav"
        src.write_bytes(audio)
        try:
            proc = subprocess.run(
                ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", str(src), str(dst)],
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            return audio
        if proc.returncode == 0 and dst.is_file() and dst.stat().st_size > 44:
            return dst.read_bytes()
    return audio


def _part_payload(part) -> bytes:
    payload = part.get_payload(decode=True)
    if payload is None:
        return b""
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return payload


def _is_audio_part(*, name: str = "", filename: str = "", content_type: str = "") -> bool:
    if (name or "").lower() in _AUDIO_FIELD_NAMES:
        return True
    fname = (filename or "").lower()
    if any(fname.endswith(ext) for ext in _AUDIO_EXTS):
        return True
    ctype = (content_type or "").split(";")[0].strip().lower()
    return ctype.startswith("audio/")


def _is_photo_part(*, name: str = "", filename: str = "", content_type: str = "") -> bool:
    if (name or "").lower() in _PHOTO_FIELD_NAMES:
        return True
    fname = (filename or "").lower()
    if any(fname.endswith(ext) for ext in _PHOTO_EXTS):
        return True
    ctype = (content_type or "").split(";")[0].strip().lower()
    return ctype.startswith("image/")


def transcribe_phone_audio(
    audio: bytes,
    *,
    filename: str = "",
    content_type: str = "",
) -> dict[str, Any]:
    """Transcribe a phone clip. Does not enqueue. ``{ok, text}`` or ``{ok: False, error}``."""
    if not audio:
        return {"ok": False, "error": "audio required"}
    if len(audio) > AUDIO_MAX_BYTES:
        return {"ok": False, "error": "audio too large"}
    wav = audio_to_wav(audio, filename=filename, content_type=content_type)
    try:
        from stt import NoSpeechError, transcribe
    except Exception as e:
        return {"ok": False, "error": f"stt unavailable: {e}"}
    try:
        heard = transcribe(None, wav)
    except NoSpeechError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"transcription failed: {e}"}
    heard = (heard or "").strip()
    if not heard:
        return {"ok": False, "error": "empty transcript"}
    return {"ok": True, "text": heard}


def parse_audio_body(
    body: bytes,
    *,
    content_type: str = "",
) -> dict[str, Any]:
    """Extract audio bytes + optional text from JSON, multipart, or raw body."""
    ctype = (content_type or "").split(";")[0].strip().lower()
    if "multipart/form-data" in (content_type or "").lower():
        preamble = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
        msg = message_from_bytes(preamble + body, policy=default)
        audio = b""
        filename = ""
        text = ""
        part_type = ""
        if msg.is_multipart():
            for part in msg.iter_parts():
                name = str(part.get_param("name", header="content-disposition") or "")
                fn = part.get_filename() or ""
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                if isinstance(payload, str):
                    payload = payload.encode("utf-8")
                if name in {"text", "command", "transcript"}:
                    text = payload.decode("utf-8", errors="replace").strip()
                elif name in {"audio", "file", "recording", "voice"} or fn:
                    audio = payload
                    filename = fn
                    part_type = part.get_content_type() or ""
        return {
            "audio": audio,
            "filename": filename,
            "text": text,
            "content_type": part_type or ctype,
        }
    if ctype in {"application/json", "text/json"}:
        data = json.loads(body.decode("utf-8") or "{}")
        if not isinstance(data, dict):
            raise ValueError("JSON object required")
        b64 = str(data.get("audio") or data.get("data") or "").strip()
        audio = base64.b64decode(b64) if b64 else b""
        return {
            "audio": audio,
            "filename": str(data.get("filename") or data.get("name") or ""),
            "text": str(data.get("text") or data.get("command") or "").strip(),
            "content_type": str(data.get("mime") or data.get("content_type") or ctype),
        }
    return {
        "audio": body,
        "filename": "",
        "text": "",
        "content_type": ctype,
    }


def ingest_phone_audio(
    audio: bytes,
    *,
    filename: str = "",
    content_type: str = "",
    text: str = "",
) -> dict[str, Any]:
    """Transcribe phone audio (unless ``text`` is already set) and queue it."""
    text = (text or "").strip()
    if text:
        enqueue_utterance(text, source="phone", input_kind="text")
        return {"ok": True, "queued": True, "text": text, "source": "text"}
    result = transcribe_phone_audio(audio, filename=filename, content_type=content_type)
    if not result.get("ok"):
        return result
    heard = str(result.get("text") or "").strip()
    enqueue_utterance(heard, source="phone", input_kind="mic")
    return {"ok": True, "queued": True, "text": heard, "source": "audio"}


def _sips_to_jpeg(src: Path, dst: Path, max_width: int) -> bool:
    try:
        proc = subprocess.run(
            [
                "sips",
                "-s",
                "format",
                "jpeg",
                "-Z",
                str(max(320, max_width)),
                str(src),
                "--out",
                str(dst),
            ],
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and dst.is_file() and dst.stat().st_size > 0


def photo_to_jpeg(
    data: bytes,
    *,
    filename: str = "",
    content_type: str = "",
    max_width: int | None = None,
    quality: int | None = None,
) -> tuple[bytes, int, int]:
    """Normalize a phone still to a resized JPEG (EXIF-rotated)."""
    if not data:
        raise ValueError("empty photo")
    max_w = max(320, int(max_width or PHOTO_MAX_WIDTH))
    q = max(40, min(int(quality or PHOTO_JPEG_QUALITY), 90))
    from io import BytesIO

    from PIL import Image, ImageOps

    img = None
    try:
        img = Image.open(BytesIO(data))
        img.load()
    except Exception:
        img = None
    if img is None:
        suffix = _suffix_for_photo(filename=filename, content_type=content_type)
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / f"in{suffix}"
            dst = Path(tmp) / "out.jpg"
            src.write_bytes(data)
            if not _sips_to_jpeg(src, dst, max_w):
                raise ValueError("unsupported image")
            jpeg = dst.read_bytes()
        img = Image.open(BytesIO(jpeg))
        img.load()
    img = ImageOps.exif_transpose(img)
    if img.mode not in {"RGB", "L"}:
        img = img.convert("RGB")
    elif img.mode == "L":
        img = img.convert("RGB")
    if img.width > max_w:
        ratio = max_w / img.width
        img = img.resize((max_w, max(1, round(img.height * ratio))))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=q, optimize=True)
    jpeg = buf.getvalue()
    if not jpeg:
        raise ValueError("jpeg encode failed")
    return jpeg, img.width, img.height


def _suffix_for_photo(*, filename: str = "", content_type: str = "") -> str:
    name = (filename or "").lower()
    for ext in (".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".tif", ".tiff"):
        if name.endswith(ext):
            return ".jpg" if ext in {".jpg", ".jpeg"} else ext
    ctype = (content_type or "").split(";")[0].strip().lower()
    return {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/heic": ".heic",
        "image/heif": ".heif",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/tiff": ".tiff",
    }.get(ctype, ".jpg")


def parse_photo_body(
    body: bytes,
    *,
    content_type: str = "",
) -> dict[str, Any]:
    """Extract image + optional caption text or mic audio from JSON, multipart, or raw body."""
    ctype = (content_type or "").split(";")[0].strip().lower()
    empty = {
        "photo": b"",
        "filename": "",
        "text": "",
        "content_type": ctype,
        "audio": b"",
        "audio_filename": "",
        "audio_content_type": "",
    }
    if "multipart/form-data" in (content_type or "").lower():
        preamble = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
        msg = message_from_bytes(preamble + body, policy=default)
        photo = b""
        filename = ""
        text = ""
        part_type = ""
        audio = b""
        audio_filename = ""
        audio_type = ""
        if msg.is_multipart():
            for part in msg.iter_parts():
                name = str(part.get_param("name", header="content-disposition") or "")
                fn = part.get_filename() or ""
                payload = _part_payload(part)
                if not payload:
                    continue
                ptype = part.get_content_type() or ""
                key = name.lower()
                if key in _TEXT_FIELD_NAMES:
                    text = payload.decode("utf-8", errors="replace").strip()
                    continue
                if _is_photo_part(name=name, filename=fn, content_type=ptype):
                    photo = payload
                    filename = fn
                    part_type = ptype
                    continue
                if _is_audio_part(name=name, filename=fn, content_type=ptype):
                    audio = payload
                    audio_filename = fn
                    audio_type = ptype
                    continue
                if fn and not photo:
                    photo = payload
                    filename = fn
                    part_type = ptype
                elif fn and not audio:
                    audio = payload
                    audio_filename = fn
                    audio_type = ptype
        return {
            "photo": photo,
            "filename": filename,
            "text": text,
            "content_type": part_type or ctype,
            "audio": audio,
            "audio_filename": audio_filename,
            "audio_content_type": audio_type,
        }
    if ctype in {"application/json", "text/json"}:
        data = json.loads(body.decode("utf-8") or "{}")
        if not isinstance(data, dict):
            raise ValueError("JSON object required")
        b64 = str(data.get("photo") or data.get("image") or data.get("data") or "").strip()
        photo = base64.b64decode(b64) if b64 else b""
        audio_b64 = str(data.get("audio") or data.get("voice") or "").strip()
        audio = base64.b64decode(audio_b64) if audio_b64 else b""
        return {
            "photo": photo,
            "filename": str(data.get("filename") or data.get("name") or ""),
            "text": str(data.get("text") or data.get("command") or data.get("caption") or "").strip(),
            "content_type": str(data.get("mime") or data.get("content_type") or ctype),
            "audio": audio,
            "audio_filename": str(data.get("audio_filename") or ""),
            "audio_content_type": str(
                data.get("audio_mime") or data.get("audio_content_type") or ""
            ),
        }
    return empty | {"photo": body, "content_type": ctype}


def ingest_phone_photo(
    photo: bytes,
    *,
    filename: str = "",
    content_type: str = "",
    text: str = "",
    audio: bytes = b"",
    audio_filename: str = "",
    audio_content_type: str = "",
) -> dict[str, Any]:
    """Resize a phone still, store it, and queue a vision request.

    Caption order: explicit ``text``, else transcribed ``audio``, else the
    default explain-this-photo prompt.
    """
    text = (text or "").strip()
    caption_source = "text" if text else ""
    if not text and audio:
        heard = transcribe_phone_audio(
            audio,
            filename=audio_filename,
            content_type=audio_content_type,
        )
        if not heard.get("ok"):
            return heard
        text = str(heard.get("text") or "").strip()
        caption_source = "audio"
    if not text:
        text = DEFAULT_PHOTO_PROMPT
        caption_source = "default"
    if not photo:
        return {"ok": False, "error": "photo required"}
    if len(photo) > PHOTO_MAX_BYTES:
        return {"ok": False, "error": "photo too large"}
    try:
        jpeg, width, height = photo_to_jpeg(
            photo,
            filename=filename,
            content_type=content_type,
        )
    except Exception as e:
        return {"ok": False, "error": f"unsupported image: {e}"}
    write_phone_photo(jpeg, width=width, height=height)
    enqueue_utterance(text, source="phone", photo=True, input_kind="photo")
    return {
        "ok": True,
        "queued": True,
        "text": text,
        "source": "photo",
        "caption_source": caption_source,
        "width": width,
        "height": height,
    }


def ensure_phone_gateway() -> subprocess.Popen | None:
    """Spawn the gateway process when ``PHONE_GATEWAY=1``."""
    if not phone_gateway_enabled():
        return None
    try:
        data = read_status()
        pid = data.get("phone_gateway_pid")
        if pid_alive(pid):
            return None
    except Exception:
        pass

    token = load_or_create_token()
    script = Path(__file__).resolve()
    env = os.environ.copy()
    env["PHONE_GATEWAY_CHILD"] = "1"
    env["PHONE_GATEWAY"] = "1"
    try:
        proc = subprocess.Popen(
            [sys.executable, str(script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
    except Exception as e:
        print(f"[phone] failed to start gateway: {e}", file=sys.stderr)
        return None
    try:
        set_phone_gateway_pid(proc.pid)
    except Exception:
        pass
    print(f"[phone] gateway started (pid={proc.pid}) port={PORT}", flush=True)
    for url in advertise_urls(PORT):
        print(f"[phone] {url}", flush=True)
    print(f"[phone] token saved at {TOKEN_PATH}", flush=True)
    print(f"[phone] Authorization: Bearer {token}", flush=True)
    return proc


def stop_phone_gateway(*, wait: float = 1.5) -> None:
    if os.environ.get("PHONE_GATEWAY_CHILD", "").strip() == "1":
        return
    try:
        pid = read_status().get("phone_gateway_pid")
    except Exception:
        return
    if not pid_alive(pid):
        return
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return
    if pid == os.getpid():
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.monotonic() + max(0.0, wait)
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            try:
                set_phone_gateway_pid(None)
            except Exception:
                pass
            return
        time.sleep(0.05)


class PhoneGatewayHandler(BaseHTTPRequestHandler):
    server_version = "JarvisPhoneGateway/1.0"
    token = ""

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[phone] " + fmt % args, flush=True)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _read_body(self, max_bytes: int) -> bytes:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return b""
        if length > max_bytes:
            raise ValueError("body too large")
        return self.rfile.read(length)

    def _read_json(self) -> dict[str, Any]:
        raw = self._read_body(JSON_MAX_BYTES)
        if not raw:
            return {}
        data = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(data, dict):
            raise ValueError("JSON object required")
        return data

    def _token_from_request(self) -> str:
        auth = (self.headers.get("Authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        query = parse_qs(urlparse(self.path).query)
        values = query.get("token") or []
        return (values[0] if values else "").strip()

    def _authorized(self) -> bool:
        expected = (getattr(self, "token", None) or "").strip()
        if not expected:
            return False
        return secrets.compare_digest(self._token_from_request(), expected)

    def _send_json(self, code: int, payload: dict[str, Any]) -> None:
        blob = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def _send_jpeg(self, blob: bytes, *, screen_at: Any = None) -> None:
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(blob)))
        self.send_header("Cache-Control", "no-store")
        if screen_at is not None:
            self.send_header("ETag", f'"{screen_at}"')
        self.end_headers()
        self.wfile.write(blob)

    def _send_wav(self, blob: bytes, *, speech_at: Any = None) -> None:
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(blob)))
        self.send_header("Cache-Control", "no-store")
        if speech_at is not None:
            self.send_header("ETag", f'"{speech_at}"')
        self.end_headers()
        self.wfile.write(blob)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path in {"/", "/v1/health"}:
            self._send_json(
                200,
                {"ok": True, "service": "cua-phone-gateway", "auth": True},
            )
            return
        if not self._authorized():
            self._send_json(401, {"ok": False, "error": "unauthorized"})
            return
        if path == "/v1/status":
            self._send_json(200, {"ok": True, **phone_status_payload()})
            return
        if path in {"/v1/screen", "/v1/screenshot"}:
            blob = read_phone_screen()
            if not blob:
                self._send_json(404, {"ok": False, "error": "no screenshot yet"})
                return
            snap = read_status()
            self._send_jpeg(blob, screen_at=snap.get("screen_at"))
            return
        if path in {"/v1/speech", "/v1/tts"}:
            blob = read_phone_speech()
            if not blob:
                self._send_json(404, {"ok": False, "error": "no speech yet"})
                return
            snap = read_status()
            self._send_wav(blob, speech_at=snap.get("speech_at"))
            return
        if path == "/v1/events":
            self._stream_events()
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self._send_json(401, {"ok": False, "error": "unauthorized"})
            return
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/v1/audio":
            try:
                raw = self._read_body(max(AUDIO_MAX_BYTES * 2, AUDIO_MAX_BYTES))
                parsed = parse_audio_body(
                    raw,
                    content_type=self.headers.get("Content-Type") or "",
                )
            except Exception as e:
                self._send_json(400, {"ok": False, "error": str(e)})
                return
            result = ingest_phone_audio(
                parsed.get("audio") or b"",
                filename=str(parsed.get("filename") or ""),
                content_type=str(parsed.get("content_type") or ""),
                text=str(parsed.get("text") or ""),
            )
            code = 200 if result.get("ok") else 400
            self._send_json(code, result)
            return
        if path in {"/v1/photo", "/v1/image", "/v1/camera"}:
            try:
                raw = self._read_body(max(PHOTO_MAX_BYTES * 2 + AUDIO_MAX_BYTES * 2, PHOTO_MAX_BYTES))
                parsed = parse_photo_body(
                    raw,
                    content_type=self.headers.get("Content-Type") or "",
                )
            except ValueError as e:
                self._send_json(413 if "too large" in str(e) else 400, {"ok": False, "error": str(e)})
                return
            except Exception as e:
                self._send_json(400, {"ok": False, "error": str(e)})
                return
            result = ingest_phone_photo(
                parsed.get("photo") or b"",
                filename=str(parsed.get("filename") or ""),
                content_type=str(parsed.get("content_type") or ""),
                text=str(parsed.get("text") or ""),
                audio=parsed.get("audio") or b"",
                audio_filename=str(parsed.get("audio_filename") or ""),
                audio_content_type=str(parsed.get("audio_content_type") or ""),
            )
            code = 200 if result.get("ok") else 400
            self._send_json(code, result)
            return
        try:
            body = self._read_json()
        except Exception as e:
            self._send_json(400, {"ok": False, "error": str(e)})
            return
        if path == "/v1/command":
            text = str(body.get("text") or body.get("command") or "").strip()
            if not text:
                self._send_json(400, {"ok": False, "error": "text required"})
                return
            enqueue_utterance(text, source="phone", input_kind="text")
            self._send_json(200, {"ok": True, "queued": True, "text": text})
            return
        if path == "/v1/control":
            result = apply_control(str(body.get("action") or ""))
            code = 200 if result.get("ok") else 400
            self._send_json(code, result)
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def _stream_events(self) -> None:
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        last = None
        try:
            while True:
                payload = phone_status_payload()
                sig = (
                    payload.get("updated_at"),
                    payload.get("state"),
                    len(payload.get("logs") or []),
                    payload.get("last_spoken"),
                    payload.get("last_llm"),
                    payload.get("queued"),
                    payload.get("screen_at"),
                    payload.get("speech_at"),
                    payload.get("photo_at"),
                )
                if sig != last:
                    last = sig
                    blob = json.dumps({"ok": True, **payload})
                    self.wfile.write(f"event: status\ndata: {blob}\n\n".encode("utf-8"))
                    self.wfile.flush()
                time.sleep(0.4)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return


def serve(host: str = HOST, port: int = PORT, *, token: str | None = None) -> None:
    tok = token if token is not None else load_or_create_token()

    class BoundHandler(PhoneGatewayHandler):
        token = tok

    httpd = ThreadingHTTPServer((host, port), BoundHandler)
    set_phone_gateway_pid(os.getpid())
    print(
        f"[phone] listening on {host}:{port} (pid={os.getpid()})",
        flush=True,
    )
    for url in advertise_urls(port):
        print(f"[phone] {url}", flush=True)

    def _quit(_signum=None, _frame=None) -> None:
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    try:
        signal.signal(signal.SIGTERM, _quit)
        signal.signal(signal.SIGINT, _quit)
    except Exception:
        pass
    try:
        httpd.serve_forever(poll_interval=0.3)
    finally:
        try:
            httpd.server_close()
        except Exception:
            pass
        try:
            set_phone_gateway_pid(None)
        except Exception:
            pass
        print("[phone] gateway stopped", flush=True)


def main() -> None:
    serve()


if __name__ == "__main__":
    main()
