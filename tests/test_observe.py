"""Tests for the passive observer (session flush, drafts, accept)."""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import observe  # noqa: E402
from observe import Focus, Observer, SessionBuffer, WindowBuffer  # noqa: E402


class ExcludeAppTests(unittest.TestCase):
    def test_password_managers_are_excluded(self) -> None:
        self.assertTrue(observe.exclude_app("1Password"))
        self.assertTrue(observe.exclude_app("Bitwarden"))
        self.assertTrue(observe.exclude_app("Keychain Access"))
        self.assertFalse(observe.exclude_app("Google Chrome"))


class SessionBufferTests(unittest.TestCase):
    def test_rotate_when_app_or_url_changes(self) -> None:
        buf = SessionBuffer()
        chrome = Focus("Google Chrome", "HN", "https://news.ycombinator.com")
        buf.note("click", chrome, now=1.0)
        self.assertFalse(buf.should_rotate(chrome))
        other = Focus("Safari", "HN", "https://news.ycombinator.com")
        self.assertTrue(buf.should_rotate(other))
        url = Focus("Google Chrome", "HN", "https://example.com")
        self.assertTrue(buf.should_rotate(url))

    def test_idle_seconds_from_last_event(self) -> None:
        buf = SessionBuffer()
        self.assertEqual(buf.idle_seconds(now=10.0), 0.0)
        buf.note("click", Focus("Chrome", "A", ""), now=5.0)
        self.assertEqual(buf.idle_seconds(now=8.0), 3.0)

    def test_scroll_debounce_collapses_burst(self) -> None:
        buf = SessionBuffer()
        focus = Focus("Chrome", "Doc", "")
        with patch.object(observe, "SCROLL_DEBOUNCE", 0.25):
            buf.note("scroll", focus, now=1.0)
            buf.note("scroll", focus, now=1.1)
            buf.note("scroll", focus, now=1.4)
        self.assertEqual([e["kind"] for e in buf.events], ["scroll", "scroll"])

    def test_take_clears_events(self) -> None:
        buf = SessionBuffer()
        buf.note("click", Focus("Chrome", "A", ""), now=1.0)
        payload = buf.take()
        self.assertIsNotNone(payload)
        self.assertEqual(len(payload["events"]), 1)
        self.assertIsNone(buf.take())


class WindowBufferTests(unittest.TestCase):
    def test_age_starts_on_first_segment(self) -> None:
        buf = WindowBuffer()
        self.assertEqual(buf.age(now=100.0), 0.0)
        buf.add({"started_at": 10.0, "events": [{"kind": "click"}]})
        self.assertEqual(buf.age(now=610.0), 600.0)

    def test_take_clears_window(self) -> None:
        buf = WindowBuffer()
        buf.add({"started_at": 1.0, "events": []}, png=b"png")
        payload = buf.take()
        self.assertEqual(len(payload["segments"]), 1)
        self.assertEqual(payload["pngs"], [b"png"])
        self.assertTrue(buf.empty())
        self.assertIsNone(buf.take())


class ParseExtractTests(unittest.TestCase):
    def test_keeps_durable_memory_and_skill(self) -> None:
        memories, skills = observe.parse_observe_extract(
            {
                "memories": [
                    {"kind": "app", "name": "chrome", "text": "Uses Chrome for HN"},
                    {"kind": "app", "name": "hw", "text": "device online: true last ping 2s"},
                ],
                "skills": [
                    {
                        "name": "Open HN",
                        "description": "Jump to Hacker News",
                        "body": "## Steps\n1. Cmd+L\n2. Type news.ycombinator.com\n3. Enter",
                    },
                    {
                        "name": "click-coords",
                        "description": "Bad playbook",
                        "body": "Click 412, 880 then 200, 40",
                    },
                ],
            }
        )
        self.assertEqual([m["name"] for m in memories], ["chrome"])
        self.assertEqual([s["name"] for s in skills], ["open-hn"])

    def test_empty_payload(self) -> None:
        memories, skills = observe.parse_observe_extract({"memories": [], "skills": []})
        self.assertEqual(memories, [])
        self.assertEqual(skills, [])


class ObserverFlushTests(unittest.TestCase):
    def setUp(self) -> None:
        self.obs = Observer()
        self.obs._take_screenshot = lambda app="": (None, None)
        self.flushed: list[tuple[dict, str]] = []
        self.obs._schedule_persist = lambda payload, reason: self.flushed.append(
            (payload, reason)
        )
        self._log = patch("observe._append_events_log")
        self._log.start()

    def tearDown(self) -> None:
        self._log.stop()

    def test_focus_change_buffers_without_drafting(self) -> None:
        with patch.object(observe, "computer_use_active", return_value=False):
            self.obs._focus = lambda: Focus("Google Chrome", "A", "https://a.example")
            self.obs.handle_input("click")
            self.obs._focus = lambda: Focus("Safari", "B", "https://b.example")
            self.obs.handle_input("click")
        self.assertEqual(self.flushed, [])
        self.assertEqual(len(self.obs._window.segments), 1)
        self.assertEqual(self.obs._window.segments[0]["focus"]["app"], "Google Chrome")
        self.assertEqual(len(self.obs._session.events), 1)
        self.assertEqual(self.obs._session.focus.app, "Safari")

    def test_idle_buffers_screenshot_session_without_drafting(self) -> None:
        with (
            patch.object(observe, "computer_use_active", return_value=False),
            patch.object(observe, "IDLE_SECONDS", 3.0),
        ):
            self.obs._focus = lambda: Focus("Code", "observe.py", "")
            self.obs.handle_input("click")
            self.obs._session.last_event_at = time.monotonic() - 3.1
            self.obs.tick_idle()
        self.assertEqual(self.flushed, [])
        self.assertFalse(self.obs._session.events)
        self.assertEqual(len(self.obs._window.segments), 1)
        self.assertEqual(self.obs._window.segments[0]["reason"], "idle")

    def test_pauses_computer_use_without_drafting(self) -> None:
        with patch.object(observe, "computer_use_active", return_value=False):
            self.obs._focus = lambda: Focus("Finder", "Desktop", "")
            self.obs.handle_input("click")
        with patch.object(observe, "computer_use_active", return_value=True):
            self.obs.handle_input("click")
            self.obs.handle_input("scroll")
        self.assertEqual(self.flushed, [])
        self.assertFalse(self.obs._session.events)
        self.assertEqual(self.obs._window.segments[0]["reason"], "computer-use")

    def test_excluded_app_does_not_start_a_session(self) -> None:
        with patch.object(observe, "computer_use_active", return_value=False):
            self.obs._focus = lambda: Focus("1Password", "All Items", "")
            self.obs.handle_input("click")
        self.assertFalse(self.obs._session.events)
        self.assertTrue(self.obs._window.empty())
        self.assertEqual(self.flushed, [])

    def test_leaving_an_app_for_1password_buffers_the_prior_session(self) -> None:
        with patch.object(observe, "computer_use_active", return_value=False):
            self.obs._focus = lambda: Focus("Safari", "Mail", "https://mail.example")
            self.obs.handle_input("click")
            self.obs._focus = lambda: Focus("1Password", "All Items", "")
            self.obs.handle_input("click")
        self.assertEqual(self.flushed, [])
        self.assertFalse(self.obs._session.events)
        self.assertEqual(self.obs._window.segments[0]["focus"]["app"], "Safari")

    def test_no_draft_before_ten_minutes(self) -> None:
        with patch.object(observe, "computer_use_active", return_value=False):
            self.obs._focus = lambda: Focus("Code", "observe.py", "")
            self.obs.handle_input("click")
            self.obs._window.started_at = time.monotonic() - 60
            self.obs.tick_idle()
        self.assertEqual(self.flushed, [])

    def test_drafts_after_ten_minutes(self) -> None:
        with (
            patch.object(observe, "computer_use_active", return_value=False),
            patch.object(observe, "DRAFT_SECONDS", 600.0),
        ):
            self.obs._focus = lambda: Focus("Code", "observe.py", "")
            self.obs.handle_input("click")
            self.obs._window.started_at = time.monotonic() - 601
            self.obs.tick_idle()
        self.assertEqual(len(self.flushed), 1)
        payload, reason = self.flushed[0]
        self.assertEqual(reason, "window")
        self.assertEqual(len(payload["segments"]), 1)
        self.assertTrue(self.obs._window.empty())
        self.assertFalse(self.obs._session.events)

    def test_stop_before_ten_minutes_does_not_draft(self) -> None:
        with patch.object(observe, "computer_use_active", return_value=False):
            self.obs._focus = lambda: Focus("Code", "observe.py", "")
            self.obs.handle_input("click")
            self.obs.stop()
        self.assertEqual(self.flushed, [])
        self.assertEqual(self.obs._window.segments[0]["reason"], "shutdown")


class DraftAcceptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._condense = patch.dict("os.environ", {"MEMORY_CONDENSE": "0"})
        self._condense.start()

    def tearDown(self) -> None:
        self._condense.stop()
        self.tmp.cleanup()

    def _write_draft(self, name: str, **draft: object) -> Path:
        folder = self.root / "proposed" / name
        folder.mkdir(parents=True)
        payload = {
            "id": name,
            "status": "proposed",
            "focus": {"app": "Google Chrome", "title": "HN", "url": ""},
            "memories": [],
            "skills": [],
            **draft,
        }
        (folder / "draft.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")
        return folder

    def test_list_skips_empty_drafts(self) -> None:
        self._write_draft("empty_chrome")
        keep = self._write_draft(
            "keep_chrome",
            memories=[{"kind": "app", "name": "chrome", "text": "HN in Chrome"}],
        )
        listed = observe.list_proposed(root=self.root / "proposed")
        self.assertEqual(listed, [keep])

    def test_accept_writes_memory_and_skill(self) -> None:
        folder = self._write_draft(
            "20260101T000000Z_chrome",
            memories=[{"kind": "app", "name": "chrome", "text": "Uses Chrome for HN"}],
            skills=[
                {
                    "name": "open-hn",
                    "description": "Jump to Hacker News",
                    "body": "## Steps\n1. Cmd+L\n2. Type news.ycombinator.com\n3. Enter",
                }
            ],
        )
        memory_dir = self.root / "memory"
        skills_dir = self.root / "skills"
        accepted = self.root / "accepted"
        written = observe.accept_draft(
            folder,
            memory_dir=memory_dir,
            skills_dir=skills_dir,
            dest_root=accepted,
        )
        self.assertTrue(any("chrome.md" in line for line in written))
        self.assertTrue((memory_dir / "apps" / "chrome.md").is_file())
        self.assertIn("Uses Chrome for HN", (memory_dir / "apps" / "chrome.md").read_text())
        self.assertTrue((skills_dir / "open-hn" / "SKILL.md").is_file())
        self.assertFalse(folder.exists())
        self.assertTrue((accepted / "20260101T000000Z_chrome" / "draft.json").is_file())

    def test_accept_skips_existing_skill(self) -> None:
        from skills import write_skill

        skills_dir = self.root / "skills"
        write_skill("open-hn", "already there", "## Steps\n1. Existing", skills_dir=skills_dir)
        folder = self._write_draft(
            "dup_skill",
            skills=[
                {
                    "name": "open-hn",
                    "description": "newer",
                    "body": "## Steps\n1. New",
                }
            ],
        )
        written = observe.accept_draft(
            folder,
            memory_dir=self.root / "memory",
            skills_dir=skills_dir,
            dest_root=self.root / "accepted",
        )
        self.assertTrue(any("already exists" in line for line in written))
        body = (skills_dir / "open-hn" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Existing", body)
        self.assertNotIn("1. New", body)


class ComputerUseGateTests(unittest.TestCase):
    def test_computer_use_active_when_agent_listed(self) -> None:
        with patch("app_status.active_agents", return_value=[{"id": "a1"}]), patch(
            "app_status.read_status", return_value={"state": "idle"}
        ):
            self.assertTrue(observe.computer_use_active())

    def test_computer_use_active_when_state_is_agent(self) -> None:
        with patch("app_status.active_agents", return_value=[]), patch(
            "app_status.read_status", return_value={"state": "agent"}
        ):
            self.assertTrue(observe.computer_use_active())

    def test_computer_use_idle(self) -> None:
        with patch("app_status.active_agents", return_value=[]), patch(
            "app_status.read_status", return_value={"state": "idle"}
        ):
            self.assertFalse(observe.computer_use_active())


class FocusedDisplayCaptureTests(unittest.TestCase):
    def test_captures_display_id_of_focused_window(self) -> None:
        studio = {
            "index": 1,
            "name": "Studio Display",
            "main": True,
            "display_id": 2,
        }
        with (
            patch("displays.monitor_for_app_window", return_value=studio),
            patch.object(observe, "_capture_cg_display", return_value=b"PNG") as cg,
            patch.object(observe, "_capture_primary_png") as primary,
            patch.object(observe, "_downscale_png", side_effect=lambda data: data),
        ):
            png, monitor = observe._capture_focused_display("Google Chrome")
        self.assertEqual(png, b"PNG")
        self.assertEqual(monitor["name"], "Studio Display")
        cg.assert_called_once_with(2)
        primary.assert_not_called()

    def test_falls_back_to_primary_without_display_id(self) -> None:
        laptop = {"index": 0, "name": "Built-in", "main": False}
        with (
            patch("displays.monitor_for_app_window", return_value=laptop),
            patch.object(observe, "_capture_cg_display") as cg,
            patch.object(observe, "_capture_primary_png", return_value=b"PRI"),
            patch.object(observe, "_downscale_png", side_effect=lambda data: data),
        ):
            png, monitor = observe._capture_focused_display("Code")
        self.assertEqual(png, b"PRI")
        self.assertEqual(monitor["name"], "Built-in")
        cg.assert_not_called()


if __name__ == "__main__":
    unittest.main()
