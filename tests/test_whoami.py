"""who_am_i reads README.md for self-description."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import whoami as wa  # noqa: E402


class WhoAmITests(unittest.TestCase):
    def test_reads_repo_readme(self) -> None:
        text = wa.read_project_readme()
        self.assertIn("Personal Computer Use Agent", text)
        self.assertIn("who_am_i", text)
        self.assertNotIn("<img", text)

    def test_strips_html_and_truncates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.md"
            path.write_text(
                "# Agent\n\n<p><img src='x.png' /></p>\n\nI drive the desktop.\n",
                encoding="utf-8",
            )
            text = wa.read_project_readme(readme_path=path)
            self.assertIn("I drive the desktop.", text)
            self.assertNotIn("<p>", text)
            self.assertNotIn("<img", text)

    def test_missing_readme(self) -> None:
        missing = Path("/tmp/does-not-exist-whoami-readme.md")
        text = wa.read_project_readme(readme_path=missing)
        self.assertIn("not found", text.lower())

    def test_tool_output_instructs_short_spoken_summary(self) -> None:
        out = wa.format_whoami_output()
        self.assertIn("short summary", out.lower())
        self.assertIn("Personal Computer Use Agent", out)
        self.assertEqual(wa.WHO_AM_I_TOOL["name"], "who_am_i")


if __name__ == "__main__":
    unittest.main()
