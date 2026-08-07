"""
Voice orchestrator: waits for a Jarvis wake word, then listens and routes via an LLM.

Tools:
  - start_task — hand off to the computer-use agent (background thread)
  - ask_user — speak a question and capture a spoken reply
  - give_response_to_user — speak a reply (optionally end the session)

Idle and mid-task listening use local openWakeWord detection ("Hey Jarvis").
Cloud STT only runs after the wake word. While Jarvis is speaking, say
"Hey Jarvis" again to interrupt TTS and give a new command (barge-in).
When the agent calls ask_user, the question is spoken and answered here on
the main thread (no wake word required; barge-in still works).

Usage:
    export OPENAI_API_KEY=sk-...
    python orchestrator.py
    python orchestrator.py --auto
    python orchestrator.py --max-steps 25
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from typing import Any

from openai import OpenAI

import agent as computer_agent
from bus import (
    AgentMessageInbox,
    AgentMessagePublisher,
    AskUserBridge,
    strip_wake_prefix,
)
from skills import format_skill_catalog
from stt import POST_TTS_COOLDOWN, ask_user, listen_for_utterance
from tts import speak
from wake import WAKE_PHRASE, wait_for_wake

MODEL = os.environ.get("ORCHESTRATOR_MODEL", "gpt-5-mini")

START_TASK_TOOL = {
    "type": "function",
    "name": "start_task",
    "description": (
        "Start the computer-use agent to control the real desktop (mouse, "
        "keyboard, screenshots) for a concrete UI task. Use when the user wants "
        "something done on screen that you cannot answer with speech alone. "
        "The agent runs in the background; say 'Hey Jarvis' then an instruction "
        "to send mid-task updates."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": (
                    "Clear natural-language instructions for the computer agent. "
                    "If continuing after a prior task, state only the remaining work "
                    "and do not redo completed steps."
                ),
            },
        },
        "required": ["task"],
        "additionalProperties": False,
    },
    "strict": True,
}

ASK_USER_TOOL = {
    "type": "function",
    "name": "ask_user",
    "description": (
        "Ask the user a clarifying question aloud and receive their spoken answer. "
        "Use before start_task when a preference, account, or choice is missing."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question to speak.",
            },
        },
        "required": ["question"],
        "additionalProperties": False,
    },
    "strict": True,
}

GIVE_RESPONSE_TOOL = {
    "type": "function",
    "name": "give_response_to_user",
    "description": (
        "Speak a response to the user (status, answer, greeting, or small talk). "
        "After finishing a normal request, set end_session=false so you can listen "
        "for the next task. Set end_session=true ONLY when the user says goodbye / quit."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "What to say aloud. Keep it concise.",
            },
            "end_session": {
                "type": "boolean",
                "description": (
                    "True only for goodbye/quit. False after answering a task so "
                    "listening continues for the next request."
                ),
            },
        },
        "required": ["message", "end_session"],
        "additionalProperties": False,
    },
    "strict": True,
}

TOOLS = [START_TASK_TOOL, ASK_USER_TOOL, GIVE_RESPONSE_TOOL]

SYSTEM_PROMPT = """You are a voice desktop orchestrator — a calm, concise Jarvis-like assistant.

You receive transcribed speech from the user. Decide the next action with tools only:
- give_response_to_user — speak an answer or acknowledgment (no desktop control)
- ask_user — ask one clarifying question when needed, then wait for their reply
- start_task — run the computer-use agent for real mouse/keyboard/UI work

Rules:
- Prefer give_response_to_user for questions you can answer without touching the computer.
- Prefer start_task for opening apps, browsing, clicking, reading on-screen content, etc.
- Call ask_user when a required detail is missing (which app, which account, confirm destructive work).
- Keep spoken messages short.
- After each start_task, you receive that task's result plus the full history of tasks
  already run in this session. Use that history to decide:
  - If the user's request is fully satisfied → give_response_to_user with the answer
    and end_session=false (keep listening for the next task).
  - If a distinct remaining step is still needed → start_task with only the leftover work.
  - Do not restart a task that already succeeded just to rephrase it.
- Stay in the conversation after completing work. Only set end_session=true when the
  user clearly says goodbye, quit, stop listening, or similar.
- While a computer task is running, the user can interrupt/update by saying
  the wake word ("Hey Jarvis") then an instruction — those go straight to the
  agent; you do not need to call tools for them.

Available desktop skills the computer agent can load:
{skills}
"""


class AgentJob:
    """Background computer-agent run + ZeroMQ inbox handle."""

    def __init__(self, task: str, call_id: str):
        self.task = task
        self.call_id = call_id
        self.done = threading.Event()
        self.result: str | None = None
        self.error: BaseException | None = None
        self.thread: threading.Thread | None = None

    @property
    def alive(self) -> bool:
        return self.thread is not None and self.thread.is_alive()


def _format_task_history(history: list[dict[str, str]]) -> str:
    if not history:
        return "(no computer tasks run yet in this session)"
    blocks: list[str] = []
    for i, entry in enumerate(history, start=1):
        blocks.append(f"### Task {i}\n" f"Request:\n{entry['task']}\n\n" f"Result:\n{entry['result']}")
    return "\n\n".join(blocks)


def _print_messages(response) -> None:
    for item in response.output:
        if item.type == "message":
            for part in item.content:
                if getattr(part, "type", None) == "output_text":
                    print(f"\n[orchestrator] {part.text}")


def _start_agent_thread(
    job: AgentJob,
    *,
    auto: bool,
    max_steps: int,
    ask_bridge: AskUserBridge,
) -> None:
    def _target() -> None:
        inbox = AgentMessageInbox()
        try:
            job.result = computer_agent.run(
                job.task,
                auto=auto,
                max_steps=max_steps,
                voice=False,
                message_inbox=inbox,
                ask_user_bridge=ask_bridge,
            )
        except BaseException as e:  # noqa: BLE001 — capture for main thread
            job.error = e
            job.result = f"failed\nError: {e}"
        finally:
            job.done.set()

    job.thread = threading.Thread(
        target=_target,
        name="computer-agent",
        daemon=True,
    )
    job.thread.start()


def _listen_after_barge(
    client: OpenAI,
    *,
    prompt: str = "Listening…",
) -> str | None:
    """Capture a command after TTS was interrupted by the wake word (no second wake)."""
    time.sleep(0.15)
    try:
        utterance = listen_for_utterance(client, prompt=prompt)
    except Exception as e:
        print(f"[orchestrator] listen after barge-in failed: {e}")
        return None
    command = strip_wake_prefix(utterance).strip()
    if not command:
        print("[orchestrator] barge-in heard but no command — listening again…")
        try:
            utterance = listen_for_utterance(
                client,
                prompt="Still listening for your command…",
            )
            command = strip_wake_prefix(utterance).strip()
        except Exception as e:
            print(f"[orchestrator] follow-up listen after barge-in failed: {e}")
            return None
    return command or None


def _speak(client: OpenAI, text: str) -> str | None:
    """
    Speak `text`. If the user says Hey Jarvis mid-speech, stop and listen.

    Returns the spoken command on barge-in, or None if playback finished normally.
    """
    if not text:
        return None
    if speak(client, text):
        return _listen_after_barge(client)
    return None


def _service_agent_ask(client: OpenAI, ask_bridge: AskUserBridge) -> bool:
    """If the agent is waiting on ask_user, speak/listen and reply. Returns True if handled."""
    req = ask_bridge.poll(timeout=0)
    if req is None:
        return False
    qid = req["id"]
    question = req["question"]
    print(f"\n[orchestrator] agent ask_user: {question}")
    try:
        answer = ask_user(client, question)
    except Exception as e:
        answer = f"Error capturing answer: {e}"
        print(f"[orchestrator] ask_user failed: {e}")
    ask_bridge.reply(qid, answer)
    return True


def _listen_command(
    client: OpenAI,
    *,
    should_stop=None,
    wake_prompt: str | None = None,
    listen_prompt: str | None = None,
) -> str | None:
    """Wake word → one cloud STT utterance. Returns None if stopped or empty."""
    if not wait_for_wake(should_stop=should_stop, prompt=wake_prompt):
        return None
    time.sleep(0.15)
    try:
        utterance = listen_for_utterance(
            client,
            prompt=listen_prompt or "Listening…",
        )
    except Exception as e:
        print(f"[orchestrator] listen after wake failed: {e}")
        return None
    command = strip_wake_prefix(utterance).strip()
    if not command:
        # STT may have only captured the wake phrase itself.
        print("[orchestrator] wake heard but no command — listening again…")
        try:
            utterance = listen_for_utterance(
                client,
                prompt="Still listening for your command…",
            )
            command = strip_wake_prefix(utterance).strip()
        except Exception as e:
            print(f"[orchestrator] follow-up listen failed: {e}")
            return None
    return command or None


def _supervise_agent(
    client: OpenAI,
    job: AgentJob,
    publisher: AgentMessagePublisher,
    ask_bridge: AskUserBridge,
) -> str:
    """
    Main-thread loop while the agent thread runs.
    Services agent ask_user; mid-task directives require the Jarvis wake word.
    """
    print(
        f"[orchestrator] agent running — say '{WAKE_PHRASE}' then an update; "
        "agent questions are spoken here automatically."
    )
    while not job.done.is_set():
        if _service_agent_ask(client, ask_bridge):
            continue

        command = _listen_command(
            client,
            should_stop=lambda: job.done.is_set() or ask_bridge.has_pending(),
            wake_prompt=f"Waiting for '{WAKE_PHRASE}'… (agent busy)",
            listen_prompt="Listening for mid-task update…",
        )
        if command is None:
            continue

        print(f'\n[user] "{command}"')
        low = command.lower().strip()
        if low in {"quit", "exit", "goodbye", "good bye", "stop listening"}:
            barged = _speak(
                client,
                "The computer task is still running. Say Hey Jarvis stop if you want it to adapt.",
            )
            if barged:
                print(f'\n[user] "{barged}" (barge-in)')
                try:
                    publisher.send(barged)
                    print(f"[orchestrator] forwarded to agent: {barged!r}")
                except Exception as e:
                    print(f"[orchestrator] bus send failed: {e}")
            else:
                time.sleep(POST_TTS_COOLDOWN)
            if job.done.is_set():
                break
            continue

        try:
            publisher.send(command)
            print(f"[orchestrator] forwarded to agent: {command!r}")
        except Exception as e:
            print(f"[orchestrator] bus send failed: {e}")

    # Drain any last ask that arrived as the agent was finishing.
    while _service_agent_ask(client, ask_bridge):
        pass

    if job.thread is not None:
        job.thread.join(timeout=5.0)
    return job.result or "failed\nError: no result from agent"


def _handle_tool(
    client: OpenAI,
    call,
    *,
    auto: bool,
    max_steps: int,
    task_history: list[dict[str, str]],
    publisher: AgentMessagePublisher,
    ask_bridge: AskUserBridge,
) -> tuple[dict | None, bool, AgentJob | None]:
    """
    Execute one tool call.
    Returns (function_call_output_or_None, end_session, deferred_agent_job).
    When start_task launches, output is None and the job must be supervised.
    """
    args = json.loads(call.arguments or "{}")
    end_session = False

    if call.name == "give_response_to_user":
        message = (args.get("message") or "").strip()
        end_session = bool(args.get("end_session"))
        farewell = bool(
            re.search(
                r"\b(goodbye|good bye|bye|quit|exit|stop listening|see you)\b",
                message.lower(),
            )
        )
        if end_session and not farewell:
            print("[orchestrator] ignoring end_session=true (not a farewell) — will listen again")
            end_session = False
        if message:
            barge = _speak(client, message)
            if barge:
                end_session = False
                output = (
                    f"Speech interrupted by wake word. User then said: {barge}. "
                    "Act on that instruction next (do not assume the spoken reply finished)."
                )
            else:
                time.sleep(0.2)
                output = f"Spoke to user. end_session={end_session}"
        else:
            output = f"Spoke to user. end_session={end_session}"
        print(f"[orchestrator] give_response_to_user → {output}")

    elif call.name == "ask_user":
        question = (args.get("question") or "").strip()
        if not question:
            output = "Error: empty question"
        else:
            output = ask_user(client, question)
            print(f"[orchestrator] ask_user answer: {output}")

    elif call.name == "start_task":
        task = (args.get("task") or "").strip()
        if not task:
            output = "Error: empty task"
        else:
            barge = _speak(client, "Starting that now.")
            if barge:
                print(f'\n[user] "{barge}" (barge-in before start_task)')
                output = (
                    "User interrupted before the computer agent started. "
                    f"They said: {barge}. Do not assume the task ran. "
                    "Decide next from their new instruction."
                )
            else:
                time.sleep(POST_TTS_COOLDOWN)
                print(f"\n[orchestrator] start_task: {task}")
                job = AgentJob(task=task, call_id=call.call_id)
                _start_agent_thread(job, auto=auto, max_steps=max_steps, ask_bridge=ask_bridge)
                # Defer function_call_output until the agent thread finishes.
                return None, False, job

    else:
        output = f"Unsupported tool: {call.name}"

    return (
        {
            "type": "function_call_output",
            "call_id": call.call_id,
            "output": output,
        },
        end_session,
        None,
    )


def _process_response(
    client: OpenAI,
    response,
    *,
    auto: bool,
    max_steps: int,
    task_history: list[dict[str, str]],
    publisher: AgentMessagePublisher,
    ask_bridge: AskUserBridge,
) -> tuple[Any, bool]:
    """
    Drain tool calls on `response` until the model stops calling tools.
    start_task runs the agent in a thread; this function blocks in a Jarvis
    listen loop until that agent finishes, then resumes the tool loop.
    """
    end_session = False
    while True:
        _print_messages(response)
        function_calls = [i for i in response.output if i.type == "function_call"]
        if not function_calls:
            return response, end_session

        outputs: list[dict] = []
        deferred_job: AgentJob | None = None

        for call in function_calls:
            out, stop, job = _handle_tool(
                client,
                call,
                auto=auto,
                max_steps=max_steps,
                task_history=task_history,
                publisher=publisher,
                ask_bridge=ask_bridge,
            )
            end_session = end_session or stop
            if job is not None:
                deferred_job = job
            elif out is not None:
                outputs.append(out)

        if deferred_job is not None:
            result = _supervise_agent(client, deferred_job, publisher, ask_bridge)
            task_history.append({"task": deferred_job.task, "result": result})
            history_blob = _format_task_history(task_history)
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": deferred_job.call_id,
                    "output": (
                        f"Computer agent finished this task.\n"
                        f"Latest result:\n{result}\n\n"
                        f"Session task history (use this to decide next action):\n"
                        f"{history_blob}\n\n"
                        "Decide next:\n"
                        "- If the user's request is fully satisfied, call "
                        "give_response_to_user with a short spoken summary.\n"
                        "- If distinct work remains, call start_task with only "
                        "the remaining step.\n"
                        "- Do not redo a task that already succeeded."
                    ),
                }
            )
            print(
                f"[orchestrator] task #{len(task_history)} finished "
                f"({(result or '').splitlines()[0] if result else 'empty'})"
            )

        if not outputs:
            return response, end_session

        response = client.responses.create(
            model=MODEL,
            tools=TOOLS,
            previous_response_id=response.id,
            input=outputs,
        )
        if end_session:
            _print_messages(response)
            return response, True


def run_orchestrator(*, auto: bool, max_steps: int) -> None:
    client = OpenAI()
    skills = format_skill_catalog()
    system = SYSTEM_PROMPT.format(skills=skills)
    publisher = AgentMessagePublisher()
    ask_bridge = AskUserBridge()

    pending = _speak(client, f"Ready. Say {WAKE_PHRASE}, then tell me what you need.")
    if pending is None:
        time.sleep(POST_TTS_COOLDOWN)

    previous_id: str | None = None
    task_history: list[dict[str, str]] = []

    try:
        while True:
            if pending is not None:
                utterance = pending
                pending = None
                print(f'\n[user] "{utterance}" (from barge-in)')
            else:
                utterance = _listen_command(
                    client,
                    wake_prompt=f"Waiting for '{WAKE_PHRASE}'…",
                    listen_prompt="Listening…",
                )
                if utterance is None:
                    continue
                print(f'\n[user] "{utterance}"')

            low = utterance.lower().strip()
            if low in {"quit", "exit", "goodbye", "good bye", "stop listening"}:
                barged = _speak(client, "Goodbye.")
                if barged:
                    pending = barged
                    continue
                return

            history_note = (
                f"User said: {utterance}\n\n" f"Computer task history so far:\n{_format_task_history(task_history)}"
            )

            if previous_id is None:
                response = client.responses.create(
                    model=MODEL,
                    tools=TOOLS,
                    instructions=system,
                    input=history_note,
                )
            else:
                response = client.responses.create(
                    model=MODEL,
                    tools=TOOLS,
                    instructions=system,
                    previous_response_id=previous_id,
                    input=history_note,
                )

            response, end_session = _process_response(
                client,
                response,
                auto=auto,
                max_steps=max_steps,
                task_history=task_history,
                publisher=publisher,
                ask_bridge=ask_bridge,
            )
            previous_id = response.id

            if end_session:
                print("[orchestrator] session ended.")
                return

            print("[orchestrator] ready for next task.")
            time.sleep(POST_TTS_COOLDOWN)
    finally:
        publisher.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Voice desktop orchestrator")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Pass --auto to the computer-use agent (skip per-step confirms)",
    )
    parser.add_argument("--max-steps", type=int, default=25)
    args = parser.parse_args(argv)

    try:
        run_orchestrator(auto=args.auto, max_steps=args.max_steps)
    except KeyboardInterrupt:
        print("\n[orchestrator] stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
