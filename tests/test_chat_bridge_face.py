"""Chat bridge face overlay helpers."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import chat_bridge as cb  # noqa: E402


class FacePayloadTests(unittest.TestCase):
    def test_update_face_toggles_and_sets_preset(self) -> None:
        status = {"ok": True, "enabled": True, "presets": [], "current": {"id": "sun"}}
        with (
            patch("face_overlay.face_overlay_env_enabled", return_value=True),
            patch("app_status.set_face_overlay_enabled") as set_enabled,
            patch("face_overlay.set_blobatar", return_value=SimpleNamespace(id="sun")) as set_blob,
            patch.object(cb, "face_status_payload", return_value=status) as payload,
        ):
            out = cb.update_face_payload({"enabled": False, "preset": "sun"})
            set_enabled.assert_called_once_with(False)
            set_blob.assert_called_once_with("sun")
            payload.assert_called()
            self.assertEqual(out["current"]["id"], "sun")

    def test_update_face_rejects_empty_preset(self) -> None:
        with self.assertRaises(ValueError):
            cb.update_face_payload({"preset": "  "})

    def test_update_face_blocks_enable_when_env_off(self) -> None:
        with (
            patch("face_overlay.face_overlay_env_enabled", return_value=False),
            patch("app_status.set_face_overlay_enabled") as set_enabled,
        ):
            with self.assertRaises(ValueError):
                cb.update_face_payload({"enabled": True})
            set_enabled.assert_not_called()

    def test_face_status_payload_lists_presets(self) -> None:
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
        ns_app = MagicMock()
        fake_appkit = SimpleNamespace(NSApplication=ns_app)
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(sys.modules, {"AppKit": fake_appkit}),
            patch(
                "app_status.read_status",
                return_value={"face_overlay_enabled": True, "face_preset": "droplet"},
            ),
            patch("face_overlay.PRESET_PATH", Path(tmp) / "face_preset"),
            patch("face_overlay.blobatar_png_bytes", return_value=fake_png),
            patch("face_overlay.face_overlay_env_enabled", return_value=True),
        ):
            out = cb.face_status_payload()
            self.assertTrue(out["ok"])
            self.assertTrue(out["enabled"])
            self.assertEqual(out["current"]["id"], "droplet")
            ids = [p["id"] for p in out["presets"]]
            self.assertEqual(ids[:4], ["pebble", "droplet", "cloud", "sun"])
            self.assertTrue(any(p["id"] == "droplet" and p["selected"] for p in out["presets"]))
            self.assertTrue(out["preview_b64"])
            ns_app.sharedApplication.assert_called()


if __name__ == "__main__":
    unittest.main()
