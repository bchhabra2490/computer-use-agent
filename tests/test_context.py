"""Ephemeral context bundle (not durable memory)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import context as ctx  # noqa: E402


class ContextBundleTests(unittest.TestCase):
    def test_clip_and_persist_runtime_not_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            occupancy = "Open windows by display (1 attached):\n  [0] Built-in"
            with (
                patch.object(ctx, "BUDGET_DISPLAYS", 40),
                patch("displays.format_monitor_occupancy", return_value=occupancy + " extra"),
                patch("skills.format_skill_catalog", return_value="skills"),
                patch("memory.format_memory_catalog", return_value="memories"),
                patch("mcp_client.format_mcp_catalog", return_value="mcp"),
            ):
                bundle = ctx.assemble_context(
                    persist=True,
                    runtime_dir=root,
                    include_geometry=False,
                    monitors=[
                        {
                            "index": 0,
                            "name": "Built-in",
                            "main": True,
                            "x": 0,
                            "y": 0,
                            "width": 1440,
                            "height": 900,
                        }
                    ],
                    occupancy=[],
                    frontmost="",
                )
            self.assertTrue((root / "desktop.txt").exists())
            self.assertFalse((root / "apps").exists())
            self.assertIn("… (truncated)", bundle.displays)
            self.assertEqual(bundle.skills, "skills")
            self.assertEqual(bundle.mcp, "mcp")
            self.assertIn("sleep", bundle.not_to_do.lower())

    def test_desktop_block_joins_geometry(self) -> None:
        bundle = ctx.ContextBundle(
            displays="occupancy",
            skills="",
            memories="",
            mcp="",
            geometry="geometry",
        )
        self.assertIn("geometry", bundle.desktop_block())
        self.assertIn("occupancy", bundle.desktop_block())


class NotToDoTests(unittest.TestCase):
    def test_loads_repo_not_to_do_list(self) -> None:
        text = ctx.format_not_to_do()
        self.assertIn("Not to do", text)
        self.assertIn("sleep", text.lower())
        self.assertIn("say", text.lower())
        self.assertNotIn("sleep 272", text)

    def test_missing_file_is_empty(self) -> None:
        missing = Path("/tmp/does-not-exist-not-to-do.md")
        self.assertEqual(ctx.format_not_to_do(path=missing), "")


class TurnDesktopContextTests(unittest.TestCase):
    def test_disabled_returns_empty(self) -> None:
        with patch.dict("os.environ", {"ORCHESTRATOR_DESKTOP_CONTEXT": "0"}):
            out = ctx.capture_turn_desktop_context()
        self.assertEqual(out.text, "")
        self.assertIsNone(out.screenshot_png)

    def test_includes_display_ax_and_screenshot(self) -> None:
        bundle = ctx.ContextBundle(
            displays="occupancy",
            skills="",
            memories="",
            mcp="",
            geometry="geometry",
        )
        mock_actions = MagicMock()
        mock_actions.list_monitors.return_value = [{"index": 0, "name": "Built-in", "main": True}]
        desktop = MagicMock()
        desktop.capture_screenshot.return_value = b"\x89PNG"
        desktop._model_w = 1200
        desktop._model_h = 800
        mock_actions.DesktopController.return_value = desktop
        with (
            patch.dict(
                "os.environ",
                {
                    "ORCHESTRATOR_DESKTOP_CONTEXT": "1",
                    "ORCHESTRATOR_DESKTOP_SCREENSHOT": "1",
                    "ORCHESTRATOR_DESKTOP_AX": "1",
                },
            ),
            patch.dict(sys.modules, {"actions": mock_actions}),
            patch.object(ctx, "assemble_context", return_value=bundle),
            patch("accessibility.read_ui_text", return_value="App: Safari\n- Tab: Example"),
        ):
            out = ctx.capture_turn_desktop_context()
        self.assertIn("Desktop snapshot", out.text)
        self.assertIn("Accessibility text", out.text)
        self.assertIn("geometry", out.text)
        self.assertIn("occupancy", out.text)
        self.assertEqual(out.screenshot_png, b"\x89PNG")

    def test_read_screen_always_captures(self) -> None:
        bundle = ctx.ContextBundle(
            displays="occupancy",
            skills="",
            memories="",
            mcp="",
            geometry="geometry",
        )
        mock_actions = MagicMock()
        mock_actions.list_monitors.return_value = [{"index": 0, "name": "Built-in", "main": True}]
        desktop = MagicMock()
        desktop.capture_screenshot.return_value = b"\x89PNG"
        desktop._model_w = 1200
        desktop._model_h = 800
        mock_actions.DesktopController.return_value = desktop
        with (
            patch.dict("os.environ", {"ORCHESTRATOR_DESKTOP_CONTEXT": "0"}),
            patch.dict(sys.modules, {"actions": mock_actions}),
            patch.object(ctx, "assemble_context", return_value=bundle),
            patch("accessibility.read_ui_text", return_value="App: Safari"),
        ):
            out = ctx.read_screen()
        self.assertIn("Screen read", out.text)
        self.assertIn("Accessibility text", out.text)
        self.assertEqual(out.screenshot_png, b"\x89PNG")

    def test_read_screen_vision_input(self) -> None:
        item = ctx.read_screen_vision_input(b"\x89PNG")
        self.assertEqual(item["role"], "user")
        types = [p["type"] for p in item["content"]]
        self.assertIn("input_image", types)


if __name__ == "__main__":
    unittest.main()
