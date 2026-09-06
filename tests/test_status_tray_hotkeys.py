"""Global tray shortcut behavior without loading AppKit."""

from __future__ import annotations

from unittest.mock import patch

from status_tray import _scheduled_task_count, _scheduled_task_titles, trigger_listen_shortcut


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


def test_listen_shortcut_cancels_turn_while_thinking():
    with (
        patch("status_tray.request_listen") as listen,
        patch("status_tray.request_cancel") as cancel,
    ):
        result = trigger_listen_shortcut({"state": "thinking", "stt_active": False})

    assert result == "cancel"
    cancel.assert_called_once_with()
    listen.assert_not_called()


def test_scheduled_task_helpers_render_queue_rows():
    class Task:
        status = "queued"
        task = "Open the deployment dashboard and check health"
        run_at = 120.0

    with (
        patch("status_tray.time.time", return_value=0.0),
        patch("scheduled_tasks.list_scheduled_tasks", return_value=[Task()]),
    ):
        assert _scheduled_task_count() == 1
        rows = _scheduled_task_titles()
    assert rows
    assert "deployment dashboard" in rows[0]
