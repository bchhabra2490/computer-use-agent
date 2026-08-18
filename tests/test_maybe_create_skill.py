"""maybe_create_skill must not block the agent / last TTS."""

from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import agent as computer_agent  # noqa: E402
from task_log import TaskLog  # noqa: E402


class MaybeCreateSkillTests(unittest.TestCase):
    def test_background_returns_before_llm(self) -> None:
        started = threading.Event()
        released = threading.Event()

        def _block(*_args, **_kwargs) -> None:
            started.set()
            released.wait(timeout=2)

        with tempfile.TemporaryDirectory() as tmp:
            log = TaskLog("play a song", logs_dir=Path(tmp))
            log.finish("completed")
            with patch.object(computer_agent, "_maybe_create_skill_impl", side_effect=_block):
                t0 = time.monotonic()
                computer_agent.maybe_create_skill(MagicMock(), log, voice=True)
                elapsed = time.monotonic() - t0
                self.assertLess(elapsed, 0.5)
                self.assertTrue(started.wait(timeout=1))
                released.set()

    def test_inline_runs_impl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = TaskLog("open notes", logs_dir=Path(tmp))
            log.finish("completed")
            with patch.object(computer_agent, "_maybe_create_skill_impl") as impl:
                computer_agent.maybe_create_skill(
                    MagicMock(),
                    log,
                    voice=False,
                    background=False,
                )
            impl.assert_called_once()


if __name__ == "__main__":
    unittest.main()
