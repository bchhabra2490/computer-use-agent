"""Signal shutdown must not acquire status locks or perform nested cleanup."""

from __future__ import annotations

import signal

import pytest

from orchestrator import _exit_on_signal


def test_signal_handler_only_requests_stack_unwind():
    with pytest.raises(SystemExit) as exc:
        _exit_on_signal(signal.SIGTERM, None)

    assert exc.value.code == 0
