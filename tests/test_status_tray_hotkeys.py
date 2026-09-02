"""Global tray shortcut behavior without loading AppKit."""

from __future__ import annotations

from unittest.mock import patch

from status_tray import trigger_listen_shortcut


def test_listen_shortcut_starts_when_idle():
    with (
        patch("status_tray.request_listen") as listen,
        patch("status_tray.request_cancel") as cancel,
    ):
        result = trigger_listen_shortcut({"state": "ready", "stt_active": False})

    assert result == "listen"
    listen.assert_called_once_with()
    cancel.assert_not_called()


def test_listen_shortcut_cancels_active_capture():
    with (
        patch("status_tray.request_listen") as listen,
        patch("status_tray.request_cancel") as cancel,
    ):
        result = trigger_listen_shortcut({"state": "listening", "stt_active": True})

    assert result == "cancel"
    cancel.assert_called_once_with()
    listen.assert_not_called()


def test_listen_shortcut_cancels_ask_user_capture():
    with (
        patch("status_tray.request_listen") as listen,
        patch("status_tray.request_cancel") as cancel,
    ):
        result = trigger_listen_shortcut({"state": "ask", "stt_active": False})

    assert result == "cancel"
    cancel.assert_called_once_with()
    listen.assert_not_called()
