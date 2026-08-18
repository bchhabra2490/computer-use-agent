"""Tests for the cua daemon CLI helpers."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cua  # noqa: E402


class RunningPidTests(unittest.TestCase):
    def test_stale_pid_file_is_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pid_path = Path(tmp) / "cua.pid"
            pid_path.write_text("999999\n", encoding="utf-8")
            with (
                patch.object(cua, "PID_PATH", pid_path),
                patch.object(cua, "_LEGACY_PID_PATH", Path(tmp) / "cau.pid"),
                patch.object(cua, "_orchestrator_pid_from_status", return_value=None),
                patch.object(cua, "_pid_alive", return_value=False),
            ):
                self.assertIsNone(cua.running_pid())
                self.assertFalse(pid_path.exists())

    def test_live_pid_file_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pid_path = Path(tmp) / "cua.pid"
            pid_path.write_text("4242\n", encoding="utf-8")
            with (
                patch.object(cua, "PID_PATH", pid_path),
                patch.object(cua, "_pid_alive", return_value=True),
            ):
                self.assertEqual(cua.running_pid(), 4242)

    def test_legacy_cau_pid_is_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "cau.pid"
            legacy.write_text("4242\n", encoding="utf-8")
            with (
                patch.object(cua, "PID_PATH", Path(tmp) / "cua.pid"),
                patch.object(cua, "_LEGACY_PID_PATH", legacy),
                patch.object(cua, "_pid_alive", return_value=True),
            ):
                self.assertEqual(cua.running_pid(), 4242)


class ShimTests(unittest.TestCase):
    def test_shim_body_points_at_cua_py(self) -> None:
        body = cua._shim_body()
        self.assertIn(cua.SHIM_MARK, body)
        self.assertIn("cua.py", body)
        self.assertTrue(body.startswith("#!/bin/sh"))

    def test_install_shim_writes_cua_and_retargets_cau(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bindir = Path(tmp) / "bin"
            bindir.mkdir()
            legacy = bindir / "cau"
            legacy.write_text("#!/bin/sh\n# cau — computer-use-agent daemon CLI\n", encoding="utf-8")
            with patch.object(cua, "_writable_bin_dirs", return_value=[bindir]):
                written = cua.install_shim()
            self.assertEqual(written, [bindir / "cua"])
            self.assertIn("cua.py", (bindir / "cua").read_text(encoding="utf-8"))
            self.assertIn("cua.py", legacy.read_text(encoding="utf-8"))


class StartStopTests(unittest.TestCase):
    def test_start_is_idempotent_when_running(self) -> None:
        with patch.object(cua, "running_pid", return_value=123):
            self.assertEqual(cua.cmd_start(), 0)

    def test_stop_when_not_running(self) -> None:
        with (
            patch.object(cua, "running_pid", return_value=None),
            patch.object(cua, "_clear_pid_file") as clear,
        ):
            self.assertEqual(cua.cmd_stop(), 0)
            clear.assert_called_once()

    def test_start_launches_orchestrator_auto(self) -> None:
        proc = MagicMock()
        proc.pid = 777
        proc.poll.return_value = None
        with (
            patch.object(cua, "running_pid", return_value=None),
            patch.object(cua, "install_shim", return_value=[]),
            patch.object(cua, "cua_on_path", return_value=True),
            patch.object(cua, "_write_pid_file") as write_pid,
            patch("cua.subprocess.Popen", return_value=proc) as popen,
            patch("cua.time.sleep"),
            patch("builtins.open", create=True),
        ):
            self.assertEqual(cua.cmd_start(), 0)
            write_pid.assert_called_once_with(777)
            launched = popen.call_args[0][0]
            self.assertIn("--auto", launched)
            self.assertTrue(str(launched[1]).endswith("orchestrator.py"))


class MainTests(unittest.TestCase):
    def test_unknown_command_exits(self) -> None:
        with self.assertRaises(SystemExit):
            cua.main(["nope"])

    def test_observe_list_dispatches(self) -> None:
        with patch("observe.cmd_list", return_value=0) as cmd:
            self.assertEqual(cua.main(["observe", "list"]), 0)
            cmd.assert_called_once()

    def test_observe_accept_all_dispatches(self) -> None:
        with patch("observe.cmd_accept", return_value=0) as cmd:
            self.assertEqual(cua.main(["observe", "accept", "--all"]), 0)
            cmd.assert_called_once_with(
                name=None,
                all_drafts=True,
                items=[],
                memories=None,
                skills=None,
            )

    def test_observe_accept_items_dispatch(self) -> None:
        with patch("observe.cmd_accept", return_value=0) as cmd:
            self.assertEqual(
                cua.main(
                    [
                        "observe",
                        "accept",
                        "20260818T134913Z_google-chrome",
                        "m1",
                        "--skill",
                        "open-hn",
                    ]
                ),
                0,
            )
            cmd.assert_called_once_with(
                name="20260818T134913Z_google-chrome",
                all_drafts=False,
                items=["m1"],
                memories=None,
                skills=["open-hn"],
            )

    def test_observe_reject_all_dispatches(self) -> None:
        with patch("observe.cmd_reject", return_value=0) as cmd:
            self.assertEqual(cua.main(["observe", "reject", "--all"]), 0)
            cmd.assert_called_once_with(
                name=None,
                all_drafts=True,
                items=[],
                memories=None,
                skills=None,
            )


if __name__ == "__main__":
    unittest.main()
