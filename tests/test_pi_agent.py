"""Pi launcher: same orchestrator path, no isolated HTTP runtime."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pi_agent as pi  # noqa: E402


class IsolationTests(unittest.TestCase):
    def test_import_does_not_load_desktop_or_models(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import pi_agent, sys; "
                "assert not ({'agent','actions','pyautogui','stt','tts','numpy',"
                "'torch','onnxruntime','wake','orchestrator'} & set(sys.modules))",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class LauncherTests(unittest.TestCase):
    def test_check_loads_env_and_does_not_start_orchestrator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env.pi"
            env_path.write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=False):
                pi.main(["--env", str(env_path), "--check"])
                self.assertEqual(os.environ.get("COMPUTER_USE"), "0")
                self.assertEqual(os.environ.get("CHAT_BROWSER"), "1")

    def test_main_invokes_orchestrator_pi(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env.pi"
            env_path.write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")
            fake = MagicMock()
            fake.main = MagicMock()
            with (
                patch.dict(os.environ, {}, clear=False),
                patch.dict(sys.modules, {"orchestrator": fake}),
            ):
                pi.main(["--env", str(env_path), "--no-gpio"])
            fake.main.assert_called_once_with(["--auto", "--pi"])


if __name__ == "__main__":
    unittest.main()
