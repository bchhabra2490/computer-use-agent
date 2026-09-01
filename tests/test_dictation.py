"""Tests for Fn-dictation helpers (no Quartz / mic required)."""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import dictation as di  # noqa: E402


class FnFlagTests(unittest.TestCase):
    def test_fn_alone(self) -> None:
        secondary = 0x00800000
        other = 0x00010000 | 0x00020000 | 0x00080000 | 0x00100000  # shift/ctrl/alt/cmd-ish
        self.assertTrue(di._fn_alone(secondary, secondary_fn=secondary, other_mods=other))
        self.assertFalse(
            di._fn_alone(secondary | 0x00100000, secondary_fn=secondary, other_mods=other)
        )
        self.assertFalse(di._fn_alone(0, secondary_fn=secondary, other_mods=other))

    def test_globe_fn_keycode_not_fkeys(self) -> None:
        other = 0x00010000 | 0x00020000 | 0x00080000 | 0x00100000
        self.assertTrue(di._is_globe_fn_key(63, 0x00800000, other_mods=other))
        self.assertTrue(di._is_globe_fn_key(63, 0, other_mods=other))
        self.assertFalse(di._is_globe_fn_key(122, 0x00800000, other_mods=other))  # F1
        self.assertFalse(di._is_globe_fn_key(63, 0x00100000, other_mods=other))  # cmd

    def test_duplicate_fn_down_does_not_cancel(self) -> None:
        daemon = di.DictationDaemon()
        daemon._session.set()
        daemon._fn_down = True
        daemon._last_edge = time.monotonic()
        with patch("app_status.request_cancel") as cancel:
            swallowed = daemon.on_fn_edge(down=True)
        self.assertTrue(swallowed)
        cancel.assert_not_called()

    def test_paste_restores_clipboard(self) -> None:
        calls: list[tuple] = []

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd))
            return type("R", (), {"returncode": 0})()

        with (
            patch("dictation.subprocess.check_output", return_value=b"OLD"),
            patch("dictation.subprocess.run", side_effect=fake_run),
            patch("dictation.time.sleep"),
        ):
            di.paste_dictation("hello world")
        self.assertIn(["pbcopy"], [c for c in calls if c and c[0] == "pbcopy"])
        self.assertTrue(any(c[:1] == ["osascript"] for c in calls))
        # Last pbcopy restores previous clipboard.
        pb_inputs = []
        # re-run capturing input kwargs
        calls.clear()

        def fake_run2(cmd, **kwargs):
            calls.append((list(cmd), kwargs.get("input")))
            return type("R", (), {"returncode": 0})()

        with (
            patch("dictation.subprocess.check_output", return_value=b"OLD"),
            patch("dictation.subprocess.run", side_effect=fake_run2),
            patch("dictation.time.sleep"),
        ):
            di.paste_dictation("hello world")
        pbcopy = [c for c in calls if c[0][:1] == ["pbcopy"]]
        self.assertEqual(pbcopy[0][1], b"hello world")
        self.assertEqual(pbcopy[-1][1], b"OLD")

    def test_daemon_skips_when_stt_active(self) -> None:
        daemon = di.DictationDaemon()
        with patch(
            "app_status.read_status",
            return_value={"stt_active": True},
        ):
            ok, why = daemon._can_start()
        self.assertFalse(ok)
        self.assertIn("listening", why)

    def test_live_paster_extends_with_delta(self) -> None:
        pasted: list[str] = []
        paster = di.LiveDictationPaster(debounce_s=0.0)

        def capture(chunk: str) -> None:
            pasted.append(chunk)

        with (
            patch.object(paster, "_paste_chunk", side_effect=capture),
            patch.object(paster, "_ax_replace", return_value=False),
            patch.object(paster, "_restore_clip"),
        ):
            paster._apply("hello")
            paster._apply("hello world")
            paster.finalize("hello world")
        self.assertEqual(pasted, ["hello", " world"])

    def test_live_paster_coalesces_partials(self) -> None:
        applied: list[str] = []
        paster = di.LiveDictationPaster(debounce_s=0.05)
        with patch.object(paster, "_apply", side_effect=lambda t: applied.append(t)):
            paster.on_partial("hel")
            paster.on_partial("hello")
            time.sleep(0.12)
        self.assertEqual(applied, ["hello"])

    def test_live_paster_discard_clears(self) -> None:
        backs: list[int] = []
        paster = di.LiveDictationPaster(debounce_s=0.0)
        paster._inserted = "gone"
        with (
            patch.object(paster, "_ax_replace", return_value=False),
            patch("dictation._backspace_n", side_effect=lambda n: backs.append(n)),
            patch.object(paster, "_restore_clip"),
        ):
            paster.discard()
        self.assertEqual(backs, [4])
        self.assertEqual(paster._inserted, "")


    def test_fn_up_switches_overlay_to_spinner(self) -> None:
        daemon = di.DictationDaemon()
        daemon._session.set()
        daemon._fn_down = True
        with patch("dictation_overlay.set_dictation_overlay_style") as set_style:
            swallowed = daemon.on_fn_edge(down=False)
        set_style.assert_called_once_with("spinner")
        self.assertTrue(swallowed)
        self.assertTrue(daemon._hold_send.is_set())

    def test_daemon_shows_overlay_hooks(self) -> None:
        daemon = di.DictationDaemon()
        shown: list[str] = []
        hidden: list[str] = []
        fake_stt = MagicMock()
        fake_stt.listen_dictation.return_value = "hello"
        fake_stt.ListenCancelled = type("ListenCancelled", (Exception,), {})
        fake_stt.NoSpeechError = type("NoSpeechError", (Exception,), {})
        with (
            patch.object(daemon, "_can_start", return_value=(True, "ok")),
            patch("dictation_overlay.show_dictation_overlay", side_effect=lambda: shown.append("show")),
            patch("dictation_overlay.hide_dictation_overlay", side_effect=lambda: hidden.append("hide")),
            patch.dict(sys.modules, {"stt": fake_stt, "openai": MagicMock()}),
            patch.object(di.LiveDictationPaster, "finalize"),
            patch("app_status.set_state"),
            patch("app_status.read_status", return_value={}),
        ):
            daemon._run_session()
        self.assertEqual(shown, ["show"])
        self.assertEqual(hidden, ["hide"])


if __name__ == "__main__":
    unittest.main()
