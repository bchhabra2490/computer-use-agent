"""Session phase machine."""

from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from session import Session, SessionError, bind_session  # noqa: E402


class SessionTests(unittest.TestCase):
    def test_legal_voice_loop(self) -> None:
        sess = Session(strict=True, project_status=False)
        sess.enter("ready", "starting")
        sess.enter("waiting")
        sess.enter("listening")
        sess.enter("thinking")
        sess.enter("speaking")
        sess.enter("agent")
        sess.enter("ask")
        sess.enter("agent")
        sess.enter("ready")
        sess.enter("done")
        sess.enter("idle")
        self.assertEqual(sess.phase, "idle")

    def test_same_phase_refresh_ok(self) -> None:
        sess = Session(strict=True, project_status=False)
        sess.enter("ready", "a")
        sess.enter("ready", "b")
        self.assertEqual(sess.detail, "b")

    def test_illegal_strict(self) -> None:
        sess = Session(strict=True, project_status=False)
        with self.assertRaises(SessionError):
            sess.enter("ask")

    def test_illegal_non_strict_still_moves(self) -> None:
        sess = Session(strict=False, project_status=False)
        sess.enter("ask")
        self.assertEqual(sess.phase, "ask")

    def test_history_is_bounded(self) -> None:
        from session import HISTORY_LIMIT

        sess = Session(strict=False, project_status=False)
        for _ in range(HISTORY_LIMIT + 25):
            sess.enter("ready", "tick")
        self.assertLessEqual(len(sess.history), HISTORY_LIMIT)

    def test_illegal_transition_emits_event(self) -> None:
        import events as ev

        sink = ev.EventSink()
        seen: list[ev.Event] = []
        sink.on(seen.append)
        previous = ev.bind_events(sink)
        try:
            sess = Session(strict=False, project_status=False)
            sess.enter("ask")
        finally:
            ev.bind_events(previous)
        types = [e.type for e in seen]
        self.assertIn("session", types)
        illegal = [e for e in seen if e.type == "session" and not e.payload.get("legal")]
        self.assertTrue(illegal)

    def test_bind(self) -> None:
        sess = Session(project_status=False)
        previous = bind_session(sess)
        bind_session(previous)

    def test_enter_increments_revision(self) -> None:
        sess = Session(strict=True, project_status=False)
        self.assertEqual(sess.revision, 0)
        sess.enter("ready")
        self.assertEqual(sess.revision, 1)
        sess.enter("waiting")
        self.assertEqual(sess.revision, 2)

    def test_delayed_thinking_does_not_clobber_speaking(self) -> None:
        import app_status as st

        tmp = tempfile.TemporaryDirectory()
        runtime = Path(tmp.name)
        status = runtime / "status.json"
        hold = threading.Event()
        started = threading.Event()
        original = st.set_state

        def gated(state: str, detail: str = "", **kwargs):
            if state == "thinking":
                started.set()
                hold.wait(timeout=2)
            original(state, detail, **kwargs)

        try:
            with (
                patch.object(st, "RUNTIME_DIR", runtime),
                patch.object(st, "STATUS_PATH", status),
                patch.object(st, "set_state", gated),
            ):
                sess = Session(strict=True, project_status=True)
                sess.enter("ready")
                worker = threading.Thread(target=lambda: sess.enter("thinking"))
                worker.start()
                self.assertTrue(started.wait(timeout=2))
                sess.enter("speaking")
                hold.set()
                worker.join(timeout=2)
                self.assertEqual(sess.phase, "speaking")
                self.assertEqual(st.read_status()["state"], "speaking")
                self.assertEqual(st.read_status()["session_revision"], sess.revision)
                self.assertEqual(st.read_status()["session_id"], sess.session_id)
        finally:
            tmp.cleanup()

    def test_new_session_is_not_blocked_by_persisted_revision(self) -> None:
        import app_status as st

        tmp = tempfile.TemporaryDirectory()
        runtime = Path(tmp.name)
        status = runtime / "status.json"
        try:
            with (
                patch.object(st, "RUNTIME_DIR", runtime),
                patch.object(st, "STATUS_PATH", status),
            ):
                old = Session(strict=True, project_status=True)
                old.enter("ready")
                old.enter("waiting")
                old.enter("listening")
                old.enter("thinking")
                old.enter("speaking")
                self.assertEqual(st.read_status()["state"], "speaking")
                self.assertGreater(st.read_status()["session_revision"], 1)

                new = Session(strict=True, project_status=True)
                new.enter("ready")
                self.assertEqual(new.phase, "ready")
                self.assertEqual(st.read_status()["state"], "ready")
                self.assertEqual(st.read_status()["session_id"], new.session_id)

                st.set_state(
                    "thinking",
                    revision=old.revision,
                    session_id=old.session_id,
                )
                self.assertEqual(st.read_status()["state"], "ready")
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
