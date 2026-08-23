"""Tests for post-task feedback capture and logging."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import task_feedback as tf


def test_interpret_feedback_yes_no_and_correction():
    assert tf.interpret_feedback_text("yes") == (True, "")
    assert tf.interpret_feedback_text("nope") == (False, "")
    accurate, note = tf.interpret_feedback_text("It opened the wrong tab")
    assert accurate is False
    assert "wrong tab" in note


def test_load_task_actions_from_steps(tmp_path: Path):
    log_dir = tmp_path / "run"
    log_dir.mkdir()
    steps = log_dir / "steps.jsonl"
    steps.write_text(
        '{"n": 1, "kind": "computer_actions", "summary": "clicked"}\n'
        '{"n": 2, "kind": "message", "summary": "done"}\n',
        encoding="utf-8",
    )
    actions = tf.load_task_actions(str(log_dir))
    assert len(actions) == 2
    assert actions[0]["kind"] == "computer_actions"


def test_save_task_feedback_writes_files(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(tf, "LOGS_DIR", tmp_path / "logs")
    log_dir = tmp_path / "run"
    log_dir.mkdir()
    (log_dir / "steps.jsonl").write_text(
        '{"n": 1, "kind": "start", "summary": "begin"}\n',
        encoding="utf-8",
    )
    (log_dir / "task.json").write_text('{"task": "open browser"}\n', encoding="utf-8")

    payload = tf.save_task_feedback(
        goal="open browser",
        user_said="open browser",
        result="ok\nDone",
        log_dir=str(log_dir),
        run_id="fc_test",
        accurate=False,
        feedback="wrong page",
    )

    assert payload["action_count"] == 1
    feedback_file = json.loads((log_dir / "feedback.json").read_text(encoding="utf-8"))
    assert feedback_file["accurate"] is False
    assert feedback_file["feedback"] == "wrong page"
    assert feedback_file["goal"] == "open browser"

    meta = json.loads((log_dir / "task.json").read_text(encoding="utf-8"))
    assert meta["user_feedback"]["accurate"] is False

    lines = (tmp_path / "logs" / "feedback.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["run_id"] == "fc_test"


def test_format_feedback_for_model():
    assert "worked" in tf.format_feedback_for_model({"accurate": True, "skipped": False})
    text = tf.format_feedback_for_model({"accurate": False, "feedback": "bad diagram", "skipped": False})
    assert "NOT work" in text
    assert "bad diagram" in text


def test_collect_post_task_feedback_hears_yes(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(tf, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(tf, "TASK_FEEDBACK", True)
    client = MagicMock()
    with patch.object(tf, "speak", return_value=None), patch.object(
        tf, "listen_once", return_value="yeah that worked"
    ):
        payload = tf.collect_post_task_feedback(
            client,
            goal="draw diagram",
            user_said="draw diagram",
            result="ok",
            log_dir=None,
            run_id="fc_1",
        )
    assert payload["accurate"] is True
    assert payload["skipped"] is False
