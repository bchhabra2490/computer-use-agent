"""Phone gateway: env switch, auth, command queue (no live network bind required)."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app_status as st  # noqa: E402
import phone_gateway as pg  # noqa: E402


class PhoneGatewayTokenTests(unittest.TestCase):
    def test_generated_token_is_five_chars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            token_path = Path(tmp) / "phone.token"
            with (
                patch.object(pg, "TOKEN_PATH", token_path),
                patch.object(pg, "RUNTIME_DIR", Path(tmp)),
                patch.dict("os.environ", {"PHONE_GATEWAY_TOKEN": ""}, clear=False),
            ):
                token = pg.load_or_create_token()
            self.assertEqual(len(token), 5)
            self.assertEqual(token_path.read_text(encoding="utf-8").strip(), token)

    def test_env_token_capped_at_five(self) -> None:
        with patch.dict("os.environ", {"PHONE_GATEWAY_TOKEN": "abcdefg"}):
            self.assertEqual(pg.load_or_create_token(), "abcde")

    def test_rewrites_legacy_long_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            token_path = Path(tmp) / "phone.token"
            token_path.write_text("this-is-a-very-long-token\n", encoding="utf-8")
            with (
                patch.object(pg, "TOKEN_PATH", token_path),
                patch.object(pg, "RUNTIME_DIR", Path(tmp)),
                patch.dict("os.environ", {"PHONE_GATEWAY_TOKEN": ""}, clear=False),
            ):
                token = pg.load_or_create_token()
            self.assertEqual(len(token), 5)
            self.assertEqual(token_path.read_text(encoding="utf-8").strip(), token)


class PhoneGatewayEnabledTests(unittest.TestCase):
    def test_off_values(self) -> None:
        with patch.dict("os.environ", {"PHONE_GATEWAY": "0"}):
            self.assertFalse(pg.phone_gateway_enabled())
        with patch.dict("os.environ", {"PHONE_GATEWAY": "false"}):
            self.assertFalse(pg.phone_gateway_enabled())
        with patch.dict("os.environ", {"PHONE_GATEWAY": "1"}):
            self.assertTrue(pg.phone_gateway_enabled())


class PhoneGatewayHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "status.json"
        self.patcher = patch.object(st, "STATUS_PATH", self.path)
        self.patcher.start()
        self.token = "test-token-abc"

    def tearDown(self) -> None:
        self.patcher.stop()
        self.tmp.cleanup()

    def _handler(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        token: str | None = None,
        *,
        raw_body: bytes | None = None,
        content_type: str | None = None,
    ):
        class FakeServer:
            pass

        if raw_body is not None:
            raw = raw_body
        elif body is not None:
            raw = json.dumps(body).encode("utf-8")
        else:
            raw = b""
        headers = {
            "Content-Length": str(len(raw)),
        }
        if content_type:
            headers["Content-Type"] = content_type
        elif body is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"

        class Handler(pg.PhoneGatewayHandler):
            def __init__(self):
                self.token = "test-token-abc"
                self.command = method
                self.path = path
                self.request_version = "HTTP/1.1"
                self.headers = headers  # type: ignore[assignment]
                self.rfile = io.BytesIO(raw)
                self.wfile = io.BytesIO()
                self._code = None
                self._out_headers: list[tuple[str, str]] = []

            def send_response(self, code, message=None):  # noqa: ARG002
                self._code = code

            def send_header(self, key, value):
                self._out_headers.append((key, value))

            def end_headers(self):
                pass

            def log_message(self, fmt, *args):  # noqa: ARG002
                return

        h = Handler()
        if method == "GET":
            h.do_GET()
        elif method == "POST":
            h.do_POST()
        return h

    def test_health_has_no_auth(self) -> None:
        h = self._handler("GET", "/v1/health")
        self.assertEqual(h._code, 200)

    def test_status_requires_token(self) -> None:
        h = self._handler("GET", "/v1/status")
        self.assertEqual(h._code, 401)

    def test_command_enqueues(self) -> None:
        h = self._handler(
            "POST",
            "/v1/command",
            {"text": "open notes"},
            token="test-token-abc",
        )
        self.assertEqual(h._code, 200)
        self.assertEqual(st.consume_utterance(), "open notes")

    def test_control_mark_done(self) -> None:
        h = self._handler(
            "POST",
            "/v1/control",
            {"action": "mark_done"},
            token="test-token-abc",
        )
        self.assertEqual(h._code, 200)
        self.assertTrue(st.mark_done_pending())

    def test_status_payload_shape(self) -> None:
        st.set_state("idle", "ready")
        payload = pg.phone_status_payload()
        self.assertEqual(payload["state"], "idle")
        self.assertIn("logs", payload)
        self.assertIn("agents", payload)
        self.assertIn("screen_at", payload)
        self.assertIn("last_llm", payload)
        self.assertIn("photo_at", payload)
        self.assertIn("speech_at", payload)
        self.assertIn("reply_sink", payload)

    def test_status_payload_includes_llm_log(self) -> None:
        st.log_llm("Here is a long assistant reply for the phone.", source="llm")
        payload = pg.phone_status_payload()
        self.assertEqual(
            payload["last_llm"],
            "Here is a long assistant reply for the phone.",
        )
        joined = "\n".join(payload["logs"])
        self.assertIn("[llm]", joined)
        self.assertIn("Here is a long assistant reply", joined)

    def test_screen_404_before_capture(self) -> None:
        screen = Path(self.tmp.name) / "phone-screen.jpg"
        with patch.object(st, "PHONE_SCREEN_PATH", screen):
            h = self._handler("GET", "/v1/screen", token="test-token-abc")
        self.assertEqual(h._code, 404)

    def test_screen_serves_agent_jpeg(self) -> None:
        from PIL import Image

        screen = Path(self.tmp.name) / "phone-screen.jpg"
        buf = io.BytesIO()
        Image.new("RGB", (64, 32), (12, 34, 56)).save(buf, format="PNG")
        with (
            patch.object(st, "PHONE_SCREEN_PATH", screen),
            patch.object(st, "RUNTIME_DIR", Path(self.tmp.name)),
        ):
            self.assertTrue(st.write_phone_screen(buf.getvalue()))
            h = self._handler("GET", "/v1/screen", token="test-token-abc")
        self.assertEqual(h._code, 200)
        body = h.wfile.getvalue()
        self.assertTrue(body.startswith(b"\xff\xd8"))
        self.assertTrue(st.read_status().get("screen_at"))

    def test_speech_404_before_publish(self) -> None:
        speech = Path(self.tmp.name) / "phone-tts.wav"
        with patch.object(st, "PHONE_SPEECH_PATH", speech):
            h = self._handler("GET", "/v1/speech", token="test-token-abc")
        self.assertEqual(h._code, 404)

    def test_speech_serves_wav(self) -> None:
        speech = Path(self.tmp.name) / "phone-tts.wav"
        wav = b"RIFF" + b"xxxx" + b"WAVE" + b"\x00" * 16
        with patch.object(st, "PHONE_SPEECH_PATH", speech):
            st.write_phone_speech(wav)
            h = self._handler("GET", "/v1/speech", token="test-token-abc")
        self.assertEqual(h._code, 200)
        self.assertEqual(h.wfile.getvalue(), wav)
        self.assertTrue(st.read_status().get("speech_at"))
        self.assertIn(
            ("Content-Type", "audio/wav"),
            h._out_headers,
        )


    def test_encode_downscales_for_phone(self) -> None:
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (2000, 1000), (1, 2, 3)).save(buf, format="PNG")
        with patch.object(st, "PHONE_SCREEN_MAX_WIDTH", 1080):
            jpeg, width, height = st._encode_phone_jpeg(buf.getvalue())
        self.assertEqual(width, 1080)
        self.assertEqual(height, 540)
        self.assertTrue(jpeg.startswith(b"\xff\xd8"))

    def test_post_audio_json(self) -> None:
        wav = b"RIFF" + b"xxxx" + b"WAVE"
        with patch("stt.transcribe", return_value="skip ads"):
            h = self._handler(
                "POST",
                "/v1/audio",
                {
                    "audio": __import__("base64").b64encode(wav).decode("ascii"),
                    "mime": "audio/wav",
                },
                token="test-token-abc",
            )
        self.assertEqual(h._code, 200)
        self.assertEqual(st.consume_utterance(), "skip ads")

    def test_post_photo_jpeg(self) -> None:
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (32, 24), (9, 8, 7)).save(buf, format="JPEG", quality=80)
        jpeg = buf.getvalue()
        photo_path = Path(self.tmp.name) / "phone-photo.jpg"
        with (
            patch.object(st, "PHONE_PHOTO_PATH", photo_path),
            patch.object(st, "RUNTIME_DIR", Path(self.tmp.name)),
        ):
            h = self._handler(
                "POST",
                "/v1/photo",
                token="test-token-abc",
                raw_body=jpeg,
                content_type="image/jpeg",
            )
        self.assertEqual(h._code, 200)
        body = json.loads(h.wfile.getvalue().decode("utf-8"))
        self.assertTrue(body["ok"])
        self.assertEqual(body["source"], "photo")
        self.assertEqual(st.consume_utterance(), pg.DEFAULT_PHOTO_PROMPT)
        self.assertTrue(photo_path.is_file())
        self.assertTrue(st.read_status().get("phone_photo_at"))


class PhoneAudioIngestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "status.json"
        self.patcher = patch.object(st, "STATUS_PATH", self.path)
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()
        self.tmp.cleanup()

    def test_text_override_skips_stt(self) -> None:
        with patch("stt.transcribe") as transcribe:
            result = pg.ingest_phone_audio(b"not-audio", text="open notes")
        transcribe.assert_not_called()
        self.assertEqual(result["text"], "open notes")
        self.assertEqual(result["source"], "text")
        self.assertEqual(st.consume_utterance(), "open notes")

    def test_transcribes_and_enqueues(self) -> None:
        wav = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 20
        with patch("stt.transcribe", return_value="  play lag ja gale  "):
            result = pg.ingest_phone_audio(wav, content_type="audio/wav")
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "audio")
        self.assertEqual(result["text"], "play lag ja gale")
        self.assertEqual(st.consume_utterance(), "play lag ja gale")

    def test_rejects_empty_audio(self) -> None:
        result = pg.ingest_phone_audio(b"")
        self.assertFalse(result["ok"])

    def test_wav_passthrough(self) -> None:
        wav = b"RIFF" + b"xxxx" + b"WAVE" + b"data"
        self.assertIs(pg.audio_to_wav(wav), wav)

    def test_json_body_roundtrip(self) -> None:
        wav = b"RIFF" + b"xxxx" + b"WAVE"
        parsed = pg.parse_audio_body(
            json.dumps({"audio": __import__("base64").b64encode(wav).decode(), "mime": "audio/wav"}).encode(),
            content_type="application/json",
        )
        self.assertEqual(parsed["audio"], wav)


class PhonePhotoIngestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.path = root / "status.json"
        self.photo = root / "phone-photo.jpg"
        self.patches = [
            patch.object(st, "STATUS_PATH", self.path),
            patch.object(st, "PHONE_PHOTO_PATH", self.photo),
            patch.object(st, "RUNTIME_DIR", root),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self) -> None:
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def _jpeg(self, size: tuple[int, int] = (40, 30)) -> bytes:
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", size, (20, 40, 60)).save(buf, format="JPEG", quality=80)
        return buf.getvalue()

    def test_ingest_stores_and_queues(self) -> None:
        result = pg.ingest_phone_photo(self._jpeg(), text="what is this label?")
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "photo")
        self.assertEqual(result["text"], "what is this label?")
        self.assertEqual(st.consume_utterance(), "what is this label?")
        self.assertTrue(self.photo.is_file())
        self.assertTrue(st.phone_photo_pending())
        jpeg = st.phone_photo_jpeg(consume_pending=True)
        self.assertTrue(jpeg and jpeg.startswith(b"\xff\xd8"))
        self.assertFalse(st.phone_photo_pending())

    def test_default_prompt_when_no_text(self) -> None:
        result = pg.ingest_phone_photo(self._jpeg())
        self.assertEqual(result["text"], pg.DEFAULT_PHOTO_PROMPT)
        self.assertEqual(result["caption_source"], "default")

    def test_rejects_empty(self) -> None:
        result = pg.ingest_phone_photo(b"")
        self.assertFalse(result["ok"])

    def test_rejects_too_large(self) -> None:
        with patch.object(pg, "PHOTO_MAX_BYTES", 10):
            result = pg.ingest_phone_photo(self._jpeg())
        self.assertFalse(result["ok"])
        self.assertIn("too large", result["error"])

    def test_png_converts_to_jpeg(self) -> None:
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (80, 40), (1, 2, 3)).save(buf, format="PNG")
        jpeg, width, height = pg.photo_to_jpeg(buf.getvalue(), content_type="image/png")
        self.assertTrue(jpeg.startswith(b"\xff\xd8"))
        self.assertEqual(width, 80)
        self.assertEqual(height, 40)

    def test_json_body_roundtrip(self) -> None:
        raw = self._jpeg()
        parsed = pg.parse_photo_body(
            json.dumps(
                {
                    "photo": __import__("base64").b64encode(raw).decode(),
                    "mime": "image/jpeg",
                    "text": "read this",
                }
            ).encode(),
            content_type="application/json",
        )
        self.assertEqual(parsed["text"], "read this")
        self.assertTrue(parsed["photo"].startswith(b"\xff\xd8"))
        self.assertEqual(parsed["audio"], b"")

    def test_audio_caption_is_transcribed(self) -> None:
        wav = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 20
        with patch("stt.transcribe", return_value="  what does this label say  "):
            result = pg.ingest_phone_photo(
                self._jpeg(),
                audio=wav,
                audio_content_type="audio/wav",
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["caption_source"], "audio")
        self.assertEqual(result["text"], "what does this label say")
        self.assertEqual(st.consume_utterance(), "what does this label say")

    def test_text_caption_skips_photo_audio_stt(self) -> None:
        with patch("stt.transcribe") as transcribe:
            result = pg.ingest_phone_photo(
                self._jpeg(),
                text="read the ingredients",
                audio=b"not-audio",
            )
        transcribe.assert_not_called()
        self.assertEqual(result["caption_source"], "text")
        self.assertEqual(result["text"], "read the ingredients")

    def test_audio_stt_failure_does_not_queue(self) -> None:
        with patch("stt.transcribe", return_value="   "):
            result = pg.ingest_phone_photo(
                self._jpeg(),
                audio=b"RIFF" + b"xxxx" + b"WAVE",
                audio_content_type="audio/wav",
            )
        self.assertFalse(result["ok"])
        self.assertIsNone(st.consume_utterance())
        self.assertFalse(self.photo.is_file())

    def test_json_includes_audio(self) -> None:
        raw = self._jpeg()
        wav = b"RIFF" + b"xxxx" + b"WAVE"
        parsed = pg.parse_photo_body(
            json.dumps(
                {
                    "photo": __import__("base64").b64encode(raw).decode(),
                    "mime": "image/jpeg",
                    "audio": __import__("base64").b64encode(wav).decode(),
                    "audio_mime": "audio/wav",
                }
            ).encode(),
            content_type="application/json",
        )
        self.assertEqual(parsed["audio"], wav)
        self.assertEqual(parsed["audio_content_type"], "audio/wav")


class EnsureGatewayTests(unittest.TestCase):
    def test_disabled_does_not_spawn(self) -> None:
        with patch.dict("os.environ", {"PHONE_GATEWAY": "0"}):
            with patch("phone_gateway.subprocess.Popen") as popen:
                self.assertIsNone(pg.ensure_phone_gateway())
                popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
