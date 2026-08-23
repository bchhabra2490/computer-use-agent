"""Tests for dictation cursor overlay helpers (no AppKit required)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import dictation_overlay as dov  # noqa: E402


class OverlayFrameTests(unittest.TestCase):
    def test_frame_below_cursor(self) -> None:
        rect = dov.overlay_frame_near_point(100.0, 200.0, width=52, height=20, margin_below=10)
        self.assertEqual(rect["x"], 114)
        self.assertEqual(rect["y"], 170)
        self.assertEqual(rect["width"], 52)
        self.assertEqual(rect["height"], 20)

    def test_dot_alphas_cycles(self) -> None:
        self.assertEqual(dov.dot_alphas(0), (1.0, 0.28, 0.55))
        self.assertEqual(dov.dot_alphas(1), (0.55, 1.0, 0.28))
        self.assertEqual(dov.dot_alphas(2), (0.28, 0.55, 1.0))
        self.assertEqual(dov.dot_alphas(3), dov.dot_alphas(0))

    def test_spinner_angles_rotate(self) -> None:
        a0, b0 = dov.spinner_angles(0.0, rps=1.0, sweep=270.0)
        a1, b1 = dov.spinner_angles(0.25, rps=1.0, sweep=270.0)
        self.assertAlmostEqual(b0 - a0, 270.0)
        self.assertAlmostEqual(a1 - a0, 90.0)
        wrap_start, wrap_end = dov.spinner_angles(1.0, rps=1.0, sweep=270.0)
        self.assertAlmostEqual(wrap_start, 0.0)
        self.assertAlmostEqual(wrap_end, 270.0)

    def test_disabled_on_non_darwin(self) -> None:
        with mock.patch.object(dov.sys, "platform", "linux"):
            self.assertFalse(dov.dictation_overlay_enabled())


if __name__ == "__main__":
    unittest.main()
