"""Tests for personal / app memory storage."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import memory as mem  # noqa: E402


class MemoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_save_read_personal_and_app(self) -> None:
        mem.save_memory("personal", "profile", "Name: Bharat", memory_dir=self.root)
        mem.save_memory("app", "hn", "username: demo", memory_dir=self.root)
        personal = mem.read_memory("personal", "profile", memory_dir=self.root)
        app = mem.read_memory("application", "hn", memory_dir=self.root)
        self.assertIn("Name: Bharat", personal)
        self.assertIn("username: demo", app)
        notes = mem.list_memories("all", memory_dir=self.root)
        self.assertEqual({n.rel for n in notes}, {"personal/profile.md", "app/hn.md"})

    def test_append_vs_replace(self) -> None:
        mem.save_memory("personal", "profile", "one", mode="replace", memory_dir=self.root)
        mem.save_memory("personal", "profile", "two", mode="append", memory_dir=self.root)
        text = mem.read_memory("personal", "profile", memory_dir=self.root)
        self.assertIn("one", text)
        self.assertIn("two", text)
        mem.save_memory("personal", "profile", "only", mode="replace", memory_dir=self.root)
        text = mem.read_memory("personal", "profile", memory_dir=self.root)
        self.assertIn("only", text)
        self.assertNotIn("two", text)

    def test_missing_and_bad_kind(self) -> None:
        with self.assertRaises(FileNotFoundError):
            mem.read_memory("personal", "nope", memory_dir=self.root)
        with self.assertRaises(ValueError):
            mem.save_memory("other", "x", "y", memory_dir=self.root)
        with self.assertRaises(ValueError):
            mem.sanitize_memory_name("***")
        self.assertEqual(mem.sanitize_memory_name("../etc"), "etc")

    def test_save_screen_utterance(self) -> None:
        self.assertTrue(mem.is_save_screen_utterance("Save the screen as memory"))
        self.assertTrue(mem.is_save_screen_utterance("remember this screenshot"))
        self.assertFalse(mem.is_save_screen_utterance("open notes"))

    def test_capture_and_save_screen(self) -> None:
        class _Resp:
            output_text = "# Pin diagram\n\nESP32 on the left, MPU6050 on the right."
            output = []

        class _Client:
            def __init__(self) -> None:
                self.responses = self

            def create(self, **_kwargs):
                return _Resp()

        with (
            patch.object(mem, "capture_screen_png", return_value=(b"\x89PNG", "draw.io")),
        ):
            status = mem.capture_and_save_screen(
                _Client(),
                name="pin-diagram",
                hint="ESP32 pinout",
                memory_dir=self.root,
            )
        self.assertIn("Saved screen memory", status)
        md = (self.root / "screens" / "pin-diagram.md").read_text(encoding="utf-8")
        png = self.root / "screens" / "pin-diagram.png"
        self.assertTrue(png.is_file())
        self.assertIn("ESP32", md)
        listed = mem.read_memory("screen", "pin-diagram", memory_dir=self.root)
        self.assertIn("Pin diagram", listed)

    def test_run_tool_roundtrip(self) -> None:
        with patch.object(mem, "MEMORY_DIR", self.root):
            out = mem.run_memory_tool(
                "save_memory",
                {"kind": "personal", "name": "profile", "text": "Hi", "mode": "append"},
            )
            self.assertIn("Saved", out)
            listed = mem.run_memory_tool("list_memories", {"kind": "all"})
            self.assertIn("personal/profile.md", listed)
            body = mem.run_memory_tool(
                "read_memory", {"kind": "personal", "name": "profile"}
            )
            self.assertIn("Hi", body)


if __name__ == "__main__":
    unittest.main()
