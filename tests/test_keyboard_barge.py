"""Interrupt bridging without opening a real terminal or audio device."""

from __future__ import annotations

from unittest.mock import patch

import keyboard_barge


def test_global_cancel_interrupts_tts_without_terminal_focus():
    with (
        patch.object(keyboard_barge, "keyboard_barge_enabled", return_value=False),
        patch("app_status.cancel_pending", return_value=True),
    ):
        event, release = keyboard_barge.acquire_tts_interrupt()
        try:
            assert event.wait(0.5)
        finally:
            release()
