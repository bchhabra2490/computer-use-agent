"""Record / match / bind easy-task action traces (no GUI)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from task_log import TaskLog  # noqa: E402
import traces as tr  # noqa: E402


def _log_with_actions(task: str, batches: list[list[dict]], *, difficulty: str = "easy") -> TaskLog:
    tmp = tempfile.TemporaryDirectory()
    log = TaskLog(task, logs_dir=Path(tmp.name))
    log.record("router", f"{difficulty} → luna", {"difficulty": difficulty, "model": "x"})
    for batch in batches:
        log.record("computer_actions", f"{len(batch)} action(s)", {"actions": batch})
    log._tmp = tmp  # type: ignore[attr-defined]
    return log


class TraceRecordTests(unittest.TestCase):
    def tearDown(self) -> None:
        for name in list(self.__dict__):
            val = getattr(self, name)
            if isinstance(val, TaskLog) and hasattr(val, "_tmp"):
                val._tmp.cleanup()

    def test_parameterize_url(self) -> None:
        task = "Open Chrome and go to https://news.ycombinator.com"
        actions = [
            {"type": "keypress", "keys": ["cmd", "space"]},
            {"type": "type", "text": "Google Chrome"},
            {"type": "keypress", "keys": ["enter"]},
            {"type": "wait"},
            {"type": "keypress", "keys": ["cmd", "l"]},
            {"type": "type", "text": "https://news.ycombinator.com"},
            {"type": "keypress", "keys": ["enter"]},
        ]
        bound, params = tr.parameterize_actions(task, tr.sanitize_actions(actions))
        self.assertEqual(params, ["url"])
        typed = [a["text"] for a in bound if a["type"] == "type"]
        self.assertEqual(typed[0], "Google Chrome")
        self.assertEqual(typed[1], "{{url}}")
        waits = [a for a in bound if a["type"] == "wait"]
        self.assertEqual(waits[0]["ms"], 2000)

    def test_skip_click_only(self) -> None:
        actions = [
            {"type": "click", "x": 10, "y": 10},
            {"type": "click", "x": 20, "y": 20},
            {"type": "click", "x": 30, "y": 30},
            {"type": "type", "text": "hi"},
        ]
        reason = tr.should_skip_record("click around", difficulty="easy", actions=actions)
        self.assertEqual(reason, "not enough keypress/type/wait actions")

    def test_keep_keyboard_spine_despite_clicks(self) -> None:
        actions = [
            {"type": "keypress", "keys": ["cmd", "space"]},
            {"type": "type", "text": "Google Chrome"},
            {"type": "keypress", "keys": ["enter"]},
            {"type": "click", "x": 100, "y": 200},
            {"type": "click", "x": 120, "y": 240},
            {"type": "click", "x": 140, "y": 260},
            {"type": "drag", "path": [{"x": 1, "y": 1}, {"x": 2, "y": 2}]},
            {"type": "keypress", "keys": ["cmd", "l"]},
            {"type": "type", "text": "https://www.youtube.com"},
            {"type": "keypress", "keys": ["enter"]},
        ]
        reason = tr.should_skip_record(
            "play a song on youtube",
            difficulty="easy",
            actions=actions,
        )
        self.assertIsNone(reason)

    def test_skip_hard_cad(self) -> None:
        actions = [
            {"type": "keypress", "keys": ["cmd", "space"]},
            {"type": "type", "text": "EasyEDA"},
        ]
        reason = tr.should_skip_record(
            "Open EasyEDA and route a USB hub",
            difficulty="easy",
            actions=actions,
        )
        self.assertEqual(reason, "hard-task keywords")

    def test_propose_from_log(self) -> None:
        task = "Open Chrome and go to https://example.com"
        log = _log_with_actions(
            task,
            [
                [
                    {"type": "keypress", "keys": ["cmd", "space"]},
                    {"type": "type", "text": "Google Chrome"},
                    {"type": "keypress", "keys": ["enter"]},
                    {"type": "keypress", "keys": ["cmd", "l"]},
                    {"type": "type", "text": "https://example.com"},
                    {"type": "keypress", "keys": ["enter"]},
                ]
            ],
        )
        self.addCleanup(log._tmp.cleanup)
        trace = tr.propose_trace(task, log)
        self.assertIsNotNone(trace)
        assert trace is not None
        self.assertIn("url", trace.params)
        self.assertEqual(trace.verify.get("ax_app"), "Google Chrome")
        self.assertIn("chrome", trace.match)


class TraceMatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.trace = tr.Trace(
            name="open-chrome",
            match=["open", "chrome"],
            params=["url"],
            actions=[
                {"type": "keypress", "keys": ["cmd", "l"]},
                {"type": "type", "text": "{{url}}"},
                {"type": "keypress", "keys": ["enter"]},
            ],
            verify={"ax_app": "Google Chrome"},
            source_task="Open Chrome and go to https://example.com",
        )

    def test_match_and_bind_url(self) -> None:
        hit = tr.find_matching_trace(
            "open chrome and go to https://news.ycombinator.com",
            [self.trace],
        )
        self.assertIsNotNone(hit)
        assert hit is not None
        trace, params = hit
        self.assertEqual(trace.name, "open-chrome")
        self.assertEqual(params["url"], "https://news.ycombinator.com")
        bound = tr.bind_actions(trace, params)
        self.assertEqual(bound[1]["text"], "https://news.ycombinator.com")

    def test_notes_does_not_match_chrome_trace(self) -> None:
        notes = tr.Trace(
            name="open-notes",
            match=["open", "notes"],
            actions=[{"type": "type", "text": "Notes"}, {"type": "keypress", "keys": ["enter"]}],
        )
        hit = tr.find_matching_trace(
            "open chrome and go to https://example.com",
            [self.trace, notes],
        )
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[0].name, "open-chrome")
        miss = tr.find_matching_trace("open notes", [self.trace])
        self.assertIsNone(miss)

    def test_save_and_load(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        tr.save_trace(self.trace, traces_dir=root)
        loaded = tr.load_traces(root)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].name, "open-chrome")
        self.assertEqual(loaded[0].params, ["url"])


class TraceVerifyTests(unittest.TestCase):
    def test_verify_without_ax_app(self) -> None:
        trace = tr.Trace(name="x", match=["open"], actions=[{"type": "wait", "ms": 1}])
        self.assertTrue(tr.verify_trace(trace))

    def test_verify_app_name(self) -> None:
        trace = tr.Trace(
            name="x",
            match=["chrome"],
            actions=[{"type": "wait", "ms": 1}],
            verify={"ax_app": "Google Chrome"},
        )
        with patch.object(tr, "frontmost_app_name", return_value="Google Chrome"):
            self.assertTrue(tr.verify_trace(trace))
        with patch.object(tr, "frontmost_app_name", return_value="Notes"):
            self.assertFalse(tr.verify_trace(trace))


if __name__ == "__main__":
    unittest.main()
