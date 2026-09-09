"""Background computer-agent job supervisor.

The orchestrator still decides *when* to launch a job. This module owns the
job object and the worker thread that runs ``agent.run``.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from app_status import remove_agent, upsert_agent
from bus import AgentMessageInbox, AskUserBridge


class AgentJob:
    """Background computer-agent run + ZeroMQ inbox handle."""

    def __init__(
        self,
        task: str,
        call_id: str,
        *,
        match_text: str | None = None,
        speaker_context: str = "",
    ):
        self.task = task
        self.match_text = (match_text or task).strip() or task
        self.speaker_context = (speaker_context or "").strip()
        self.call_id = call_id
        self.done = threading.Event()
        self.result: str | None = None
        self.error: BaseException | None = None
        self.thread: threading.Thread | None = None
        self.redirected_from_barge = False
        self.log_dir: str | None = None
        self.reply_sink: str = "mac"
        self.feedback_payload: dict[str, Any] | None = None

    @property
    def alive(self) -> bool:
        return self.thread is not None and self.thread.is_alive()


def start_agent_thread(
    job: AgentJob,
    *,
    auto: bool,
    max_steps: int,
    ask_bridge: AskUserBridge,
    run_agent: Callable[..., str] | None = None,
) -> None:
    """Start the computer-agent worker and register it in the tray."""
    if run_agent is None:
        import agent as computer_agent

        run = computer_agent.run
    else:
        run = run_agent
    upsert_agent(
        job.call_id,
        task=job.task,
        kind="computer-agent",
        status="running",
    )

    def _target() -> None:
        try:
            try:
                inbox = AgentMessageInbox()

                def _on_log_dir(path: str) -> None:
                    job.log_dir = path

                job.result = run(
                    job.task,
                    auto=auto,
                    max_steps=max_steps,
                    voice=False,
                    message_inbox=inbox,
                    ask_user_bridge=ask_bridge,
                    status_agent_id=job.call_id,
                    user_said=job.match_text,
                    speaker_context=job.speaker_context,
                    on_log_dir=_on_log_dir,
                    latency_trace_id=getattr(job, "latency_trace_id", None),
                    execution_route=getattr(job, "execution_route", None),
                )
            except BaseException as e:  # noqa: BLE001 — capture for main thread
                job.error = e
                job.result = f"failed\nError: {e}"
            try:
                from latency_report import finish_trace

                finish_trace(
                    getattr(job, "latency_trace_id", None),
                    status="failed" if job.error is not None else "completed",
                    task=job.task,
                    metadata={"result": (job.result or "")[:160]},
                )
            except Exception as e:
                print(f"[agent] finish_trace failed: {e}", flush=True)
            try:
                remove_agent(job.call_id)
            except Exception as e:
                print(f"[agent] remove_agent failed: {e}", flush=True)
        finally:
            job.done.set()

    job.thread = threading.Thread(
        target=_target,
        name="computer-agent",
        daemon=True,
    )
    job.thread.start()
