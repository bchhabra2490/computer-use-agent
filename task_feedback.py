"""
Post-task user feedback: spoken prompt, persisted with goal and action log.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI

from stt import POST_TTS_COOLDOWN, NoSpeechError, classify_yes_no, listen_once, speak
from task_log import LOGS_DIR

TASK_FEEDBACK = os.environ.get("TASK_FEEDBACK", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}


def feedback_enabled() -> bool:
    return TASK_FEEDBACK


def load_task_actions(log_dir: str | None) -> list[dict[str, Any]]:
    if not log_dir:
        return []
    steps_path = Path(log_dir) / "steps.jsonl"
    if not steps_path.is_file():
        return []
    actions: list[dict[str, Any]] = []
    for line in steps_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            actions.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return actions


def interpret_feedback_text(text: str) -> tuple[bool | None, str]:
    """
    Map a spoken reply to (accurate, note).
    accurate: True = worked, False = did not, None = unclear / skipped marker.
    """
    raw = (text or "").strip()
    if not raw:
        return None, ""

    kind = classify_yes_no(raw)
    if kind == "yes":
        return True, ""
    if kind == "no":
        return False, ""
    if kind in {"quit", "retry"}:
        return None, raw

    low = raw.lower()
    if any(p in low for p in ("wrong", "incorrect", "not right", "didn't work", "did not work", "failed", "missed")):
        return False, raw
    if len(raw) > 12:
        return False, raw
    return None, raw


def save_task_feedback(
    *,
    goal: str,
    user_said: str,
    result: str,
    log_dir: str | None,
    run_id: str,
    accurate: bool | None,
    feedback: str,
    skipped: bool = False,
    skip_reason: str = "",
) -> dict[str, Any]:
    """Write feedback.json in the task log dir and append logs/feedback.jsonl."""
    now = datetime.now(timezone.utc).isoformat()
    actions = load_task_actions(log_dir)
    payload: dict[str, Any] = {
        "ts": now,
        "run_id": run_id,
        "goal": goal,
        "user_said": user_said,
        "result": result,
        "accurate": accurate,
        "feedback": feedback,
        "skipped": skipped,
        "skip_reason": skip_reason,
        "log_dir": log_dir,
        "action_count": len(actions),
        "actions": actions,
    }

    if log_dir:
        log_path = Path(log_dir)
        if log_path.is_dir():
            (log_path / "feedback.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            meta_path = log_path / "task.json"
            if meta_path.is_file():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    meta = {}
                meta["user_feedback"] = {
                    "accurate": accurate,
                    "feedback": feedback,
                    "skipped": skipped,
                    "recorded_at": now,
                }
                meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with (LOGS_DIR / "feedback.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    label = "yes" if accurate is True else "no" if accurate is False else "skipped" if skipped else "unclear"
    note = f'; note="{feedback[:80]}"' if feedback else ""
    print(f"[feedback] task {run_id}: accurate={label}{note}", flush=True)
    return payload


def format_feedback_for_model(payload: dict[str, Any]) -> str:
    if payload.get("skipped"):
        reason = payload.get("skip_reason") or "not collected"
        return f"Post-task user feedback: skipped ({reason})."
    accurate = payload.get("accurate")
    if accurate is True:
        return "Post-task user feedback: user said the task worked."
    if accurate is False:
        note = (payload.get("feedback") or "").strip()
        if note:
            return f"Post-task user feedback: user said it did NOT work. Correction: {note}"
        return "Post-task user feedback: user said it did NOT work."
    note = (payload.get("feedback") or "").strip()
    if note:
        return f"Post-task user feedback: unclear yes/no; user said: {note}"
    return "Post-task user feedback: unclear (no response)."


def collect_post_task_feedback(
    client: OpenAI,
    *,
    goal: str,
    user_said: str,
    result: str,
    log_dir: str | None,
    run_id: str,
    speak_fn: Callable[..., str | None] | None = None,
    should_skip: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Ask the user whether the task worked; persist with goal and actions."""
    if not feedback_enabled():
        return save_task_feedback(
            goal=goal,
            user_said=user_said,
            result=result,
            log_dir=log_dir,
            run_id=run_id,
            accurate=None,
            feedback="",
            skipped=True,
            skip_reason="TASK_FEEDBACK disabled",
        )

    if should_skip is not None and should_skip():
        return save_task_feedback(
            goal=goal,
            user_said=user_said,
            result=result,
            log_dir=log_dir,
            run_id=run_id,
            accurate=None,
            feedback="",
            skipped=True,
            skip_reason="quit or interrupt",
        )

    _speak = speak_fn or speak
    prompt = "Did that work? Say yes, or tell me what went wrong."
    print(f"\n[feedback] {prompt}", flush=True)
    barged = _speak(client, prompt)
    if barged:
        accurate, note = interpret_feedback_text(barged)
        if accurate is not None or note:
            return save_task_feedback(
                goal=goal,
                user_said=user_said,
                result=result,
                log_dir=log_dir,
                run_id=run_id,
                accurate=accurate,
                feedback=note,
            )
    elif not barged:
        time.sleep(POST_TTS_COOLDOWN)

    if should_skip is not None and should_skip():
        return save_task_feedback(
            goal=goal,
            user_said=user_said,
            result=result,
            log_dir=log_dir,
            run_id=run_id,
            accurate=None,
            feedback="",
            skipped=True,
            skip_reason="quit or interrupt",
        )

    try:
        heard = listen_once(
            client,
            mode="freeform",
            max_attempts=2,
            prompt="Listening for feedback… (yes, or what went wrong)",
        )
    except NoSpeechError:
        return save_task_feedback(
            goal=goal,
            user_said=user_said,
            result=result,
            log_dir=log_dir,
            run_id=run_id,
            accurate=None,
            feedback="",
            skipped=True,
            skip_reason="no speech",
        )

    accurate, note = interpret_feedback_text(heard)
    if accurate is False and not note:
        follow = "What was wrong?"
        print(f"\n[feedback] {follow}", flush=True)
        barged2 = _speak(client, follow)
        if barged2:
            note = barged2.strip()
        else:
            time.sleep(POST_TTS_COOLDOWN)
            if should_skip is not None and should_skip():
                return save_task_feedback(
                    goal=goal,
                    user_said=user_said,
                    result=result,
                    log_dir=log_dir,
                    run_id=run_id,
                    accurate=False,
                    feedback="",
                    skipped=True,
                    skip_reason="quit before follow-up",
                )
            try:
                note = listen_once(
                    client,
                    mode="freeform",
                    max_attempts=2,
                    prompt="Listening…",
                ).strip()
            except NoSpeechError:
                note = ""

    if accurate is None and note:
        accurate = False

    return save_task_feedback(
        goal=goal,
        user_said=user_said,
        result=result,
        log_dir=log_dir,
        run_id=run_id,
        accurate=accurate,
        feedback=note,
    )
