"""
Voice orchestrator: waits for a Jarvis wake word, then listens and routes via an LLM.

Tools:
  - who_am_i — read README.md and answer questions about this agent
  - start_task — hand off to the computer-use agent (background thread)
  - ask_user — speak a question and capture a spoken reply
  - give_response_to_user — speak a reply (optionally end the session)
  - list_memories / read_memory / save_memory / save_screen_memory — notes + screen snapshots
  - mcp_call — tools from servers in mcp.json (when configured)

Idle and mid-task listening use local openWakeWord detection ("Hey Jarvis").
Cloud STT only runs after the wake word. While Jarvis is speaking, say
"Hey Jarvis" again (or press Space / Esc / Enter in the terminal) to interrupt
TTS and give a new command (barge-in).
When the agent calls ask_user, the question is spoken and answered here on
the main thread (no wake word required; barge-in still works). If the model
dumps a question as a plain message or inside give_response_to_user, the
runtime still speaks it and listens without a wake word.

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
    TurnTrace,
    capture_and_save_screen,
    format_memory_catalog,
    is_save_screen_utterance,
    maybe_extract_run_memories,
    run_memory_tool,
)
from mcp_client import (
    format_mcp_catalog,
    mcp_openai_tools,
    run_mcp_tool,
    start_mcp,
    stop_mcp,
)
from skills import format_skill_catalog
from status_tray import ensure_tray_running
from stt import POST_TTS_COOLDOWN, ask_user, listen_for_utterance, listen_once
from tts import speak, speak_later
from whoami import WHO_AM_I_TOOL, run_whoami_tool
from displays import remember_monitor_layout
from wake import (
    WAKE_PHRASE,
    ensure_persistent_wake,
    format_wake_phrases,
    get_last_wake,
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
        "Ask the user a clarifying question aloud and capture their spoken answer "
        "immediately (no wake word). Required whenever you need a reply — never put "
        "questions in a plain assistant message or in give_response_to_user. Ask one "
        "short spoken question, not a numbered list."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": (
                    "One short question to speak. Natural wording; titles " "instead of raw URLs. Not a numbered list."
                ),
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
        "Speak the answer once, in one or two short sentences, then stop. "
        "Do not ask questions here (use ask_user). Do not say you will wait, "
        "that you are ready, or recap the same result a second time. "
        "Set end_session=true ONLY when the user says goodbye / quit."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": (
                    "What to say aloud. Speak like a person: short natural "
                    "sentences. Use titles and names, not raw URLs or https "
                    "links (painful to hear). No markdown."
                ),
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


def orchestrator_tools() -> list:
    return [
        WHO_AM_I_TOOL,
        START_TASK_TOOL,
        ASK_USER_TOOL,
        GIVE_RESPONSE_TOOL,
        *MEMORY_TOOLS,
        *mcp_openai_tools(for_agent=False),
    ]


SYSTEM_PROMPT = """You are a voice desktop orchestrator — a calm, concise Jarvis-like assistant.

You receive transcribed speech from the user. Decide the next action with tools only
— never reply with a plain assistant message (the user will not hear it, and the mic
will not open):
- give_response_to_user — speak an answer or acknowledgment that does not need a reply
- who_am_i — read README.md when they ask who you are, what you can do, or about this agent
- ask_user — ask one short clarifying question aloud, then listen for their answer
  (no wake word). Use this for any question, confirmation, or choice.
- start_task — run the computer-use agent for real mouse/keyboard/UI work
- list_memories / read_memory / save_memory — personal facts and per-app notes
  under memory/ (see skill read-memory). Read before asking for a known preference;
  save when the user says remember/save this.
- save_screen_memory — screenshot the desktop, describe it, store under
  memory/screens/. Use when they say "save the screen as memory" (do not start_task).
{mcp_rule}
Rules:
- Prefer give_response_to_user for questions you can answer without touching the computer.
- If they ask who you are, what you do, how you work, or about this agent / Jarvis /
  Rekha / computer-use-agent, call who_am_i first, then give_response_to_user with a
  short spoken summary from the README (do not read it verbatim, no markdown).
- Prefer mcp_call over start_task when a connected MCP server can search, fetch, or
  change the data (issues, docs, analytics, APIs). Use start_task only for real
  mouse/keyboard/UI work (open an app, click play, fill a form on screen).
- Prefer start_task for opening apps, browsing, clicking, reading on-screen content, etc.
- Call read_memory before ask_user when the missing detail may already be stored
  (name, usernames, usual apps, what was on screen). save_memory for durable
  facts they state. save_screen_memory when they want the current display stored.
- Call ask_user when a required detail is missing (which app, which account, confirm
  destructive work, how to split issues, labels). One short spoken question — never a
  numbered list in a message or in give_response_to_user.
- Keep spoken messages short. Write as if talking, not as a written report:
  titles and names instead of raw URLs or https links (those are painful to hear);
  no markdown, no reading out slugs or file paths unless asked.
  After give_response_to_user, STOP — do not emit a plain message or speak again.
  Never say “I’ll wait”, “I’m ready”, or repeat that you marked the task done.
- After each start_task, you receive that task's result plus the full history of tasks
  already run in this session. Use that history to decide:
  - If the user's request is fully satisfied → give_response_to_user ONCE with the
    outcome (one or two sentences) and stop. The runtime already listens next.
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
- When multiple displays are listed below, use that layout in start_task
  (which screen already has Chrome, Slack, etc.). Screenshots are primary-only.

Available desktop skills the computer agent can load:
{skills}

{memories}

{displays}

{mcp}
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


def _record_llm_step(turn: TurnTrace | None, response) -> None:
    if turn is None:
        return
    text = _assistant_message_text(response)
    if text:
        turn.add("llm_response", text)
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) != "function_call":
            continue
        name = getattr(item, "name", "") or "tool"
        args = getattr(item, "arguments", None) or ""
        turn.add("llm_tool_call", f"{name} {args}", max_len=2500)


def _assistant_message_text(response) -> str:
    """Plain assistant text from a Responses API turn (not tool-call arguments)."""
    parts: list[str] = []
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) != "message":
            continue
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", None) == "output_text":
                text = (getattr(part, "text", None) or "").strip()
                if text:
                    parts.append(text)
    return "\n".join(parts).strip()


_QUESTION_HINT = re.compile(
    r"\?"
    r"|^\s*\d+[.)]\s"
    r"|\b("
    r"which option|which should|do you want|should I|"
    r"confirm (the|that)|any default|quick questions?|"
    r"before I (create|do|start|open)|want me to"
    r")\b",
    re.IGNORECASE | re.MULTILINE,
)


def _looks_like_question(text: str) -> bool:
    """True when spoken text expects a reply (so we must open the mic)."""
    return bool(text and _QUESTION_HINT.search(text.strip()))


_WAIT_FILLER_RE = re.compile(
    r"(?is)"
    r"(?:\s*(?:"
    r"I(?:'ll| will) wait(?: for (?:any )?(?:further )?instructions?)?|"
    r"I(?:'m| am) ready(?: for (?:your )?next(?: task)?)?|"
    r"Let me know if you need anything else|"
    r"What(?:'s| is) next\??"
    r")\.?)+\s*$"
)


def _strip_wait_filler(text: str) -> str:
    """Drop trailing 'I'll wait / I'm ready' padding from a spoken reply."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    stripped = _WAIT_FILLER_RE.sub("", cleaned).strip()
    return stripped or cleaned


def _turn_already_spoke(turn: TurnTrace | None) -> bool:
    if turn is None:
        return False
    return any(kind == "spoken" for kind, _ in turn.steps)


def _give_response_closes_turn(call, out: dict | None) -> bool:
    """True when a statement was spoken and the model must not talk again."""
    if getattr(call, "name", None) != "give_response_to_user" or not out:
        return False
    text = str(out.get("output") or "")
    if "captured their answer" in text or text.startswith("Speech interrupted"):
        return False
    return text.startswith("Spoke to user")


def _listen_for_answer(client: OpenAI) -> str:
    """Capture a spoken reply without requiring the wake word."""
    return listen_once(
        client,
        mode="freeform",
        prompt="Listening for your answer… (sends after 3s without new words)",
    )


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
                    if response_id and items[item.id]["name"] == "give_response_to_user" and items[item.id]["call_id"]:
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


def _speak_later(client: OpenAI, text: str) -> None:
    """Start TTS without blocking the agent / tool loop."""
    if not text:
        return
    set_state("speaking", text[:100])
    status_log(f"[tts] {text[:160]}")
    speak_later(client, text)


def _confirm_heard_enabled() -> bool:
    return os.environ.get("TTS_CONFIRM_HEARD", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _heard_confirm_line(text: str) -> str:
    """One short TTS sentence restating what STT captured."""
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return ""
    if len(cleaned) > 160:
        cut = cleaned[:157].rsplit(" ", 1)[0].rstrip(",.;:")
        cleaned = (cut or cleaned[:157]) + "…"
    return f"I heard: {cleaned}."


def _confirm_heard(client: OpenAI, utterance: str) -> str:
    """
    After listening ends, speak back what was understood in one sentence.

    If the user barges in during that line, return their new command (no second confirm).
    """
    if not utterance or not _confirm_heard_enabled():
        return utterance
    line = _heard_confirm_line(utterance)
    if not line:
        return utterance
    barged = _speak(client, line)
    if barged:
        return barged
    time.sleep(POST_TTS_COOLDOWN)
    return utterance


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
    hit = get_last_wake()
    heard = hit.label if hit else "Wake word"
    set_and_log("listening", f"{heard} heard — listening")
    remainder = get_wake_remainder()
    if remainder:
        return strip_wake_prefix(remainder).strip() or remainder
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
        return job.done.is_set() or ask_bridge.has_pending() or quit_requested() or mark_done_pending(job.call_id)

    def _signal_agent_done(*, spoken: bool) -> None:
        nonlocal notified_done
        request_mark_done(job.call_id)
        if not notified_done:
            try:
                publisher.send(
                    "The user marked this task done. Stop all UI actions. " "Call mark_done and do not continue."
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

        command = _confirm_heard(client, command)
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
                "The computer task is still running. Say the wake word, then stop, " "if you want it to adapt.",
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
    turn: TurnTrace | None = None,
) -> tuple[dict | None, bool, AgentJob | None]:
    """
    Execute one tool call.
    Returns (function_call_output_or_None, end_session, deferred_agent_job).
    When start_task launches, output is None and the job must be supervised.
    """
    args = json.loads(call.arguments or "{}")
    end_session = False

    if call.name == "give_response_to_user":
        message = _strip_wait_filler((args.get("message") or "").strip())
        if turn is not None and message:
            turn.add("spoken", message)
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
        handled_barge = False
        if message and already_streamed:
            # Playback continues on the TTS worker — do not block the agent.
            print(
                "[orchestrator] give_response already streaming via low-latency TTS " "(not waiting)",
                flush=True,
            )
            set_state("speaking", message[:100])
            if _looks_like_question(message) and not end_session:
                interrupted = bool(llm_tts.wait_call(call.call_id))
                llm_tts.acknowledge_call(call.call_id)
                if interrupted:
                    handled_barge = True
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
                    output = f"Spoke to user. end_session={end_session}"
            else:
                llm_tts.acknowledge_call(call.call_id)
                output = f"Spoke to user. end_session={end_session}"
        elif message:
            if _looks_like_question(message) and not end_session:
                barge = _speak(client, message)
                if barge:
                    handled_barge = True
                    end_session = False
                    output = (
                        f"Speech interrupted. User then said: {barge}. "
                        "Act on that instruction next (do not assume the spoken reply finished)."
                    )
                else:
                    output = f"Spoke to user. end_session={end_session}"
            else:
                _speak_later(client, message)
                output = f"Spoke to user. end_session={end_session}"
        else:
            output = f"Spoke to user. end_session={end_session}"

        # give_response does not open the mic. If the model asked a question
        # here anyway, listen without a wake word so the user can answer.
        if not handled_barge and not end_session and message and _looks_like_question(message):
            print(
                "[orchestrator] give_response asked a question — " "listening without wake word",
                flush=True,
            )
            answer = _listen_for_answer(client)
            output = (
                f"Spoke to user, then captured their answer (no wake word): {answer}. "
                "Continue with that answer. Further questions must use ask_user "
                "(one short spoken question, not a numbered list)."
            )
        print(f"[orchestrator] give_response_to_user → {output}")

    elif call.name == "ask_user":
        question = (args.get("question") or "").strip()
        if not question:
            output = "Error: empty question"
        else:
            output = ask_user(client, question)
            print(f"[orchestrator] ask_user answer: {output}")
            if turn is not None:
                turn.add("ask_user", f"Q: {question}\nA: {output}")

    elif call.name == "start_task":
        task = (args.get("task") or "").strip()
        if not task:
            output = "Error: empty task"
        else:
            print(f"\n[orchestrator] start_task: {task}")
            set_and_log("agent", f"Starting task: {task[:120]}", task=task)
            job = AgentJob(task=task, call_id=call.call_id)
            _start_agent_thread(job, auto=auto, max_steps=max_steps, ask_bridge=ask_bridge)
            _speak_later(client, "Starting that now.")
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

    elif call.name == "who_am_i":
        output = run_whoami_tool(call.name, args)
        print(f"[orchestrator] who_am_i: {output[:120].replace(chr(10), ' ')}")

    elif call.name == "mcp_call":
        output = run_mcp_tool(call.name, args)
        print(f"[orchestrator] mcp_call: {output[:160].replace(chr(10), ' ')}")

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
    turn: TurnTrace | None = None,
) -> tuple[Any, bool, list[dict]]:
    """
    Drain tool calls on `response` until the model stops calling tools.
    start_task runs the agent in a thread; this function blocks in a Jarvis
    listen loop until that agent finishes, then resumes the tool loop.

    The third value is function_call_output items that must be sent on the
    next user turn when we already spoke and skipped a recap model call.
    """
    end_session = False
    while True:
        _print_messages(response)
        _record_llm_step(turn, response)
        function_calls = [i for i in response.output if i.type == "function_call"]
        if not function_calls:
            leftover = _assistant_message_text(response)
            already_spoke = _turn_already_spoke(turn)
            if leftover and _looks_like_question(leftover) and not already_spoke:
                print(
                    "[orchestrator] model asked in a message instead of ask_user — "
                    "speaking and listening without wake word",
                    flush=True,
                )
                answer = ask_user(client, leftover)
                if turn is not None:
                    turn.add("ask_user", f"Q: {leftover}\nA: {answer}")
                response = _create_response(
                    client,
                    llm_tts=llm_tts,
                    model=MODEL,
                    tools=orchestrator_tools(),
                    previous_response_id=response.id,
                    input=(
                        f"User answered: {answer}\n\n"
                        "Continue the task with this answer. Never put questions in a "
                        "plain message; call ask_user (one short question) or "
                        "give_response_to_user (statements only)."
                    ),
                )
                continue
            if leftover and not already_spoke:
                print(
                    "[orchestrator] model replied with a message instead of "
                    "give_response_to_user — speaking it in the background",
                    flush=True,
                )
                _speak_later(client, leftover)
            elif leftover and already_spoke:
                print(
                    "[orchestrator] skipping leftover message " "(already spoke this turn)",
                    flush=True,
                )
            return response, end_session, []

        outputs: list[dict] = []
        deferred_job: AgentJob | None = None
        close_after_speech = False

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
                turn=turn,
            )
            end_session = end_session or stop
            if job is not None:
                deferred_job = job
                if turn is not None:
                    turn.add("start_task", job.task)
            elif out is not None:
                outputs.append(out)
                if turn is not None:
                    result_text = str(out.get("output") or "")
                    turn.add("tool_result", f"{call.name}: {result_text}", max_len=3000)
                if _give_response_closes_turn(call, out):
                    close_after_speech = True

        if deferred_job is not None:
            result = _supervise_agent(client, deferred_job, publisher, ask_bridge)
            task_history.append({"task": deferred_job.task, "result": result})
            if turn is not None:
                turn.add("start_task_result", result or "", max_len=4000)
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
                        "give_response_to_user ONCE with a short spoken summary "
                        "(titles/names, not raw URLs), then stop. Do not recap "
                        "again in a message.\n"
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
            close_after_speech = False

        if close_after_speech:
            print(
                "[orchestrator] already spoke — not asking the model to recap",
                flush=True,
            )
            return response, end_session, outputs

        if not outputs:
            return response, end_session, []

        response = _create_response(
            client,
            llm_tts=llm_tts,
            model=MODEL,
            tools=orchestrator_tools(),
            previous_response_id=response.id,
            input=outputs,
        )
        if end_session:
            _print_messages(response)
            _record_llm_step(turn, response)
            return response, True, []


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

    start_mcp()
    mcp_rule = ""
    if mcp_openai_tools(for_agent=False):
        mcp_rule = (
            "- mcp_call — call a tool on a connected MCP server (search, GitHub, "
            "Linear, docs, APIs). Prefer this over start_task when it can complete "
            "the request.\n"
        )

    def _system_prompt() -> str:
        occupancy = remember_monitor_layout()
        # Occupancy text can contain `{` from window titles; inject after format.
        return (
            SYSTEM_PROMPT.replace("{displays}", "__DISPLAYS__")
            .format(
                skills=format_skill_catalog(),
                memories=format_memory_catalog(),
                mcp=format_mcp_catalog(),
                mcp_rule=mcp_rule,
            )
            .replace("__DISPLAYS__", occupancy)
        )

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
    pending_fn_outputs: list[dict] = []

    try:
        while True:
            if quit_requested():
                print("[orchestrator] quit requested from menu bar.")
                set_and_log("done", "Quit from menu bar")
                return

            if pending is not None:
                utterance = pending
                pending = None
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

            utterance = _confirm_heard(client, utterance)
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
            turn = TurnTrace(utterance)
            system = _system_prompt()
            if pending_fn_outputs:
                turn_input: Any = [
                    *pending_fn_outputs,
                    {"role": "user", "content": history_note},
                ]
                pending_fn_outputs = []
            else:
                turn_input = history_note

            if previous_id is None:
                response = _create_response(
                    client,
                    llm_tts=llm_tts,
                    model=MODEL,
                    tools=orchestrator_tools(),
                    instructions=system,
                    input=turn_input,
                )
            else:
                response = _create_response(
                    client,
                    llm_tts=llm_tts,
                    model=MODEL,
                    tools=orchestrator_tools(),
                    instructions=system,
                    previous_response_id=previous_id,
                    input=turn_input,
                )

            response, end_session, pending_fn_outputs = _process_response(
                client,
                response,
                auto=auto,
                max_steps=max_steps,
                task_history=task_history,
                publisher=publisher,
                ask_bridge=ask_bridge,
                llm_tts=llm_tts,
                turn=turn,
            )
            previous_id = response.id
            maybe_extract_run_memories(
                user_input=utterance,
                transcript=turn.as_text(),
            )

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
        try:
            stop_mcp()
        except Exception as e:
            print(f"[orchestrator] MCP shutdown error: {e}", flush=True)
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
