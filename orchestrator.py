"""
Voice orchestrator: waits for a Jarvis wake word, then listens and routes via an LLM.

Tools:
  - who_am_i — read README.md and answer questions about this agent
  - start_task — hand off to the computer-use agent (background thread)
  - ask_user — speak a question and capture a spoken reply
  - give_response_to_user — speak a reply (optionally end the session)
  - list_memories / read_memory / save_memory / save_screen_memory / read_screen — notes + screen snapshots
  - list_open_apps — running apps, windows by display, and open browser tabs
  - set_timer / list_timers / cancel_timer — native countdown (no Clock UI)
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
import base64
import json
import os
import re
import signal
import sys
import threading
import time
from typing import Any, Callable
from pathlib import Path

from openai import OpenAI

from llm_client import (
    fold_orphan_tool_outputs,
    input_has_image,
    make_llm_client,
    merge_tool_followup_input,
    model_for_request,
    orchestrator_provider,
    supports_previous_response_id,
)

import agent as computer_agent
from app_status import log as status_log
from app_status import (
    active_agents,
    clear_phone_photo,
    consume_utterance,
    is_mark_done_utterance,
    log_llm,
    mark_done_pending,
    phone_photo_jpeg,
    phone_photo_pending,
    quit_requested,
    register_orchestrator,
    remove_agent,
    request_mark_done,
    request_quit,
    reply_sink,
    reply_to_chat,
    reply_tts_enabled,
    set_chat_stream,
    set_last_spoken,
    set_reply_sink,
    set_turn_source,
    speak_pending,
    speak_pending,
    consume_speak,
    take_turn_chat_screenshot,
    unregister_orchestrator,
    upsert_agent,
    utterance_pending,
)
from bus import (
    AgentMessageInbox,
    AgentMessagePublisher,
    AskUserBridge,
    strip_wake_prefix,
)
from audio import AudioSession, bind_audio, get_audio
from checkpoint import run_orchestrator_checkpoint
from context import assemble_context, read_screen_vision_input
from events import emit
from input_queues import (
    classify_utterance_for_agent,
    get_next_run_queue,
)
from memory import (
    TurnTrace,
    capture_and_save_screen,
    is_save_screen_utterance,
    maybe_extract_run_memories,
)
from mcp_client import (
    mcp_openai_tools,
    start_mcp,
    stop_mcp,
)
from orchestrator_prompts import build_system_prompt, local_datetime_line
from session import Session, bind_session, get_session
from session_compact import (
    SessionCompactState,
    format_task_history_block,
    is_context_overflow_error,
)
from phone_gateway import ensure_phone_gateway, stop_phone_gateway
from status_tray import ensure_tray_running, stop_tray
from dictation import ensure_dictation_running, stop_dictation
from stt import POST_TTS_COOLDOWN, NoSpeechError, ask_user, listen_once
from task_spec import resolve_agent_task
from task_feedback import collect_post_task_feedback, format_feedback_for_model
from tools_registry import orchestrator_tools, run_tool
from barge_router import classify_barge_utterance
from wake import (
    format_wake_phrases,
)

try:
    from tts.low_latency import LowLatencyTTS, decoded_message_prefix, extract_message_field
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

_CREDIT_MARKERS = (
    "no credits remaining",
    "insufficient_quota",
    "credit_balance_exhausted",
    "insufficient_funds",
    "billing_hard_limit",
)
_AUTH_MARKERS = (
    "invalid_api_key",
    "incorrect api key",
    "invalid api key",
    "authentication",
)


class LlmUnavailableError(RuntimeError):
    """LLM call failed; speak it and return to the wake loop instead of crashing."""


def _exception_blob(exc: BaseException) -> str:
    parts = [type(exc).__name__, str(exc)]
    body = getattr(exc, "body", None)
    if body is not None:
        parts.append(str(body))
    for attr in ("code", "type", "message"):
        val = getattr(exc, attr, None)
        if val:
            parts.append(str(val))
    return " ".join(parts)


def is_fatal_llm_error(exc: BaseException) -> bool:
    """Quota / auth failures will also fail the non-streaming fallback."""
    blob = _exception_blob(exc).lower()
    if any(m in blob for m in _CREDIT_MARKERS + _AUTH_MARKERS):
        return True
    status = getattr(exc, "status_code", None)
    if status in {401, 403}:
        return True
    if status == 429 and any(m in blob for m in ("quota", "credit", "billing", "balance")):
        return True
    name = type(exc).__name__.lower()
    if name in {"authenticationerror", "permissiondeniederror"}:
        return True
    if name == "ratelimiterror" and any(m in blob for m in _CREDIT_MARKERS + ("quota", "credit", "billing")):
        return True
    return False


def llm_error_speech(exc: BaseException) -> str:
    """Short spoken form of a reasoning-API error (no URLs)."""
    if isinstance(exc, LlmUnavailableError):
        text = str(exc).strip()
        return text or "The language model could not complete that."
    blob = _exception_blob(exc)
    match = re.search(r"['\"]message['\"]\s*:\s*['\"]([^'\"]+)['\"]", blob)
    if match:
        msg = re.sub(r"https?://\S+", "", match.group(1)).strip()
        msg = re.sub(r"\s+", " ", msg).strip(" .")
        if msg:
            return msg + "."
    lower = blob.lower()
    if any(m in lower for m in _CREDIT_MARKERS):
        return "You have no credits remaining. Add credits to continue using the API."
    provider = orchestrator_provider()
    vendor = "DeepSeek" if provider == "deepseek" else "OpenAI"
    if any(m in lower for m in _AUTH_MARKERS):
        return f"The {vendor} API key is invalid. Check your environment file."
    brief = re.sub(r"https?://\S+", "", str(exc))
    brief = re.sub(r"\s+", " ", brief).strip()
    if len(brief) > 180:
        brief = brief[:177].rstrip() + "…"
    return f"I hit a {vendor} error. {brief}" if brief else f"I hit a {vendor} error and could not complete that."


_phone_photo_in_session = False


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


def _format_task_history(
    history: list[dict[str, str]],
    *,
    task_summary: str = "",
) -> str:
    return format_task_history_block(history, task_summary=task_summary)


def _clear_speaker_tag() -> None:
    """Drop stale voice-ID state when this utterance had no local mic clip."""
    try:
        from speaker_id import clear_last_speaker

        clear_last_speaker()
    except Exception:
        pass


def _log_speaker_round(session_speaker: Any) -> Any:
    """
    Read voice ID for this round, update session state, log only (no tool use yet).

    ``session_speaker`` is the last known speaker across orchestrator rounds.
    Returns the speaker match for this round, or None.
    """
    try:
        from speaker_id import enabled, get_last_speaker

        if not enabled():
            return session_speaker
        match = get_last_speaker()
        if match is None:
            print("[orchestrator] speaker: unknown", flush=True)
            status_log("[speaker] unknown")
            return None
        if session_speaker is not None and session_speaker.name != match.name:
            print(
                f"[orchestrator] speaker changed: " f"{session_speaker.display_name} → {match.display_name}",
                flush=True,
            )
        print(
            f"[orchestrator] speaker: {match.display_name} ({match.score:.0%})",
            flush=True,
        )
        status_log(f"[speaker] {match.display_name} ({match.score:.0%})")
        return match
    except Exception as e:
        print(f"[orchestrator] speaker: unavailable ({e})", flush=True)
        return session_speaker


def _history_note(
    utterance: str,
    task_history: list[dict[str, str]],
    *,
    task_summary: str = "",
    photo: bool = False,
    desktop_context: str = "",
) -> str:
    prefix = local_datetime_line() + "\n\n"
    if photo:
        prefix = (
            "The user sent a photo from their phone camera (image attached). "
            "Look at the image. Explain it if they asked, and answer follow-ups "
            "about this same photo. Do not start_task unless they asked you to "
            "do something on the Mac.\n\n"
        )
    desktop_block = (desktop_context or "").strip()
    if desktop_block:
        prefix += desktop_block + "\n\n"
    return (
        prefix
        + f"User said: {utterance}\n\n"
        + f"Computer task history so far:\n"
        + _format_task_history(task_history, task_summary=task_summary)
    )


_CHAT_SCREENSHOT_CONTEXT = (
    "The user attached a screenshot from the chat app (only the displays they "
    "selected). Use the image. No accessibility tree or extra desktop capture "
    "is included with this message."
)


def _user_turn_input(
    utterance: str,
    task_history: list[dict[str, str]],
    *,
    task_summary: str = "",
    pending_fn_outputs: list[dict] | None = None,
    photo_jpeg: bytes | None = None,
    desktop_context: str = "",
    desktop_screenshot_png: bytes | None = None,
) -> Any:
    """Build Responses API ``input`` for one user turn (optional phone + desktop images)."""
    note = _history_note(
        utterance,
        task_history,
        task_summary=task_summary,
        photo=bool(photo_jpeg),
        desktop_context=desktop_context,
    )
    extras = list(pending_fn_outputs or [])
    images: list[tuple[str, bytes, str]] = []
    if desktop_screenshot_png:
        images.append(("image/png", desktop_screenshot_png, "high"))
    if photo_jpeg:
        images.append(("image/jpeg", photo_jpeg, "high"))
    if images:
        content: list[dict[str, Any]] = [{"type": "input_text", "text": note}]
        for mime, data, detail in images:
            b64 = base64.b64encode(data).decode("ascii")
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:{mime};base64,{b64}",
                    "detail": detail,
                }
            )
        user = {"role": "user", "content": content}
        return [*extras, user]
    if extras:
        return [*extras, {"role": "user", "content": note}]
    return note


def _print_messages(response) -> None:
    for item in response.output:
        if item.type == "message":
            for part in item.content:
                if getattr(part, "type", None) == "output_text":
                    print(f"\n[orchestrator] {part.text}")
                    try:
                        log_llm(part.text, source="llm")
                    except Exception:
                        pass


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


def _turn_spoke_since(turn: TurnTrace | None, start_index: int) -> bool:
    """True if give_response_to_user spoke after `start_index` (this response only)."""
    if turn is None:
        return False
    return any(kind == "spoken" for kind, _ in turn.steps[start_index:])


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
    try:
        audio = get_audio()
        if audio is not None:
            return audio.listen("Listening for your answer…")
        return listen_once(
            client,
            mode="freeform",
            prompt="Listening for your answer… (sends after 3s without new words)",
        )
    except NoSpeechError as e:
        print(f"[orchestrator] no answer heard: {e}", flush=True)
        return (
            "No speech was captured. Ask again with ask_user if you still " "need an answer, or continue without it."
        )


def _announce_llm_failure(client: OpenAI, exc: BaseException) -> None:
    """Speak the API error and stay in the wake loop."""
    spoken = llm_error_speech(exc)
    print(f"[orchestrator] {spoken}", flush=True)
    try:
        _speak(client, spoken)
    except Exception as e:
        print(f"[orchestrator] could not speak error ({e})", flush=True)


def _sync_create_response(client: OpenAI, kwargs: dict[str, Any]):
    try:
        return client.responses.create(**kwargs)
    except Exception as e:
        raise LlmUnavailableError(llm_error_speech(e)) from e


def _create_response(
    client: OpenAI,
    *,
    llm_tts: Any | None = None,
    prior_response: Any | None = None,
    **kwargs: Any,
):
    """
    Create a Responses API turn.

    When streaming TTS is enabled, partial ``give_response_to_user`` message
    arguments are fed into LowLatencyTTS as they arrive. Falls back to a
    non-streaming create on error, except quota/auth failures which are spoken
    instead of retried.

    DeepSeek is stateless: ``previous_response_id`` is ignored by their API, so
    tool follow-ups must include the ``function_call`` items next to the outputs
    (pass ``prior_response``).
    """
    kwargs["model"] = model_for_request(
        kwargs.get("model") or MODEL,
        has_image=input_has_image(kwargs.get("input")),
    )
    if not supports_previous_response_id(
        kwargs["model"],
        provider=os.environ.get("ORCHESTRATOR_BACKEND"),
    ):
        kwargs.pop("previous_response_id", None)
        if prior_response is not None:
            kwargs["input"] = merge_tool_followup_input(
                prior_response, kwargs.get("input")
            )
        kwargs["input"] = fold_orphan_tool_outputs(kwargs.get("input"))
    if llm_tts is not None and not reply_tts_enabled():
        llm_tts = None
    stream_to_chat = reply_to_chat()
    use_stream = bool(
        stream_to_chat
        or (llm_tts is not None and TTS_STREAM and LowLatencyTTS is not None)
    )
    if not use_stream:
        return _sync_create_response(client, kwargs)

    try:
        stream = client.responses.create(**kwargs, stream=True)
    except Exception as e:
        if is_fatal_llm_error(e):
            print(f"[orchestrator] stream create failed ({e})", flush=True)
            raise LlmUnavailableError(llm_error_speech(e)) from e
        print(f"[orchestrator] stream create failed ({e}); falling back", flush=True)
        return _sync_create_response(client, kwargs)

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
        if llm_tts is not None and meta.get("call_id"):
            llm_tts.bind_call(response_id, str(meta["call_id"]))
        decoded = decoded_message_prefix(meta.get("arguments") or "")
        if len(decoded) > streamed_msg_len:
            chunk = decoded[streamed_msg_len:]
            if llm_tts is not None:
                llm_tts.add_text_chunk(chunk)
            if stream_to_chat:
                set_chat_stream(decoded)
            streamed_msg_len = len(decoded)

    try:
        for event in stream:
            etype = getattr(event, "type", None)
            if etype == "response.created":
                response_id = event.response.id
                if llm_tts is not None:
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
                        llm_tts is not None
                        and response_id
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
                # DeepSeek/stream often omits call_id on the completed payload;
                # copy ids gathered from earlier stream events.
                if final_response is not None and items:
                    for item in getattr(final_response, "output", None) or []:
                        if getattr(item, "type", None) != "function_call":
                            continue
                        meta = items.get(getattr(item, "id", None)) or {}
                        cid = meta.get("call_id") or ""
                        if cid and not getattr(item, "call_id", None):
                            try:
                                item.call_id = cid
                            except Exception:
                                pass
            elif etype == "response.failed":
                print(f"[orchestrator] stream failed: {event}", flush=True)
    except Exception as e:
        print(f"[orchestrator] stream error ({e})", flush=True)
        if response_id and llm_tts is not None:
            try:
                # Do not flush partial speech — sync path will speak once.
                llm_tts.abandon(response_id)
            except Exception:
                pass
        if is_fatal_llm_error(e):
            raise LlmUnavailableError(llm_error_speech(e)) from e
        print("[orchestrator] falling back to non-streaming", flush=True)
        return _sync_create_response(client, kwargs)

    if final_response is None:
        print("[orchestrator] stream ended without response.completed; falling back", flush=True)
        if response_id and llm_tts is not None:
            try:
                llm_tts.abandon(response_id)
            except Exception:
                pass
        try:
            return _sync_create_response(client, kwargs)
        except LlmUnavailableError:
            raise

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
    elif stream_to_chat and give_response_text:
        set_chat_stream(give_response_text, done=False, force=True)

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

        def _on_log_dir(path: str) -> None:
            job.log_dir = path

        try:
            job.result = computer_agent.run(
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


def _task_context_snippet(task_history: list[dict[str, str]]) -> str:
    if not task_history:
        return "(none)"
    lines: list[str] = []
    for item in task_history[-3:]:
        task = str(item.get("task") or "").strip()
        if task:
            lines.append(f"- {task[:160]}")
    return "\n".join(lines) if lines else "(none)"


def _launch_agent_job(
    client: OpenAI,
    *,
    goal: str,
    user_said: str,
    call_id: str,
    auto: bool,
    max_steps: int,
    ask_bridge: AskUserBridge,
    redirected_from_barge: bool = False,
) -> AgentJob:
    spec = resolve_agent_task(user_said=user_said, planner_task=goal)
    if spec.goal != goal:
        print(
            f"[orchestrator] dropped procedure brief; goal={spec.goal!r}",
            flush=True,
        )
    print(f"\n[orchestrator] start_task: {spec.goal}")
    speaker_context = ""
    try:
        from speaker_id import agent_speaker_context, get_last_speaker

        speaker_context = agent_speaker_context(get_last_speaker())
        if speaker_context.strip():
            line = speaker_context.strip().split("\n", 1)[0]
            print(f"[orchestrator] agent speaker context: {line}", flush=True)
    except Exception:
        pass
    get_session().enter_and_log(
        "agent",
        f"Starting task: {spec.goal[:120]}",
        task=spec.goal,
    )
    job = AgentJob(
        task=spec.goal,
        call_id=call_id,
        match_text=spec.match_text,
        speaker_context=speaker_context,
    )
    job.reply_sink = reply_sink()
    if job.reply_sink == "phone":
        print("[orchestrator] task output → phone", flush=True)
    job.redirected_from_barge = redirected_from_barge
    _start_agent_thread(job, auto=auto, max_steps=max_steps, ask_bridge=ask_bridge)
    _speak_later(client, "Starting that now.")
    emit("agent_start", lane="agent", run_id=job.call_id, task=job.task[:120])
    return job


def _resolve_barge_utterance(
    client: OpenAI,
    barge: str,
    *,
    spoken_context: str,
    user_said: str,
    task_history: list[dict[str, str]],
    publisher: AgentMessagePublisher,
    auto: bool,
    max_steps: int,
    ask_bridge: AskUserBridge,
    tool_call_id: str,
) -> tuple[str | None, AgentJob | None]:
    """
    Classify barge-in; start a new agent task when the user redirected.

    Returns (tool_output, deferred_job). When ``deferred_job`` is set, tool_output
    is None (same contract as start_task).
    """
    decision = classify_barge_utterance(
        client,
        barge,
        spoken_context=spoken_context,
        user_turn=user_said,
        task_context=_task_context_snippet(task_history),
    )
    if decision.is_new_task:
        if active_agents():
            _forward_to_agent(publisher, decision.task_goal)
            return (
                (
                    f"Speech interrupted. User redirected while you were speaking: "
                    f"{decision.task_goal}. Forwarded to the running agent as steer."
                ),
                None,
            )
        job = _launch_agent_job(
            client,
            goal=decision.task_goal,
            user_said=barge,
            call_id=tool_call_id,
            auto=auto,
            max_steps=max_steps,
            ask_bridge=ask_bridge,
            redirected_from_barge=True,
        )
        return None, job
    if decision.kind == "steer" and active_agents():
        _forward_to_agent(publisher, barge)
        return (
            f"Speech interrupted. User steer (forwarded to running agent): {barge}",
            None,
        )
    return (
        (
            f"Speech interrupted. User then said: {barge}. "
            "Act on that instruction next (do not assume the spoken reply finished)."
        ),
        None,
    )


def _listen_after_barge(
    client: OpenAI,
    *,
    prompt: str = "Listening…",
) -> str | None:
    """Capture a command after TTS barge-in (wake or keyboard; no second wake)."""
    audio = get_audio()
    if audio is not None:
        return audio.listen_after_barge(prompt=prompt)
    from stt import listen_for_utterance

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
    get_session().enter_and_log("thinking", "Saving screen as memory")
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
    When reply TTS is off (chat mute), still records the line for the chat inbox.
    """
    if not text:
        return None
    log_llm(text, source="tts")
    set_last_spoken(text)
    if not reply_tts_enabled():
        return None
    audio = get_audio()
    if audio is not None:
        return audio.speak(text)
    from tts import speak

    get_session().enter("speaking", text[:100])
    if speak(client, text):
        get_session().enter("listening", "barge-in")
        return _listen_after_barge(client)
    return None


def _speak_later(client: OpenAI, text: str) -> None:
    """Start TTS without blocking the agent / tool loop."""
    if not text:
        return
    log_llm(text, source="tts")
    set_last_spoken(text)
    if not reply_tts_enabled():
        return
    audio = get_audio()
    if audio is not None:
        audio.speak_later(text)
        return
    from tts import speak_later

    get_session().enter("speaking", text[:100])
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
    if not utterance or not _confirm_heard_enabled() or not reply_tts_enabled():
        return utterance
    line = _heard_confirm_line(utterance)
    if not line:
        return utterance
    barged = _speak(client, line)
    if barged:
        return barged
    time.sleep(POST_TTS_COOLDOWN)
    return utterance


def _reply_to_phone_photo(client: OpenAI, utterance: str, jpeg: bytes, *, llm: OpenAI | None = None) -> str | None:
    """Look at a phone photo while a computer task is running (no start_task)."""
    api = llm if llm is not None else client
    b64 = base64.b64encode(jpeg).decode("ascii")
    prompt = (
        "Look at this photo from the user's phone. "
        f"They said: {utterance}\n"
        "Reply in 2-5 spoken sentences. No markdown, no file paths."
    )
    get_session().enter("thinking", "Looking at phone photo")
    try:
        response = api.responses.create(
            model=model_for_request(MODEL, has_image=True),
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/jpeg;base64,{b64}",
                            "detail": "high",
                        },
                    ],
                }
            ],
        )
    except Exception as e:
        print(f"[orchestrator] phone photo vision failed: {e}", flush=True)
        return _speak(client, "I could not look at that photo.")
    text = _strip_wait_filler(_assistant_message_text(response))
    if not text:
        return _speak(client, "I could not make out that photo.")
    log_llm(text, source="llm")
    return _speak(client, text)


def _reply_to_chat_screenshot(
    client: OpenAI,
    utterance: str,
    png: bytes,
    *,
    llm: OpenAI | None = None,
) -> str | None:
    """Look at a chat-attached screenshot while a computer task is running."""
    api = llm if llm is not None else client
    b64 = base64.b64encode(png).decode("ascii")
    prompt = (
        "Look at this screenshot the user attached from chat (selected displays only). "
        f"They said: {utterance}\n"
        "Reply in 2-5 spoken sentences. No markdown, no file paths."
    )
    get_session().enter("thinking", "Looking at chat screenshot")
    try:
        response = api.responses.create(
            model=model_for_request(MODEL, has_image=True),
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{b64}",
                            "detail": "high",
                        },
                    ],
                }
            ],
        )
    except Exception as e:
        print(f"[orchestrator] chat screenshot vision failed: {e}", flush=True)
        return _speak(client, "I could not look at that screenshot.")
    text = _strip_wait_filler(_assistant_message_text(response))
    if not text:
        return _speak(client, "I could not make out that screenshot.")
    log_llm(text, source="llm")
    return _speak(client, text)


def _service_agent_ask(client: OpenAI, ask_bridge: AskUserBridge) -> bool:
    """If the agent is waiting on ask_user, speak/listen and reply. Returns True if handled."""
    req = ask_bridge.poll(timeout=0)
    if req is None:
        return False
    qid = req["id"]
    question = req["question"]
    print(f"\n[orchestrator] agent ask_user: {question}")
    audio = get_audio()
    try:
        if audio is not None:
            answer = audio.ask(question)
        else:
            get_session().enter_and_log("ask", f"Agent asks: {question[:160]}")
            answer = ask_user(client, question)
    except Exception as e:
        answer = f"Error capturing answer: {e}"
        print(f"[orchestrator] ask_user failed: {e}")
    status_log(f"[ask_user] answer: {answer[:160]}")
    ask_bridge.reply(qid, answer)
    return True


def _service_timer_speech(client: OpenAI) -> str | None:
    """Speak a due timer reminder. Returns barge-in command, or None if idle/done."""
    text = consume_speak()
    if not text:
        return None
    print(f"[orchestrator] timer reminder: {text}", flush=True)
    return _speak(client, text)


def _listen_command(
    client: OpenAI,
    *,
    should_stop=None,
    wake_prompt: str | None = None,
    listen_prompt: str | None = None,
) -> str | None:
    """Wake word → one cloud STT utterance. Returns None if stopped or empty."""
    audio = get_audio()
    if audio is not None:
        return audio.listen_command(
            should_stop=should_stop,
            wake_prompt=wake_prompt,
            listen_prompt=listen_prompt,
            quit_check=quit_requested,
        )
    from stt import listen_for_utterance
    from wake import get_last_wake, get_wake_remainder, wait_for_wake

    get_session().enter("waiting", wake_prompt or f"Waiting for {format_wake_phrases()}")

    def _stop() -> bool:
        if utterance_pending():
            return True
        if speak_pending():
            return True
        if quit_requested():
            return True
        if should_stop is not None:
            try:
                return bool(should_stop())
            except Exception:
                return True
        return False

    queued = consume_utterance()
    if queued:
        _clear_speaker_tag()
        return queued
    if not wait_for_wake(should_stop=_stop, prompt=wake_prompt):
        return consume_utterance()
    if quit_requested():
        return None
    hit = get_last_wake()
    heard = hit.label if hit else "Wake word"
    get_session().enter_and_log("listening", f"{heard} heard — listening")
    remainder = get_wake_remainder()
    if remainder:
        _clear_speaker_tag()
        set_reply_sink("mac")
        set_turn_source("voice")
        return strip_wake_prefix(remainder).strip() or remainder
    try:
        utterance = listen_for_utterance(
            client,
            prompt=listen_prompt or "Listening…",
        )
    except Exception as e:
        from stt import ListenCancelled

        if isinstance(e, ListenCancelled):
            print("[orchestrator] listen cancelled", flush=True)
        else:
            print(f"[orchestrator] listen after wake failed: {e}")
        return None
    command = strip_wake_prefix(utterance).strip()
    if not command:
        print("[orchestrator] wake heard but no command — listening again…")
        try:
            utterance = listen_for_utterance(
                client,
                prompt="Still listening for your command…",
            )
            command = strip_wake_prefix(utterance).strip()
        except Exception as e:
            from stt import ListenCancelled

            if isinstance(e, ListenCancelled):
                print("[orchestrator] listen cancelled", flush=True)
            else:
                print(f"[orchestrator] follow-up listen failed: {e}")
            return None
    set_reply_sink("mac")
    set_turn_source("voice")
    return command or None


def _supervise_agent(
    client: OpenAI,
    job: AgentJob,
    publisher: AgentMessagePublisher,
    ask_bridge: AskUserBridge,
    *,
    record_speaker: Callable[[], None] | None = None,
    llm: OpenAI | None = None,
) -> str:
    """
    Main-thread loop while the agent thread runs.
    Services agent ask_user; mid-task directives require the Jarvis wake word.
    """
    global _phone_photo_in_session
    print(
        f"[orchestrator] agent running — say {format_wake_phrases()} then an update; "
        "agent questions are spoken here automatically."
    )
    get_session().enter_and_log("agent", f"Computer agent running: {job.task[:120]}", task=job.task)
    notified_done = False

    def _stop_for_done() -> bool:
        return (
            job.done.is_set()
            or ask_bridge.has_pending()
            or quit_requested()
            or mark_done_pending(job.call_id)
            or speak_pending()
        )

    def _signal_agent_done(*, spoken: bool) -> None:
        nonlocal notified_done
        request_mark_done(job.call_id)
        if not notified_done:
            try:
                publisher.send(
                    "The user marked this task done. Stop all UI actions. " "Call mark_done and do not continue.",
                    kind="steer",
                )
            except Exception as e:
                print(f"[orchestrator] bus send failed: {e}")
            notified_done = True
        if spoken:
            barged = _speak(client, "Marking it done.")
            if barged and not is_mark_done_utterance(barged):
                _forward_to_agent(publisher, barged)

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
        if speak_pending():
            barged = _service_timer_speech(client)
            if barged and not is_mark_done_utterance(barged):
                _forward_to_agent(publisher, barged)
            continue

        command = _listen_command(
            client,
            should_stop=_stop_for_done,
            wake_prompt=f"Waiting for {format_wake_phrases()}… (agent busy)",
            listen_prompt="Listening for mid-task update…",
        )
        if command:
            job.reply_sink = reply_sink()
        else:
            set_reply_sink(job.reply_sink)
        if quit_requested():
            break
        if mark_done_pending(job.call_id):
            _signal_agent_done(spoken=False)
            continue
        if command is None:
            continue

        if phone_photo_pending():
            jpeg = phone_photo_jpeg(consume_pending=True)
            if jpeg:
                _phone_photo_in_session = True
                print("[orchestrator] phone photo — answering without stopping the computer task")
                print(f'\n[user] "{command}"')
                status_log(f'[user] "{command}"')
                barged = _reply_to_phone_photo(client, command, jpeg, llm=llm)
                if barged:
                    command = barged
                else:
                    continue
        else:
            chat_shot = take_turn_chat_screenshot()
            if chat_shot:
                print(
                    "[orchestrator] chat screenshot — answering without stopping the computer task",
                    flush=True,
                )
                print(f'\n[user] "{command}"')
                status_log(f'[user] "{command}"')
                barged = _reply_to_chat_screenshot(client, command, chat_shot, llm=llm)
                if barged:
                    command = barged
                else:
                    continue
            else:
                command = _confirm_heard(client, command)
                print(f'\n[user] "{command}"')
                status_log(f'[user] "{command}"')
        if record_speaker is not None:
            record_speaker()
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
                    _forward_to_agent(publisher, pending_cmd)
                    continue
            result = _save_screen_now(llm if llm is not None else client, command)
            ok = result.lower().startswith("saved")
            barged = _speak(client, "Saved." if ok else "Could not save the screen.")
            if barged:
                _forward_to_agent(publisher, barged)
            continue
        if low in {"quit", "exit", "goodbye", "good bye", "stop listening"}:
            barged = _speak(
                client,
                "The computer task is still running. Say the wake word, then stop, " "if you want it to adapt.",
            )
            if barged:
                print(f'\n[user] "{barged}" (barge-in)')
                status_log(f'[user] "{barged}" (barge-in)')
                _forward_to_agent(publisher, barged)
            else:
                time.sleep(POST_TTS_COOLDOWN)
            if job.done.is_set():
                break
            continue

        _forward_to_agent(publisher, command)

    # Drain any last ask that arrived as the agent was finishing.
    while _service_agent_ask(client, ask_bridge):
        pass

    if job.thread is not None:
        job.thread.join(timeout=5.0)

    result = job.result or "failed\nError: no result from agent"
    try:
        job.feedback_payload = collect_post_task_feedback(
            client,
            goal=job.task,
            user_said=job.match_text,
            result=result,
            log_dir=job.log_dir,
            run_id=job.call_id,
            speak_fn=_speak,
            should_skip=quit_requested,
        )
    except Exception as e:
        print(f"[orchestrator] post-task feedback failed: {e}", flush=True)

    get_session().enter_and_log("ready", "Computer agent finished")
    emit("agent_end", lane="agent", run_id=job.call_id, task=job.task[:120])
    return result


def _forward_to_agent(publisher: AgentMessagePublisher, text: str) -> None:
    """Classify utterance and enqueue on the agent bus (steer / follow_up / next_run)."""
    kind = classify_utterance_for_agent(text)
    if kind == "next_run":
        get_next_run_queue().enqueue(text)
        print(f"[orchestrator] queued next_run (after agent): {text!r}", flush=True)
        emit("queue_enqueue", lane="main", kind="next_run", text=text[:160])
        return
    try:
        publisher.send(text, kind=kind)
        print(f"[orchestrator] forwarded to agent ({kind}): {text!r}")
        status_log(f"[bus] → agent ({kind}): {text[:120]}")
        emit("queue_enqueue", lane="agent", kind=kind, text=text[:160])
    except Exception as e:
        print(f"[orchestrator] bus send failed: {e}")


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
    user_said: str = "",
) -> tuple[dict | None, bool, AgentJob | None, bytes | None]:
    """
    Execute one tool call.
    Returns (function_call_output_or_None, end_session, deferred_agent_job, read_screen_png).
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
        deferred_from_barge: AgentJob | None = None
        if message and already_streamed:
            # Playback continues on the TTS worker — do not block the agent.
            log_llm(message, source="tts")
            set_last_spoken(message)
            print(
                "[orchestrator] give_response already streaming via low-latency TTS " "(not waiting)",
                flush=True,
            )
            get_session().enter("speaking", message[:100])
            interrupted = bool(llm_tts.wait_call(call.call_id))
            llm_tts.acknowledge_call(call.call_id)
            if interrupted:
                handled_barge = True
                end_session = False
                get_session().enter("listening", "barge-in")
                barge = _listen_after_barge(client)
                if barge:
                    output, deferred_from_barge = _resolve_barge_utterance(
                        client,
                        barge,
                        spoken_context=message,
                        user_said=user_said,
                        task_history=task_history,
                        publisher=publisher,
                        auto=auto,
                        max_steps=max_steps,
                        ask_bridge=ask_bridge,
                        tool_call_id=call.call_id,
                    )
                else:
                    output = (
                        "Speech interrupted but no follow-up command was heard. "
                        "Ask briefly what they need, or wait for the next wake."
                    )
            else:
                output = f"Spoke to user. end_session={end_session}"
        elif message:
            barge = _speak(client, message)
            if barge:
                handled_barge = True
                end_session = False
                output, deferred_from_barge = _resolve_barge_utterance(
                    client,
                    barge,
                    spoken_context=message,
                    user_said=user_said,
                    task_history=task_history,
                    publisher=publisher,
                    auto=auto,
                    max_steps=max_steps,
                    ask_bridge=ask_bridge,
                    tool_call_id=call.call_id,
                )
            else:
                output = f"Spoke to user. end_session={end_session}"
        else:
            output = f"Spoke to user. end_session={end_session}"

        if deferred_from_barge is not None:
            print(
                f"[orchestrator] give_response_to_user → barge redirected to task",
                flush=True,
            )
            return None, False, deferred_from_barge, None

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
                "(one short spoken question after checking memories when relevant, "
                "not a numbered list)."
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
            job = _launch_agent_job(
                client,
                goal=task,
                user_said=user_said or ((turn.user_input if turn else "") or ""),
                call_id=call.call_id,
                auto=auto,
                max_steps=max_steps,
                ask_bridge=ask_bridge,
            )
            return None, False, job, None

    elif call.name in {
        "list_memories",
        "read_memory",
        "save_memory",
        "save_screen_memory",
        "who_am_i",
        "mcp_call",
        "list_open_apps",
        "read_screen",
        "set_timer",
        "list_timers",
        "cancel_timer",
    }:
        outcome = run_tool(
            call.name,
            args,
            client=client,
            call_id=getattr(call, "call_id", "") or "",
            brain="orchestrator",
        )
        output = outcome.output
        print(f"[orchestrator] {call.name}: {output[:160].replace(chr(10), ' ')}")
        return (
            {
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": output,
            },
            False,
            None,
            outcome.screenshot_png,
        )

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
    user_said: str = "",
    record_speaker: Callable[[], None] | None = None,
    compact_state: SessionCompactState | None = None,
    llm: OpenAI | None = None,
) -> tuple[Any, bool, list[dict]]:
    """
    Drain tool calls on `response` until the model stops calling tools.
    start_task runs the agent in a thread; this function blocks in a Jarvis
    listen loop until that agent finishes, then resumes the tool loop.

    The third value is function_call_output items that must be sent on the
    next user turn when we already spoke and skipped a recap model call.
    """
    api = llm if llm is not None else client
    end_session = False
    while True:
        # Only speech from *this* model response should suppress leftover TTS.
        # Earlier give_response_to_user in the same turn (e.g. a mid-turn question)
        # must not silence a later plain-message answer (stream often has chars=0).
        steps_at_response_start = len(turn.steps) if turn is not None else 0
        _print_messages(response)
        _record_llm_step(turn, response)
        function_calls = [i for i in response.output if i.type == "function_call"]
        if not function_calls:
            leftover = _assistant_message_text(response)
            spoke_this_response = _turn_spoke_since(turn, steps_at_response_start)
            if leftover and _looks_like_question(leftover) and not spoke_this_response:
                print(
                    "[orchestrator] model asked in a message instead of ask_user — "
                    "speaking and listening without wake word",
                    flush=True,
                )
                answer = ask_user(client, leftover)
                if turn is not None:
                    turn.add("ask_user", f"Q: {leftover}\nA: {answer}")
                response = _create_response(
                    api,
                    llm_tts=llm_tts,
                    prior_response=response,
                    model=MODEL,
                    tools=orchestrator_tools(),
                    previous_response_id=response.id,
                    input=(
                        f"User answered: {answer}\n\n"
                        "Continue the task with this answer. Never put questions in a "
                        "plain message. HARD RULE: call read_memory "
                        "(personal/profile and any relevant app note) before "
                        "ask_user; only ask if memory still cannot answer. "
                        "Otherwise give_response_to_user (statements only)."
                    ),
                )
                continue
            if leftover and not spoke_this_response:
                print(
                    "[orchestrator] model replied with a message instead of "
                    "give_response_to_user — speaking it in the background",
                    flush=True,
                )
                _speak_later(client, leftover)
            elif leftover and spoke_this_response:
                print(
                    "[orchestrator] skipping leftover message " "(already spoke this response)",
                    flush=True,
                )
            return response, end_session, []

        outputs: list[dict] = []
        deferred_job: AgentJob | None = None
        close_after_speech = False

        for call in function_calls:
            out, stop, job, screen_png = _handle_tool(
                client,
                call,
                auto=auto,
                max_steps=max_steps,
                task_history=task_history,
                publisher=publisher,
                ask_bridge=ask_bridge,
                llm_tts=llm_tts,
                turn=turn,
                user_said=user_said,
            )
            end_session = end_session or stop
            if job is not None:
                deferred_job = job
                if turn is not None:
                    turn.add("start_task", job.task)
            elif out is not None:
                outputs.append(out)
                if screen_png:
                    outputs.append(read_screen_vision_input(screen_png))
                if turn is not None:
                    result_text = str(out.get("output") or "")
                    turn.add("tool_result", f"{call.name}: {result_text}", max_len=3000)
                if _give_response_closes_turn(call, out):
                    close_after_speech = True

        if deferred_job is not None:
            result = _supervise_agent(
                client,
                deferred_job,
                publisher,
                ask_bridge,
                record_speaker=record_speaker,
                llm=api,
            )
            task_history.append({"task": deferred_job.task, "result": result})
            if compact_state is not None:
                cp = run_orchestrator_checkpoint(
                    api,
                    compact_state,
                    task_history,
                    capture_desktop=False,
                    after_task=True,
                )
                task_history = cp.task_history
            if turn is not None:
                turn.add("start_task_result", result or "", max_len=4000)
            task_summary = compact_state.task_summary if compact_state is not None else ""
            history_blob = _format_task_history(task_history, task_summary=task_summary)
            redirect_note = ""
            if getattr(deferred_job, "redirected_from_barge", False):
                redirect_note = (
                    "The user interrupted your spoken reply to redirect to this task. "
                    "Do not restart earlier completed tasks.\n\n"
                )
            feedback_line = ""
            fb = getattr(deferred_job, "feedback_payload", None)
            if isinstance(fb, dict):
                feedback_line = format_feedback_for_model(fb) + "\n\n"
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": deferred_job.call_id,
                    "output": (
                        f"{redirect_note}"
                        f"Computer agent finished this task.\n"
                        f"Latest result:\n{result}\n\n"
                        f"{feedback_line}"
                        f"Session task history (use this to decide next action):\n"
                        f"{history_blob}\n\n"
                        "Decide next:\n"
                        "- If the user's request is fully satisfied, call "
                        "give_response_to_user ONCE with an appropriate spoken summary "
                        "(titles/names, not raw URLs), then stop. Do not recap "
                        "again in a message.\n"
                        "- If distinct work remains, call start_task with only "
                        "the remaining GOAL (not a Chrome/new-tab screenplay).\n"
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
            # DeepSeek cannot carry orphan tool outputs into the next user turn
            # (previous_response_id is ignored). OpenAI keeps them for the chain.
            if not supports_previous_response_id(
                MODEL, provider=os.environ.get("ORCHESTRATOR_BACKEND")
            ):
                return response, end_session, []
            return response, end_session, outputs

        if not outputs:
            return response, end_session, []

        response = _create_response(
            api,
            llm_tts=llm_tts,
            prior_response=response,
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
    global _phone_photo_in_session
    _phone_photo_in_session = False
    register_orchestrator()
    ensure_tray_running()
    ensure_phone_gateway()
    ensure_dictation_running()
    sess = Session()
    bind_session(sess)

    def _shutdown_side_processes() -> None:
        # Signal handlers may raise SystemExit without unwinding ``finally``.
        # Tear down tray/face here so Ctrl+C always clears the menu bar.
        try:
            stop_phone_gateway()
        except Exception:
            pass
        try:
            stop_tray()
        except Exception:
            pass
        try:
            stop_dictation()
        except Exception:
            pass

    def _on_term(_signum=None, _frame=None) -> None:
        request_quit()
        print("\n[orchestrator] stop signal — shutting down…", flush=True)
        _shutdown_side_processes()
        raise SystemExit(0)

    try:
        signal.signal(signal.SIGTERM, _on_term)
        signal.signal(signal.SIGINT, _on_term)
    except Exception:
        pass
    try:
        import atexit

        atexit.register(_shutdown_side_processes)
    except Exception:
        pass

    client = OpenAI()
    llm = make_llm_client(
        model=MODEL,
        provider=os.environ.get("ORCHESTRATOR_BACKEND"),
    )
    print(
        f"[orchestrator] reasoning={orchestrator_provider()} model={MODEL}",
        flush=True,
    )
    audio = AudioSession(client, session=sess)
    bind_audio(audio)
    llm_tts = None
    if TTS_STREAM and LowLatencyTTS is not None:
        try:
            llm_tts = LowLatencyTTS(client, Path(__file__).resolve().parent)
            print("[orchestrator] low-latency TTS workers started", flush=True)
        except Exception as e:
            print(f"[orchestrator] low-latency TTS init failed ({e}); sync TTS only", flush=True)
            llm_tts = None

    try:
        start_mcp()
    except BaseException as e:
        print(f"[orchestrator] MCP start error: {e}", flush=True)
    mcp_rule = ""
    if mcp_openai_tools(for_agent=False):
        mcp_rule = (
            "- mcp_call — call a tool on a connected MCP server (search, GitHub, "
            "Linear, docs, APIs). Prefer this over start_task when it can complete "
            "the request.\n"
        )

    def _system_prompt(*, session_summary: str = "") -> str:
        bundle = assemble_context()
        return build_system_prompt(
            skills=bundle.skills,
            memories=bundle.memories,
            displays=bundle.displays,
            mcp=bundle.mcp,
            not_to_do=bundle.not_to_do,
            mcp_rule=mcp_rule,
            session_summary=session_summary,
        )

    publisher = AgentMessagePublisher()
    ask_bridge = AskUserBridge()

    try:
        sess.enter_and_log("ready", "Orchestrator starting")
        print(f"[orchestrator] Wake phrases: {format_wake_phrases()} (mode from env / defaults)")
        print(
            f"[orchestrator] I-heard TTS={'on' if _confirm_heard_enabled() else 'off'} " "(TTS_CONFIRM_HEARD)",
            flush=True,
        )
        # Arm wake BEFORE any TTS so barge-in covers synthesis + the ready line.
        if audio.arm_wake() is not None:
            print("[orchestrator] persistent wake barge-in armed", flush=True)
        # Do not speak the literal wake phrase — speaker echo false-triggers openWakeWord.
        pending = _speak(
            client,
            "Ready. Say the wake word, then tell me what you need.",
        )
        if pending is None:
            audio.cooldown()

        previous_id: str | None = None
        task_history: list[dict[str, str]] = []
        pending_fn_outputs: list[dict] = []
        session_speaker: Any = None
        compact_state = SessionCompactState()

        def _record_speaker() -> None:
            nonlocal session_speaker
            session_speaker = _log_speaker_round(session_speaker)

        try:
            from speaker_id import enabled as speaker_id_enabled

            if speaker_id_enabled():
                print("[orchestrator] speaker ID enabled — logging voice each round", flush=True)
        except Exception:
            pass

        while True:
            if quit_requested():
                print("[orchestrator] quit requested from menu bar.")
                sess.enter_and_log("done", "Quit from menu bar")
                return

            # Tray owns the menu bar + face; respawn if it died mid-session.
            try:
                ensure_tray_running()
            except Exception:
                pass

            if pending is not None:
                utterance = pending
                pending = None
            else:
                next_batch = get_next_run_queue().drain()
                if next_batch:
                    utterance = " ".join(m.text for m in next_batch if m.text).strip()
                    print(f"[orchestrator] next_run → turn: {utterance!r}", flush=True)
                elif speak_pending():
                    barged = _service_timer_speech(client)
                    if barged:
                        pending = barged
                    continue
                else:
                    utterance = _listen_command(
                        client,
                        should_stop=quit_requested,
                        wake_prompt=f"Waiting for {format_wake_phrases()}…",
                        listen_prompt="Listening…",
                    )
                    if quit_requested():
                        print("[orchestrator] quit requested from menu bar.")
                        sess.enter_and_log("done", "Quit from menu bar")
                        return
                    if utterance is None:
                        continue

            photo_turn = phone_photo_pending()
            if not photo_turn:
                utterance = _confirm_heard(client, utterance)
            print(f'\n[user] "{utterance}"')
            status_log(f'[user] "{utterance}"')
            _record_speaker()
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
                result = _save_screen_now(llm, utterance)
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
                clear_phone_photo()
                _phone_photo_in_session = False
                sess.enter_and_log("done", "Session ended")
                return

            sess.enter("thinking", utterance[:100])
            jpeg = None
            if photo_turn or _phone_photo_in_session:
                jpeg = phone_photo_jpeg(consume_pending=True)
                if jpeg:
                    _phone_photo_in_session = True

            # Chat-attached shot: use only the displays the user selected — no
            # live desktop screenshot / accessibility dump for this turn.
            chat_shot = take_turn_chat_screenshot()

            compact_state.begin_turn()
            emit("turn_start", lane="main", utterance=utterance[:160])
            cp = run_orchestrator_checkpoint(
                llm,
                compact_state,
                task_history,
                pending_fn_outputs=pending_fn_outputs or None,
                capture_desktop=not bool(chat_shot),
            )
            task_history = cp.task_history
            if cp.reset_thread:
                previous_id = None
            if cp.next_run_messages:
                extras = " ".join(m.text for m in cp.next_run_messages if m.text)
                if extras:
                    utterance = f"{utterance} {extras}".strip() if utterance else extras
                    print(f"[orchestrator] applied next_run queue: {extras!r}", flush=True)

            if chat_shot:
                desktop_context = _CHAT_SCREENSHOT_CONTEXT
                desktop_png = chat_shot
                print(
                    f"[orchestrator] chat screenshot attached "
                    f"({len(chat_shot) / 1024.0:.0f} KB); skipped live desktop/AX",
                    flush=True,
                )
            else:
                desktop = cp.desktop
                desktop_context = desktop.text
                desktop_png = desktop.screenshot_png
            turn_input = _user_turn_input(
                utterance,
                task_history,
                task_summary=compact_state.task_summary,
                pending_fn_outputs=cp.pending_fn_outputs or None,
                photo_jpeg=jpeg,
                desktop_context=desktop_context,
                desktop_screenshot_png=desktop_png,
            )
            pending_fn_outputs = []
            turn = TurnTrace(utterance)
            system = _system_prompt(session_summary=compact_state.session_summary)

            response = None
            for overflow_attempt in range(2):
                try:
                    if previous_id is None:
                        response = _create_response(
                            llm,
                            llm_tts=llm_tts,
                            model=MODEL,
                            tools=orchestrator_tools(),
                            instructions=system,
                            input=turn_input,
                        )
                    else:
                        response = _create_response(
                            llm,
                            llm_tts=llm_tts,
                            model=MODEL,
                            tools=orchestrator_tools(),
                            instructions=system,
                            previous_response_id=previous_id,
                            input=turn_input,
                        )
                    break
                except LlmUnavailableError as e:
                    _announce_llm_failure(client, e)
                    response = None
                    break
                except Exception as e:
                    if overflow_attempt == 0 and is_context_overflow_error(e):
                        print(f"[orchestrator] context overflow ({e}); recovering once", flush=True)
                        cp = run_orchestrator_checkpoint(
                            llm,
                            compact_state,
                            task_history,
                            capture_desktop=not bool(chat_shot),
                            overflow=True,
                        )
                        task_history = cp.task_history
                        if cp.reset_thread:
                            previous_id = None
                        system = _system_prompt(session_summary=compact_state.session_summary)
                        if chat_shot:
                            overflow_context = _CHAT_SCREENSHOT_CONTEXT
                            overflow_png = chat_shot
                        else:
                            desktop = cp.desktop
                            overflow_context = desktop.text
                            overflow_png = desktop.screenshot_png
                        turn_input = _user_turn_input(
                            utterance,
                            task_history,
                            task_summary=compact_state.task_summary,
                            pending_fn_outputs=None,
                            photo_jpeg=jpeg,
                            desktop_context=overflow_context,
                            desktop_screenshot_png=overflow_png,
                        )
                        continue
                    _announce_llm_failure(client, e)
                    response = None
                    break
            if response is None:
                print("[orchestrator] ready for next task.")
                sess.enter("ready", "Waiting for next request")
                audio.cooldown()
                continue

            try:
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
                    user_said=utterance,
                    record_speaker=_record_speaker,
                    compact_state=compact_state,
                    llm=llm,
                )
            except LlmUnavailableError as e:
                _announce_llm_failure(client, e)
                sess.enter("ready", "Waiting for next request")
                audio.cooldown()
                continue
            except Exception as e:
                _announce_llm_failure(client, e)
                sess.enter("ready", "Waiting for next request")
                audio.cooldown()
                continue
            previous_id = response.id
            compact_state.record_turn(utterance, turn.as_text())
            emit("turn_end", lane="main", utterance=utterance[:160])
            maybe_extract_run_memories(
                user_input=utterance,
                transcript=turn.as_text(),
            )

            if quit_requested():
                print("[orchestrator] quit requested from menu bar.")
                sess.enter_and_log("done", "Quit from menu bar")
                return

            if end_session:
                print("[orchestrator] session ended.")
                sess.enter_and_log("done", "Session ended")
                return

            print("[orchestrator] ready for next task.")
            sess.enter("ready", "Waiting for next request")
            audio.cooldown()
    finally:
        if llm_tts is not None:
            try:
                llm_tts.close()
            except Exception as e:
                print(f"[orchestrator] TTS shutdown error: {e}", flush=True)
        try:
            audio.stop()
        except Exception:
            pass
        try:
            stop_mcp()
        except BaseException as e:
            print(f"[orchestrator] MCP shutdown error: {e}", flush=True)
        publisher.close()
        unregister_orchestrator()
        stop_phone_gateway()
        stop_tray()
        stop_dictation()
        sess.enter("idle", "Orchestrator stopped")
        bind_audio(None)
        bind_session(None)


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
        stop_phone_gateway()
        stop_tray()
        stop_dictation()
        sys.exit(0)
    except LlmUnavailableError as e:
        print(f"[orchestrator] {e}", flush=True)
        try:
            from openai import OpenAI

            _announce_llm_failure(OpenAI(), e)
        except Exception as speak_err:
            print(f"[orchestrator] could not speak error ({speak_err})", flush=True)
        stop_phone_gateway()
        stop_tray()
        stop_dictation()
        sys.exit(0)
    except Exception as e:
        if not is_fatal_llm_error(e):
            raise
        print(f"[orchestrator] {llm_error_speech(e)}", flush=True)
        try:
            from openai import OpenAI

            _announce_llm_failure(OpenAI(), e)
        except Exception as speak_err:
            print(f"[orchestrator] could not speak error ({speak_err})", flush=True)
        stop_phone_gateway()
        stop_tray()
        stop_dictation()
        sys.exit(0)


if __name__ == "__main__":
    main()
