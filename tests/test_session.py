"""Session phase machine."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

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

    def test_bind(self) -> None:
        sess = Session(project_status=False)
        previous = bind_session(sess)
        bind_session(previous)


if __name__ == "__main__":
    unittest.main()
