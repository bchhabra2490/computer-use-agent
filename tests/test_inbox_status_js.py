"""Run the chat UI inbox-status JavaScript regression tests."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS_TEST = ROOT / "tests" / "test_inbox_status.js"


class InboxStatusJsTests(unittest.TestCase):
    def test_node_regression(self) -> None:
        proc = subprocess.run(
            ["node", "--test", str(JS_TEST)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            self.fail(proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
