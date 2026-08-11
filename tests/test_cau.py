"""Tests for the cau daemon CLI helpers."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cau  # noqa: E402


class RunningPidTests(unittest.TestCase):
    def test_stale_pid_file_is_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pid_path = Path(tmp) / "cau.pid"
            pid_path.write_text("999999\n", encoding="utf-8")
            with (
                patch.object(cau, "PID_PATH", pid_path),
                patch.object(cau, "_orchestrator_pid_from_status", return_value=None),
                patch.object(cau, "_pid_alive", return_value=False),
            ):
                self.assertIsNone(cau.running_pid())
                self.assertFalse(pid_path.exists())

    def test_live_pid_file_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pid_path = Path(tmp) / "cau.pid"
            pid_path.write_text("4242\n", encoding="utf-8")
            with (
                patch.object(cau, "PID_PATH", pid_path),
                patch.object(cau, "_pid_alive", return_value=True),
            ):
                self.assertEqual(cau.running_pid(), 4242)


class ShimTests(unittest.TestCase):
    def test_shim_body_points_at_cau_py(self) -> None:
        body = cau._shim_body()
        self.assertIn(cau.SHIM_MARK, body)
        self.assertIn("cau.py", body)
        self.assertTrue(body.startswith("#!/bin/sh"))


class StartStopTests(unittest.TestCase):
    def test_start_is_idempotent_when_running(self) -> None:
        with patch.object(cau, "running_pid", return_value=123):
            self.assertEqual(cau.cmd_start(), 0)

    def test_stop_when_not_running(self) -> None:
        with (
            patch.object(cau, "running_pid", return_value=None),
            patch.object(cau, "_clear_pid_file") as clear,
        ):
            self.assertEqual(cau.cmd_stop(), 0)
            clear.assert_called_once()

    def test_start_launches_orchestrator_auto(self) -> None:
        proc = MagicMock()
        proc.pid = 777
        proc.poll.return_value = None
        with (
            patch.object(cau, "running_pid", return_value=None),
            patch.object(cau, "install_shim", return_value=[]),
            patch.object(cau, "cau_on_path", return_value=True),
            patch.object(cau, "_write_pid_file") as write_pid,
            patch("cau.subprocess.Popen", return_value=proc) as popen,
            patch("cau.time.sleep"),
            patch("builtins.open", create=True),
        ):
            self.assertEqual(cau.cmd_start(), 0)
            write_pid.assert_called_once_with(777)
            launched = popen.call_args[0][0]
            self.assertIn("--auto", launched)
            self.assertTrue(str(launched[1]).endswith("orchestrator.py"))


class MainTests(unittest.TestCase):
    def test_unknown_command_exits(self) -> None:
        with self.assertRaises(SystemExit):
            cau.main(["nope"])


if __name__ == "__main__":
    unittest.main()
