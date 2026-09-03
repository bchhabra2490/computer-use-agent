"""Tests for personal / app memory storage."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
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
        self._condense = patch.dict("os.environ", {"MEMORY_CONDENSE": "0"})
        self._condense.start()

    def tearDown(self) -> None:
        self._condense.stop()
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
        self.assertEqual(mem.sanitize_memory_name("raspberry-pi-3b.md"), "raspberry-pi-3b")
        self.assertEqual(
            mem.sanitize_memory_name("personal/raspberry-pi-3b.md"),
            "raspberry-pi-3b",
        )

    def test_personal_always_single_profile(self) -> None:
        mem.save_memory(
            "personal", "multimeter", "Fluke 117", memory_dir=self.root, condense=False
        )
        mem.save_memory(
            "personal", "contacts", "Mom on WhatsApp", memory_dir=self.root, condense=False
        )
        notes = mem.list_memories("personal", memory_dir=self.root)
        self.assertEqual([n.name for n in notes], ["profile"])
        self.assertTrue((self.root / "personal" / "profile.md").is_file())
        self.assertFalse((self.root / "personal" / "multimeter.md").exists())
        text = mem.read_memory("personal", "multimeter", memory_dir=self.root)
        self.assertIn("Fluke 117", text)
        self.assertIn("**multimeter:**", text)
        self.assertIn("**contacts:**", text)
        self.assertIn("Mom on WhatsApp", text)

    def test_merge_legacy_personal_files(self) -> None:
        personal = self.root / "personal"
        personal.mkdir(parents=True)
        (personal / "profile.md").write_text(
            "# personal / profile\n\n- Name: Bharat\n", encoding="utf-8"
        )
        (personal / "multimeter.md").write_text(
            "# personal / multimeter\n\n- Fluke 117\n", encoding="utf-8"
        )
        (personal / "raspberry-pi-3b.md").write_text(
            "- Lives on the shelf\n", encoding="utf-8"
        )
        path = mem.merge_legacy_personal_files(memory_dir=self.root)
        self.assertIsNotNone(path)
        self.assertFalse((personal / "multimeter.md").exists())
        self.assertFalse((personal / "raspberry-pi-3b.md").exists())
        body = (personal / "profile.md").read_text(encoding="utf-8")
        self.assertIn("Name: Bharat", body)
        self.assertIn("Fluke 117", body)
        self.assertIn("## raspberry-pi-3b", body)
        self.assertNotIn("Migrated from", body)
        notes = mem.list_memories("personal", memory_dir=self.root)
        self.assertEqual([n.name for n in notes], ["profile"])

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

    def test_search_memories_ranks_relevant_sections(self) -> None:
        mem.save_memory(
            "personal", "hardware", "My multimeter is a Fluke 117.",
            memory_dir=self.root, condense=False,
        )
        mem.save_memory(
            "app", "youtube", "Prefer ambient music playlists.",
            memory_dir=self.root, condense=False,
        )
        hits = mem.search_memories("which multimeter do I own", memory_dir=self.root)
        self.assertTrue(hits)
        self.assertEqual(hits[0].note.rel, "personal/profile.md")
        self.assertIn("Fluke 117", hits[0].text)

    def test_search_tool_does_not_require_filename(self) -> None:
        mem.save_memory(
            "app", "github", "Repository owner is bchhabra2490.",
            memory_dir=self.root, condense=False,
        )
        with patch.object(mem, "MEMORY_DIR", self.root):
            out = mem.run_memory_tool(
                "search_memories",
                {"query": "repository owner", "kind": "all", "limit": 3},
            )
        self.assertIn("app/github.md", out)
        self.assertIn("bchhabra2490", out)

    def test_relevant_memory_context_falls_back_to_catalog(self) -> None:
        mem.save_memory(
            "app", "maps", "Home is Wentworth Avenue.",
            memory_dir=self.root, condense=False,
        )
        relevant = mem.format_relevant_memories("navigate home", memory_dir=self.root)
        self.assertIn("app/maps.md", relevant)
        fallback = mem.format_relevant_memories("quantum zebras", memory_dir=self.root)
        self.assertIn("Saved memories", fallback)


class TurnTraceTests(unittest.TestCase):
    def test_as_text_includes_user_and_steps(self) -> None:
        turn = mem.TurnTrace("How many stars on my computer-use agent?")
        turn.add("llm_tool_call", "mcp_call search_repositories")
        turn.add("tool_result", "bchhabra2490/computer-use-agent stars=0")
        turn.add("spoken", "It currently has 0 stars.")
        blob = turn.as_text()
        self.assertIn("How many stars", blob)
        self.assertIn("llm_tool_call", blob)
        self.assertIn("stars=0", blob)
        self.assertIn("0 stars", blob)

    def test_truncates_long_step(self) -> None:
        turn = mem.TurnTrace("x")
        turn.add("tool_result", "n" * 50, max_len=10)
        self.assertIn("truncated", turn.as_text())


class ExtractMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._condense = patch.dict("os.environ", {"MEMORY_CONDENSE": "0"})
        self._condense.start()

    def tearDown(self) -> None:
        self._condense.stop()
        self.tmp.cleanup()

    def test_parse_items_and_skip_secrets(self) -> None:
        payload = {
            "items": [
                {
                    "kind": "app",
                    "name": "github",
                    "text": "- Owns bchhabra2490/computer-use-agent (0 stars)",
                },
                {
                    "kind": "app",
                    "name": "github",
                    "text": "token: ghp_abcdefghijklmnopqrstuvwxyz",
                },
                {"kind": "screen", "name": "x", "text": "nope"},
            ]
        }
        items = mem.parse_extracted_memory_items(payload)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "github")

    def test_parse_items_skips_volatile_hardware_telemetry(self) -> None:
        payload = {
            "items": [
                {
                    "kind": "app",
                    "name": "home-hardware",
                    "text": (
                        'Memory snapshot: Node "office" — online: false; '
                        "component lamp; last ping 2026-08-18T08:57:58.552Z."
                    ),
                },
                {
                    "kind": "app",
                    "name": "home-hardware",
                    "text": "- Office lamp is controlled by relay component `lamp`.",
                },
            ]
        }
        items = mem.parse_extracted_memory_items(payload)
        self.assertEqual(len(items), 1)
        self.assertIn("relay component", items[0]["text"])

    def test_apply_writes_app_memory(self) -> None:
        written = mem.apply_extracted_memory_items(
            [
                {
                    "kind": "app",
                    "name": "youtube",
                    "text": "- Played Highway to Hell by AC/DC",
                }
            ],
            memory_dir=self.root,
        )
        self.assertEqual(written, ["apps/youtube.md"])
        body = mem.read_memory("app", "youtube", memory_dir=self.root)
        self.assertIn("Highway to Hell", body)

    def test_extract_from_run_transcript(self) -> None:
        class _Resp:
            output_text = json.dumps(
                {
                    "items": [
                        {
                            "kind": "app",
                            "name": "github",
                            "text": "- Repo bchhabra2490/computer-use-agent has 0 stars",
                            "reason": "user asked about their repo",
                        }
                    ]
                }
            )
            output = []

        class _Client:
            def __init__(self) -> None:
                self.responses = self
                self.prompts: list[str] = []

            def create(self, **kwargs):
                self.prompts.append(str(kwargs.get("input") or ""))
                return _Resp()

        client = _Client()
        transcript = (
            "User input:\nFind stars on the computer usage agent I own\n\n"
            "Step 1 [llm_tool_call]:\nmcp_call get_me / search_repositories\n\n"
            "Step 2 [tool_result]:\nbchhabra2490/computer-use-agent stargazers_count=0\n\n"
            "Step 3 [spoken]:\nYour computer-use agent repo has 0 stars."
        )
        written = mem.maybe_extract_run_memories(
            client,
            user_input="Find stars on the computer usage agent I own",
            transcript=transcript,
            memory_dir=self.root,
            background=False,
        )
        self.assertEqual(written, ["apps/github.md"])
        self.assertTrue(any("stargazers_count=0" in p for p in client.prompts))
        body = mem.read_memory("app", "github", memory_dir=self.root)
        self.assertIn("computer-use-agent", body)

    def test_extract_disabled(self) -> None:
        class _Client:
            def __init__(self) -> None:
                self.responses = self
                self.called = False

            def create(self, **_kwargs):
                self.called = True
                raise AssertionError("should not call the model")

        with patch.dict("os.environ", {"MEMORY_EXTRACT": "0"}):
            written = mem.maybe_extract_run_memories(
                _Client(),
                user_input="play a song",
                transcript="played Thunderstruck",
                memory_dir=self.root,
            )
        self.assertEqual(written, [])

    def test_background_does_not_block(self) -> None:
        started = threading.Event()
        release = threading.Event()

        def slow_impl(*_args, **_kwargs):
            started.set()
            release.wait(timeout=2)
            return ["apps/youtube.md"]

        with (
            patch.object(mem, "_extract_run_memories_impl", side_effect=slow_impl),
            patch.object(mem, "_new_extract_client", return_value=object()),
        ):
            t0 = time.monotonic()
            written = mem.maybe_extract_run_memories(
                user_input="play a song",
                transcript="played Thunderstruck",
                memory_dir=self.root,
            )
            elapsed = time.monotonic() - t0
            self.assertEqual(written, [])
            self.assertLess(elapsed, 0.5)
            self.assertTrue(started.wait(timeout=1.0))
            release.set()


class CondenseMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        mem._condense_running = False
        mem._condense_pending = False
        mem._condense_force_kinds.clear()
        self._env = patch.dict("os.environ", {"MEMORY_CONDENSE": "1"})
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        mem._condense_running = False
        mem._condense_pending = False
        mem._condense_force_kinds.clear()
        self.tmp.cleanup()

    def test_needs_condense_on_stacked_sections(self) -> None:
        mem.save_memory(
            "app", "youtube", "Played A", memory_dir=self.root, condense=False
        )
        notes = mem.list_memories("app", memory_dir=self.root)
        self.assertFalse(mem.notes_need_condense(notes))
        mem.save_memory(
            "app", "youtube", "Played A again", memory_dir=self.root, condense=False
        )
        notes = mem.list_memories("app", memory_dir=self.root)
        self.assertTrue(mem.notes_need_condense(notes))

    def test_force_personal_condense_after_single_write(self) -> None:
        mem.save_memory(
            "personal",
            "profile",
            "- Prefers dark mode",
            memory_dir=self.root,
            condense=False,
        )
        notes = mem.list_memories("personal", memory_dir=self.root)
        self.assertFalse(mem.notes_need_condense(notes))
        self.assertTrue(
            mem.notes_need_condense(notes, force_kinds=frozenset({"personal"}))
        )

        class _Resp:
            output_text = json.dumps(
                {
                    "files": [
                        {
                            "kind": "personal",
                            "name": "profile",
                            "text": "# personal / profile\n\n- Prefers dark mode",
                        }
                    ]
                }
            )
            output = []

        class _Client:
            def __init__(self) -> None:
                self.responses = self

            def create(self, **_kwargs):
                return _Resp()

        written = mem._condense_memories_impl(
            _Client(),
            memory_dir=self.root,
            force_kinds=frozenset({"personal"}),
        )
        self.assertEqual(written, ["personal/profile.md"])
        body = mem.read_memory("personal", memory_dir=self.root)
        self.assertIn("Prefers dark mode", body)
        self.assertEqual(mem._dated_heading_count(body), 0)

    def test_parse_and_write_compact_file(self) -> None:
        mem.save_memory(
            "app", "youtube", "Played A", memory_dir=self.root, condense=False
        )
        mem.save_memory(
            "app", "youtube", "Played A", memory_dir=self.root, condense=False
        )
        payload = {
            "files": [
                {
                    "kind": "app",
                    "name": "youtube",
                    "text": "# app / youtube\n\n- Played A",
                    "reason": "duplicate play lines",
                }
            ]
        }
        files = mem.parse_condensed_memory_files(payload)
        written = mem.apply_condensed_memory_files(files, memory_dir=self.root)
        self.assertEqual(written, ["apps/youtube.md"])
        body = mem.read_memory("app", "youtube", memory_dir=self.root)
        self.assertIn("Played A", body)
        self.assertEqual(mem._dated_heading_count(body), 0)

    def test_impl_rewrites_duplicates(self) -> None:
        mem.save_memory(
            "personal",
            "profile",
            "- Prefers volume 40%",
            memory_dir=self.root,
            condense=False,
        )
        mem.save_memory(
            "personal",
            "profile",
            "- Prefers volume 50%",
            memory_dir=self.root,
            condense=False,
        )

        class _Resp:
            output_text = json.dumps(
                {
                    "files": [
                        {
                            "kind": "personal",
                            "name": "profile",
                            "text": "# personal / profile\n\n- Prefers volume 50%",
                        }
                    ]
                }
            )
            output = []

        class _Client:
            def __init__(self) -> None:
                self.responses = self

            def create(self, **_kwargs):
                return _Resp()

        written = mem._condense_memories_impl(_Client(), memory_dir=self.root)
        self.assertEqual(written, ["personal/profile.md"])
        body = mem.read_memory("personal", "profile", memory_dir=self.root)
        self.assertIn("50%", body)
        self.assertNotIn("40%", body)
        self.assertEqual(body.count("Prefers volume"), 1)

    def test_schedule_does_not_block(self) -> None:
        started = threading.Event()
        release = threading.Event()

        def slow_impl(*_args, **_kwargs):
            started.set()
            release.wait(timeout=2)
            return []

        with (
            patch.object(mem, "_condense_memories_impl", side_effect=slow_impl),
            patch.object(mem, "_new_extract_client", return_value=object()),
        ):
            t0 = time.monotonic()
            mem.schedule_memory_condense(memory_dir=self.root)
            elapsed = time.monotonic() - t0
            self.assertLess(elapsed, 0.5)
            self.assertTrue(started.wait(timeout=1.0))
            release.set()

    def test_disabled(self) -> None:
        with patch.dict("os.environ", {"MEMORY_CONDENSE": "0"}):
            with patch.object(mem, "_condense_worker") as worker:
                mem.schedule_memory_condense(memory_dir=self.root)
                worker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
