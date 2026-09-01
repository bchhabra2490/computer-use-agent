from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import latency_report
from task_log import TaskLog


def _paths(tmp_path: Path):
    folder = tmp_path / "latency"
    return folder, folder / "traces.jsonl", folder / "report.md"


def test_voice_to_first_action_trace_and_report(tmp_path: Path) -> None:
    folder, traces, report = _paths(tmp_path)
    ticks = iter([1_000, 1_300, 1_500, 1_900, 2_100, 2_700, 3_500])
    with (
        patch.object(latency_report, "LATENCY_DIR", folder),
        patch.object(latency_report, "TRACES_PATH", traces),
        patch.object(latency_report, "REPORT_PATH", report),
        patch.object(latency_report, "_wall_ms", side_effect=lambda: next(ticks)),
    ):
        latency_report._ACTIVE.clear()
        latency_report._CURRENT_ID = None
        trace_id = latency_report.start_trace(wake_label="Jarvis")
        latency_report.mark(trace_id, "speech_finished")
        latency_report.mark(trace_id, "transcript_ready")
        latency_report.mark(trace_id, "plan_ready")
        latency_report.mark(trace_id, "agent_started", task="Open Notes")
        latency_report.mark(trace_id, "first_computer_action")
        saved = latency_report.finish_trace(trace_id, task="Open Notes")

        assert saved is not None
        assert saved["durations_ms"]["voice_to_first_action"] == 1_700
        assert saved["durations_ms"]["wake_to_transcript"] == 500
        payload = latency_report.report_payload()
        assert payload["completed_action_count"] == 1
        assert payload["metrics"]["voice_to_first_action"]["median_ms"] == 1_700
        assert report.is_file()
        assert "Voice → first action" in report.read_text(encoding="utf-8")


def test_task_log_marks_only_first_desktop_action(tmp_path: Path) -> None:
    with patch("latency_report.mark") as mark:
        log = TaskLog("Open Notes", logs_dir=tmp_path, latency_trace_id="trace-1")
        log.record("computer_actions", "1 action")
        log.record("computer_actions", "2 actions")

    assert mark.call_count == 2
    # latency_report.mark itself uses setdefault, so repeated batches cannot move
    # the first-action milestone.
    assert all(call.args[:2] == ("trace-1", "first_computer_action") for call in mark.call_args_list)


def test_corrupt_trace_lines_are_ignored(tmp_path: Path) -> None:
    folder, traces, report = _paths(tmp_path)
    folder.mkdir(parents=True)
    traces.write_text('{"id":"ok","durations_ms":{}}\nnot-json\n', encoding="utf-8")
    with (
        patch.object(latency_report, "LATENCY_DIR", folder),
        patch.object(latency_report, "TRACES_PATH", traces),
        patch.object(latency_report, "REPORT_PATH", report),
    ):
        rows = latency_report.read_traces()
        assert [row["id"] for row in rows] == ["ok"]
