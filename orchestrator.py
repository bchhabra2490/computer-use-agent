"""
Voice orchestrator: waits for a Jarvis wake word, then listens and routes via an LLM.

Tools:
  - start_task — hand off to the computer-use agent (background thread)
  - ask_user — speak a question and capture a spoken reply
  - give_response_to_user — speak a reply (optionally end the session)
  - list_memories / read_memory / save_memory / save_screen_memory — notes + screen snapshots

Idle and mid-task listening use local openWakeWord detection ("Hey Jarvis").
Cloud STT only runs after the wake word. While Jarvis is speaking, say
"Hey Jarvis" again (or press Space / Esc / Enter in the terminal) to interrupt
TTS and give a new command (barge-in).
When the agent calls ask_user, the question is spoken and answered here on
the main thread (no wake word required; barge-in still works).

Usage:
    export OPENAI_API_KEY=sk-...
    python orchestrator.py
    python orchestrator.py --auto
    python orchestrator.py --max-steps 25
"""

from __future__ import annotations

# Load .env before any module reads WAKE_* / OPENAI_* defaults.
from envfile import load_dotenv

load_dotenv()

import argparse
import json
import os
import re
import signal
import sys
import threading
import time
from typing import Any
from pathlib import Path

from openai import OpenAI

import agent as computer_agent
from app_status import log as status_log
from app_status import (
    active_agents,
    is_mark_done_utterance,
    mark_done_pending,
    quit_requested,
    register_orchestrator,
    remove_agent,
    request_mark_done,
    request_quit,
    set_and_log,
    set_state,
    unregister_orchestrator,
    upsert_agent,
)
from bus import (
    AgentMessageInbox,
    AgentMessagePublisher,
    AskUserBridge,
    strip_wake_prefix,
)
from memory import (
    MEMORY_TOOLS,
    capture_and_save_screen,
    format_memory_catalog,
    is_save_screen_utterance,
    run_memory_tool,
)
from skills import format_skill_catalog
from status_tray import ensure_tray_running
from stt import POST_TTS_COOLDOWN, ask_user, listen_for_utterance
from tts import speak
from wake import (
    WAKE_PHRASE,
    ensure_persistent_wake,
    format_wake_phrases,
    get_wake_remainder,
    stop_persistent_wake,
    wait_for_wake,
)

try:
    from low_latency_tts import LowLatencyTTS, decoded_message_prefix, extract_message_field
except Exception:  # pragma: no cover - optional at import time
    LowLatencyTTS = None  # type: ignore[misc, assignment]
    decoded_message_prefix = None  # type: ignore[misc, assignment]
    extract_message_field = None  # type: ignore[misc, assignment]

MODEL = os.environ.get("ORCHESTRATOR_MODEL", "gpt-5-mini")
TTS_STREAM = os.environ.get("TTS_STREAM", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}

START_TASK_TOOL = {
    "type": "function",
    "name": "start_task",
    "description": (
        "Start the computer-use agent to control the real desktop (mouse, "
        "keyboard, screenshots) for a concrete UI task. Use when the user wants "
        "something done on screen that you cannot answer with speech alone. "
        "The agent runs in the background; say the wake word then an instruction "
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

TOOLS = [START_TASK_TOOL, ASK_USER_TOOL, GIVE_RESPONSE_TOOL, *MEMORY_TOOLS]

SYSTEM_PROMPT = """You are a voice desktop orchestrator — a calm, concise Jarvis-like assistant.

You receive transcribed speech from the user. Decide the next action with tools only:
- give_response_to_user — speak an answer or acknowledgment (no desktop control)
- ask_user — ask one clarifying question when needed, then wait for their reply
- start_task — run the computer-use agent for real mouse/keyboard/UI work
- list_memories / read_memory / save_memory — personal facts and per-app notes
  under memory/ (see skill read-memory). Read before asking for a known preference;
  save when the user says remember/save this.
- save_screen_memory — screenshot the desktop, describe it, store under
  memory/screens/. Use when they say "save the screen as memory" (do not start_task).

Rules:
- Prefer give_response_to_user for questions you can answer without touching the computer.
- Prefer start_task for opening apps, browsing, clicking, reading on-screen content, etc.
- Call read_memory before ask_user when the missing detail may already be stored
  (name, usernames, usual apps, what was on screen). save_memory for durable
  facts they state. save_screen_memory when they want the current display stored.
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
- If they say "mark it done", "that's done", or "no other action is required"
  while a computer task is running, the runtime stops that task — do not
  start_task again for the same work.

Available desktop skills the computer agent can load:
{skills}

{memories}
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


def _create_response(
    client: OpenAI,
    *,
    llm_tts: Any | None = None,
    **kwargs: Any,
):
    """
    Create a Responses API turn.

    When streaming TTS is enabled, partial ``give_response_to_user`` message
    arguments are fed into LowLatencyTTS as they arrive. Falls back to a
    non-streaming create on error.
    """
    use_stream = bool(llm_tts is not None and TTS_STREAM and LowLatencyTTS is not None)
    if not use_stream:
        return client.responses.create(**kwargs)

    try:
        stream = client.responses.create(**kwargs, stream=True)
    except Exception as e:
        print(f"[orchestrator] stream create failed ({e}); falling back", flush=True)
        return client.responses.create(**kwargs)

    response_id: str | None = None
    # item_id -> {name, call_id, arguments}
    items: dict[str, dict[str, Any]] = {}
    final_response = None
    give_response_text = ""
    streamed_msg_len = 0

    def _is_give_response(meta: dict[str, Any]) -> bool:
        name = (meta.get("name") or "").strip()
        if name == "give_response_to_user":
            return True
        if name:
            return False
        # Name sometimes arrives after the first argument deltas — detect via JSON.
        if decoded_message_prefix is None:
            return False
        return bool(decoded_message_prefix(meta.get("arguments") or ""))

    def _feed_message_growth(meta: dict[str, Any]) -> None:
        nonlocal streamed_msg_len
        if response_id is None or decoded_message_prefix is None:
            return
        if not _is_give_response(meta):
            return
        if meta.get("call_id"):
            llm_tts.bind_call(response_id, str(meta["call_id"]))
        decoded = decoded_message_prefix(meta.get("arguments") or "")
        if len(decoded) > streamed_msg_len:
            llm_tts.add_text_chunk(decoded[streamed_msg_len:])
            streamed_msg_len = len(decoded)

    try:
        for event in stream:
            etype = getattr(event, "type", None)
            if etype == "response.created":
                response_id = event.response.id
                llm_tts.start_stream(response_id)
                print(f"[orchestrator] streaming response {response_id}", flush=True)
            elif etype == "response.output_item.added":
                item = event.item
                if getattr(item, "type", None) == "function_call":
                    items[item.id] = {
                        "name": getattr(item, "name", "") or "",
                        "call_id": getattr(item, "call_id", "") or "",
                        "arguments": getattr(item, "arguments", None) or "",
                    }
                    if (
                        response_id
                        and items[item.id]["name"] == "give_response_to_user"
                        and items[item.id]["call_id"]
                    ):
                        llm_tts.bind_call(response_id, items[item.id]["call_id"])
            elif etype == "response.function_call_arguments.delta":
                meta = items.get(event.item_id)
                if meta is None:
                    # Some SDK builds emit deltas before output_item.added — seed a stub.
                    meta = {"name": "", "call_id": "", "arguments": ""}
                    items[event.item_id] = meta
                meta["arguments"] = (meta.get("arguments") or "") + (event.delta or "")
                # Name / call_id may appear on the delta event itself.
                for attr in ("name", "call_id"):
                    val = getattr(event, attr, None)
                    if val and not meta.get(attr):
                        meta[attr] = val
                _feed_message_growth(meta)
            elif etype == "response.function_call_arguments.done":
                meta = items.get(event.item_id) or {"name": "", "call_id": "", "arguments": ""}
                meta["arguments"] = event.arguments or meta.get("arguments") or ""
                if getattr(event, "name", None):
                    meta["name"] = event.name
                if getattr(event, "call_id", None) and not meta.get("call_id"):
                    meta["call_id"] = event.call_id
                items[event.item_id] = meta
                if _is_give_response(meta):
                    if extract_message_field is not None:
                        give_response_text = extract_message_field(meta["arguments"])
                    _feed_message_growth(meta)
            elif etype == "response.output_item.done":
                item = getattr(event, "item", None)
                if item is not None and getattr(item, "type", None) == "function_call":
                    meta = items.get(item.id) or {"name": "", "call_id": "", "arguments": ""}
                    if getattr(item, "name", None):
                        meta["name"] = item.name
                    if getattr(item, "call_id", None):
                        meta["call_id"] = item.call_id
                    if getattr(item, "arguments", None):
                        meta["arguments"] = item.arguments
                    items[item.id] = meta
                    if _is_give_response(meta):
                        if extract_message_field is not None:
                            give_response_text = extract_message_field(meta.get("arguments") or "")
                        _feed_message_growth(meta)
            elif etype == "response.completed":
                final_response = event.response
            elif etype == "response.failed":
                print(f"[orchestrator] stream failed: {event}", flush=True)
    except Exception as e:
        print(f"[orchestrator] stream error ({e}); falling back", flush=True)
        if response_id and llm_tts is not None:
            try:
                # Do not flush partial speech — sync path will speak once.
                llm_tts.abandon(response_id)
            except Exception:
                pass
        return client.responses.create(**kwargs)

    if final_response is None:
        print("[orchestrator] stream ended without response.completed; falling back", flush=True)
        if response_id and llm_tts is not None:
            try:
                llm_tts.abandon(response_id)
            except Exception:
                pass
        return client.responses.create(**kwargs)

    if response_id and llm_tts is not None:
        # Prefer message extracted during stream; else scan final output.
        if not give_response_text and extract_message_field is not None:
            for item in final_response.output or []:
                if getattr(item, "type", None) == "function_call" and item.name == "give_response_to_user":
                    give_response_text = extract_message_field(item.arguments or "")
                    if getattr(item, "call_id", None):
                        llm_tts.bind_call(response_id, item.call_id)
                    break
        if give_response_text and len(give_response_text) > streamed_msg_len:
            llm_tts.add_text_chunk(give_response_text[streamed_msg_len:])
            streamed_msg_len = len(give_response_text)
        llm_tts.stop_stream()

    return final_response


def _start_agent_thread(
    job: AgentJob,
    *,
    auto: bool,
    max_steps: int,
    ask_bridge: AskUserBridge,
) -> None:
    upsert_agent(
        job.call_id,
        task=job.task,
        kind="computer-agent",
        status="running",
    )

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
                status_agent_id=job.call_id,
            )
        except BaseException as e:  # noqa: BLE001 — capture for main thread
            job.error = e
            job.result = f"failed\nError: {e}"
        finally:
            remove_agent(job.call_id)
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
    """Capture a command after TTS barge-in (wake or keyboard; no second wake)."""
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


def _save_screen_now(client: OpenAI, hint: str) -> str:
    """Capture + describe the display immediately (don't wait for start_task)."""
    set_and_log("thinking", "Saving screen as memory")
    try:
        result = capture_and_save_screen(client, hint=hint)
        print(f"[orchestrator] {result}", flush=True)
        return result
    except Exception as e:
        msg = f"Could not save screen memory: {e}"
        print(f"[orchestrator] {msg}", flush=True)
        return msg


def _speak(client: OpenAI, text: str) -> str | None:
    """
    Speak `text`. If the user barges in (wake word or keyboard), stop and listen.

    Returns the spoken command on barge-in, or None if playback finished normally.
    """
    if not text:
        return None
    set_state("speaking", text[:100])
    status_log(f"[tts] {text[:160]}")
    if speak(client, text):
        set_state("listening", "barge-in")
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
    set_and_log("ask", f"Agent asks: {question[:160]}")
    try:
        answer = ask_user(client, question)
    except Exception as e:
        answer = f"Error capturing answer: {e}"
        print(f"[orchestrator] ask_user failed: {e}")
    status_log(f"[ask_user] answer: {answer[:160]}")
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
    set_state("waiting", wake_prompt or f"Waiting for {format_wake_phrases()}")

    def _stop() -> bool:
        if quit_requested():
            return True
        if should_stop is not None:
            try:
                return bool(should_stop())
            except Exception:
                return True
        return False

    if not wait_for_wake(should_stop=_stop, prompt=wake_prompt):
        return None
    if quit_requested():
        return None
    set_and_log("listening", "Wake word heard — listening")
    remainder = get_wake_remainder()
    if remainder:
        return strip_wake_prefix(remainder).strip() or remainder
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
        f"[orchestrator] agent running — say {format_wake_phrases()} then an update; "
        "agent questions are spoken here automatically."
    )
    set_and_log("agent", f"Computer agent running: {job.task[:120]}", task=job.task)
    notified_done = False

    def _stop_for_done() -> bool:
        return job.done.is_set() or ask_bridge.has_pending() or quit_requested() or mark_done_pending(
            job.call_id
        )

    def _signal_agent_done(*, spoken: bool) -> None:
        nonlocal notified_done
        request_mark_done(job.call_id)
        if not notified_done:
            try:
                publisher.send(
                    "The user marked this task done. Stop all UI actions. "
                    "Call mark_done and do not continue."
                )
            except Exception as e:
                print(f"[orchestrator] bus send failed: {e}")
            notified_done = True
        if spoken:
            barged = _speak(client, "Marking it done.")
            if barged and not is_mark_done_utterance(barged):
                try:
                    publisher.send(barged)
                except Exception as e:
                    print(f"[orchestrator] bus send failed: {e}")

    while not job.done.is_set():
        if quit_requested():
            print("[orchestrator] quit requested — leaving agent supervision")
            break
        if mark_done_pending(job.call_id):
            print("[orchestrator] mark done requested — stopping computer agent")
            _signal_agent_done(spoken=False)
            # Agent consumes the flag on its next turn; keep supervising until it exits.
            time.sleep(0.2)
            continue
        if _service_agent_ask(client, ask_bridge):
            continue

        command = _listen_command(
            client,
            should_stop=_stop_for_done,
            wake_prompt=f"Waiting for {format_wake_phrases()}… (agent busy)",
            listen_prompt="Listening for mid-task update…",
        )
        if quit_requested():
            break
        if mark_done_pending(job.call_id):
            _signal_agent_done(spoken=False)
            continue
        if command is None:
            continue

        print(f'\n[user] "{command}"')
        status_log(f'[user] "{command}"')
        low = command.lower().strip()
        if is_mark_done_utterance(command):
            print("[orchestrator] user marked the running task done")
            _signal_agent_done(spoken=True)
            continue
        if is_save_screen_utterance(command):
            barged = _speak(client, "Saving the screen.")
            if barged:
                pending_cmd = barged
                if is_mark_done_utterance(pending_cmd):
                    _signal_agent_done(spoken=True)
                    continue
                if is_save_screen_utterance(pending_cmd):
                    command = pending_cmd
                else:
                    try:
                        publisher.send(pending_cmd)
                    except Exception as e:
                        print(f"[orchestrator] bus send failed: {e}")
                    continue
            result = _save_screen_now(client, command)
            ok = result.lower().startswith("saved")
            barged = _speak(client, "Saved." if ok else "Could not save the screen.")
            if barged:
                try:
                    publisher.send(barged)
                except Exception as e:
                    print(f"[orchestrator] bus send failed: {e}")
            continue
        if low in {"quit", "exit", "goodbye", "good bye", "stop listening"}:
            barged = _speak(
                client,
                "The computer task is still running. Say the wake word, then stop, "
                "if you want it to adapt.",
            )
            if barged:
                print(f'\n[user] "{barged}" (barge-in)')
                status_log(f'[user] "{barged}" (barge-in)')
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
            status_log(f"[bus] → agent: {command[:120]}")
        except Exception as e:
            print(f"[orchestrator] bus send failed: {e}")

    # Drain any last ask that arrived as the agent was finishing.
    while _service_agent_ask(client, ask_bridge):
        pass

    if job.thread is not None:
        job.thread.join(timeout=5.0)
    set_and_log("ready", "Computer agent finished")
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
    llm_tts: Any | None = None,
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

        already_streamed = bool(
            llm_tts is not None and getattr(call, "call_id", None) and llm_tts.took_call(call.call_id)
        )
        if message and already_streamed:
            # Playback may still be draining — wait, do not speak again.
            print("[orchestrator] give_response already streaming via low-latency TTS", flush=True)
            set_state("speaking", message[:100])
            interrupted = bool(llm_tts.wait_call(call.call_id))
            llm_tts.acknowledge_call(call.call_id)
            if interrupted:
                end_session = False
                set_state("listening", "barge-in")
                barge = _listen_after_barge(client)
                if barge:
                    output = (
                        f"Speech interrupted. User then said: {barge}. "
                        "Act on that instruction next (do not assume the spoken reply finished)."
                    )
                else:
                    output = (
                        "Speech interrupted but no follow-up command was heard. "
                        "Ask briefly what they need, or wait for the next wake."
                    )
            else:
                time.sleep(0.15)
                output = f"Spoke to user. end_session={end_session}"
        elif message:
            barge = _speak(client, message)
            if barge:
                end_session = False
                output = (
                    f"Speech interrupted. User then said: {barge}. "
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
                set_and_log("agent", f"Starting task: {task[:120]}", task=task)
                job = AgentJob(task=task, call_id=call.call_id)
                _start_agent_thread(job, auto=auto, max_steps=max_steps, ask_bridge=ask_bridge)
                # Defer function_call_output until the agent thread finishes.
                return None, False, job

    elif call.name in {
        "list_memories",
        "read_memory",
        "save_memory",
        "save_screen_memory",
    }:
        output = run_memory_tool(call.name, args, client=client)
        print(f"[orchestrator] {call.name}: {output[:160].replace(chr(10), ' ')}")

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
    llm_tts: Any | None = None,
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
                llm_tts=llm_tts,
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

        response = _create_response(
            client,
            llm_tts=llm_tts,
            model=MODEL,
            tools=TOOLS,
            previous_response_id=response.id,
            input=outputs,
        )
        if end_session:
            _print_messages(response)
            return response, True


def run_orchestrator(*, auto: bool, max_steps: int) -> None:
    ensure_tray_running()
    register_orchestrator()

    def _on_term(_signum=None, _frame=None) -> None:
        request_quit()
        print("\n[orchestrator] stop signal — shutting down…", flush=True)
        raise SystemExit(0)

    try:
        signal.signal(signal.SIGTERM, _on_term)
    except Exception:
        pass

    client = OpenAI()
    llm_tts = None
    if TTS_STREAM and LowLatencyTTS is not None:
        try:
            llm_tts = LowLatencyTTS(client, Path(__file__).resolve().parent)
            print("[orchestrator] low-latency TTS workers started", flush=True)
        except Exception as e:
            print(f"[orchestrator] low-latency TTS init failed ({e}); sync TTS only", flush=True)
            llm_tts = None

    skills = format_skill_catalog()
    memories = format_memory_catalog()
    system = SYSTEM_PROMPT.format(skills=skills, memories=memories)
    publisher = AgentMessagePublisher()
    ask_bridge = AskUserBridge()

    set_and_log("ready", "Orchestrator starting")
    print(f"[orchestrator] Wake phrases: {format_wake_phrases()} (mode from env / defaults)")
    # Arm wake BEFORE any TTS so barge-in covers synthesis + the ready line.
    if ensure_persistent_wake() is not None:
        print("[orchestrator] persistent wake barge-in armed", flush=True)
    # Do not speak the literal wake phrase — speaker echo false-triggers openWakeWord.
    pending = _speak(
        client,
        "Ready. Say the wake word, then tell me what you need.",
    )
    if pending is None:
        time.sleep(POST_TTS_COOLDOWN)

    previous_id: str | None = None
    task_history: list[dict[str, str]] = []

    try:
        while True:
            if quit_requested():
                print("[orchestrator] quit requested from menu bar.")
                set_and_log("done", "Quit from menu bar")
                return

            if pending is not None:
                utterance = pending
                pending = None
                print(f'\n[user] "{utterance}" (from barge-in)')
                status_log(f'[user] "{utterance}" (barge-in)')
            else:
                utterance = _listen_command(
                    client,
                    should_stop=quit_requested,
                    wake_prompt=f"Waiting for {format_wake_phrases()}…",
                    listen_prompt="Listening…",
                )
                if quit_requested():
                    print("[orchestrator] quit requested from menu bar.")
                    set_and_log("done", "Quit from menu bar")
                    return
                if utterance is None:
                    continue
                print(f'\n[user] "{utterance}"')
                status_log(f'[user] "{utterance}"')

            low = utterance.lower().strip()
            if is_mark_done_utterance(utterance):
                if active_agents():
                    request_mark_done()
                    barged = _speak(client, "Marking it done.")
                else:
                    barged = _speak(client, "Nothing is running.")
                if barged:
                    pending = barged
                continue
            if is_save_screen_utterance(utterance):
                barged = _speak(client, "Saving the screen.")
                if barged:
                    pending = barged
                    continue
                result = _save_screen_now(client, utterance)
                ok = result.lower().startswith("saved")
                barged = _speak(client, "Saved." if ok else "Could not save the screen.")
                if barged:
                    pending = barged
                continue
            if low in {"quit", "exit", "goodbye", "good bye", "stop listening"}:
                barged = _speak(client, "Goodbye.")
                if barged:
                    pending = barged
                    continue
                set_and_log("done", "Session ended")
                return

            set_state("thinking", utterance[:100])
            history_note = (
                f"User said: {utterance}\n\n" f"Computer task history so far:\n{_format_task_history(task_history)}"
            )

            if previous_id is None:
                response = _create_response(
                    client,
                    llm_tts=llm_tts,
                    model=MODEL,
                    tools=TOOLS,
                    instructions=system,
                    input=history_note,
                )
            else:
                response = _create_response(
                    client,
                    llm_tts=llm_tts,
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
                llm_tts=llm_tts,
            )
            previous_id = response.id

            if quit_requested():
                print("[orchestrator] quit requested from menu bar.")
                set_and_log("done", "Quit from menu bar")
                return

            if end_session:
                print("[orchestrator] session ended.")
                set_and_log("done", "Session ended")
                return

            print("[orchestrator] ready for next task.")
            set_state("ready", "Waiting for next request")
            time.sleep(POST_TTS_COOLDOWN)
    finally:
        if llm_tts is not None:
            try:
                llm_tts.close()
            except Exception as e:
                print(f"[orchestrator] TTS shutdown error: {e}", flush=True)
        try:
            stop_persistent_wake()
        except Exception:
            pass
        publisher.close()
        unregister_orchestrator()
        set_state("idle", "Orchestrator stopped")


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
