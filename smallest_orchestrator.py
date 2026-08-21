"""Smallest AI Electron brain for the voice orchestrator (chat + tools).

Emulates enough of the OpenAI Responses shape (``.id``, ``.output`` with
``function_call`` / ``message`` items) so ``orchestrator._process_response``
can stay unchanged.

Electron is OpenAI Chat Completions compatible at
``https://api.smallest.ai/waves/v1`` with ``model=electron``. It is text-only
but supports tool calling with spoken filler phrases — ideal for low-latency
voice turns when paired with Lightning TTS.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

ORCHESTRATOR_BACKEND = (
    os.environ.get("ORCHESTRATOR_BACKEND", "openai").strip().lower() or "openai"
)
SMALLEST_API_KEY = (os.environ.get("SMALLEST_API_KEY") or "").strip()
SMALLEST_BASE_URL = (
    os.environ.get("SMALLEST_BASE_URL") or "https://api.smallest.ai/waves/v1"
).strip().rstrip("/")
DEFAULT_MODEL = (os.environ.get("ORCHESTRATOR_MODEL") or "electron").strip() or "electron"
SMALLEST_TIMEOUT = float(os.environ.get("ORCHESTRATOR_SMALLEST_TIMEOUT", "60"))
SMALLEST_TEMPERATURE = float(os.environ.get("ORCHESTRATOR_SMALLEST_TEMPERATURE", "0.3"))

_TOOL_TEXT_BLOCK = re.compile(
    r"(?ms)^\s*([a-zA-Z_][\w]{0,64})\s*\n\s*(\{.*\})\s*$"
)
_TOOL_XML = re.compile(r"(?is)<tool_call>\s*(\{.*?\})\s*</tool_call>")
_TOOL_HINT = (
    "CRITICAL: Prefer the API tool_calls mechanism. Never print a tool name "
    "followed by JSON in your message content when a tool applies. "
    "English only. Keep spoken text short. Before slow tools (start_task, "
    "mcp_call), briefly acknowledge out loud in content (e.g. 'On it') so "
    "TTS can speak while the tool runs. For final spoken answers use "
    "give_response_to_user."
)


def using_smallest() -> bool:
    return ORCHESTRATOR_BACKEND in {"smallest", "electron", "waves"}


@dataclass
class _OutputText:
    type: str = "output_text"
    text: str = ""


@dataclass
class _MessageItem:
    type: str = "message"
    content: list[_OutputText] = field(default_factory=list)


@dataclass
class _FunctionCall:
    type: str = "function_call"
    name: str = ""
    arguments: str = ""
    call_id: str = ""
    id: str = ""


@dataclass
class ElectronResponse:
    id: str
    output: list[Any]


def _args_to_json(arguments: Any) -> str:
    if arguments is None:
        return "{}"
    if isinstance(arguments, str):
        return arguments if arguments.strip() else "{}"
    try:
        return json.dumps(arguments)
    except (TypeError, ValueError):
        return "{}"


def _new_function_call(name: str, arguments: Any, *, call_id: str | None = None) -> _FunctionCall:
    return _FunctionCall(
        name=name,
        arguments=_args_to_json(arguments),
        call_id=call_id or f"call_{uuid.uuid4().hex[:12]}",
        id=f"fc_{uuid.uuid4().hex[:12]}",
    )


def parse_text_tool_calls(content: str, allowed: set[str]) -> list[_FunctionCall]:
    text = (content or "").strip()
    if not text or not allowed:
        return []

    calls: list[_FunctionCall] = []
    for m in _TOOL_XML.finditer(text):
        try:
            payload = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        name = str(payload.get("name") or "").strip()
        if name in allowed:
            calls.append(_new_function_call(name, payload.get("arguments") or payload))
    if calls:
        return calls

    m = _TOOL_TEXT_BLOCK.match(text)
    if m and m.group(1) in allowed:
        try:
            args = json.loads(m.group(2))
        except json.JSONDecodeError:
            return []
        if isinstance(args, dict):
            return [_new_function_call(m.group(1), args)]

    if text.startswith("{") and text.endswith("}"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            name = str(payload.get("name") or payload.get("tool") or "").strip()
            if name in allowed:
                args = payload.get("arguments")
                if not isinstance(args, dict):
                    args = {
                        k: v for k, v in payload.items() if k not in {"name", "tool"}
                    }
                return [_new_function_call(name, args)]
    return []


def responses_tools_to_chat(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Convert Responses-style function tools to Chat Completions tools."""
    out: list[dict[str, Any]] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        if tool.get("type") not in {None, "function"}:
            continue
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else None
        name = str((fn or {}).get("name") or tool.get("name") or "").strip()
        if not name:
            continue
        description = str(
            (fn or {}).get("description") or tool.get("description") or ""
        )
        parameters = (fn or {}).get("parameters") or tool.get("parameters") or {
            "type": "object",
            "properties": {},
        }
        if isinstance(parameters, dict):
            parameters = {
                k: v for k, v in parameters.items() if k != "additionalProperties"
            }
        out.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            }
        )
    return out


def _text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content or "")
    parts: list[str] = []
    saw_image = False
    for part in content:
        if not isinstance(part, dict):
            continue
        ptype = part.get("type")
        if ptype in {"input_text", "text", "output_text"}:
            parts.append(str(part.get("text") or ""))
        elif ptype in {"input_image", "image_url"}:
            saw_image = True
    text = "\n".join(p for p in parts if p).strip()
    if saw_image:
        note = (
            "(A phone photo was attached, but Electron cannot see images. "
            "Say you cannot view the photo unless they describe it.)"
        )
        text = f"{text}\n\n{note}".strip() if text else note
    return text


def _normalize_input_items(raw: Any) -> list[dict[str, Any]]:
    """Flatten Responses ``input`` into chat messages / tool results."""
    if raw is None:
        return []
    if isinstance(raw, str):
        return [{"role": "user", "content": raw}]
    if not isinstance(raw, list):
        return [{"role": "user", "content": str(raw)}]

    messages: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            messages.append({"role": "user", "content": item})
            continue
        if not isinstance(item, dict):
            continue
        itype = item.get("type")
        role = item.get("role")
        if itype == "function_call_output":
            call_id = str(item.get("call_id") or "").strip()
            msg: dict[str, Any] = {
                "role": "tool",
                "content": str(item.get("output") or ""),
            }
            if call_id:
                msg["tool_call_id"] = call_id
            messages.append(msg)
            continue
        if role == "user" or itype in {None, "message"}:
            content = item.get("content", item.get("text", ""))
            messages.append({"role": "user", "content": _text_from_content(content)})
            continue
        if role == "system":
            messages.append(
                {"role": "system", "content": _text_from_content(item.get("content"))}
            )
    return messages


def _client() -> OpenAI:
    if not SMALLEST_API_KEY:
        raise RuntimeError("SMALLEST_API_KEY is not set")
    return OpenAI(
        api_key=SMALLEST_API_KEY,
        base_url=SMALLEST_BASE_URL,
        timeout=SMALLEST_TIMEOUT,
    )


class ElectronSession:
    """Stateful chat history for one orchestrator process."""

    def __init__(self, *, model: str = DEFAULT_MODEL) -> None:
        self.model = model or DEFAULT_MODEL
        self._system: str = ""
        self._messages: list[dict[str, Any]] = []
        self._openai = _client()

    def reset(self) -> None:
        self._messages = []
        self._system = ""

    def create(
        self,
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        instructions: str | None = None,
        input: Any = None,
        previous_response_id: str | None = None,  # noqa: ARG002 — API parity
        llm_tts: Any | None = None,
        **_kwargs: Any,
    ) -> ElectronResponse:
        if model:
            self.model = model
        if instructions is not None:
            base = str(instructions).strip()
            self._system = f"{base}\n\n{_TOOL_HINT}" if base else _TOOL_HINT

        for msg in _normalize_input_items(input):
            self._messages.append(msg)

        payload_messages: list[dict[str, Any]] = []
        if self._system:
            payload_messages.append({"role": "system", "content": self._system})
        payload_messages.extend(self._messages)

        chat_tools = responses_tools_to_chat(tools)
        allowed = {
            str(t["function"]["name"]) for t in chat_tools if t.get("function")
        }

        stream_tts = llm_tts is not None
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": payload_messages,
            "temperature": SMALLEST_TEMPERATURE,
            "stream": stream_tts,
        }
        if chat_tools:
            kwargs["tools"] = chat_tools

        if stream_tts:
            content, tool_calls, response_id = self._chat_stream(
                kwargs, llm_tts=llm_tts, allowed=allowed
            )
        else:
            raw = self._openai.chat.completions.create(**kwargs)
            message = raw.choices[0].message
            content = str(message.content or "").strip()
            tool_calls = []
            for tc in message.tool_calls or []:
                tool_calls.append(
                    {
                        "id": tc.id,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                )
            response_id = f"electron_{uuid.uuid4().hex[:16]}"

        # Recover text-shaped tool calls.
        if not tool_calls and content and allowed:
            recovered = parse_text_tool_calls(content, allowed)
            if recovered:
                tool_calls = [
                    {
                        "id": c.call_id,
                        "function": {
                            "name": c.name,
                            "arguments": c.arguments,
                        },
                    }
                    for c in recovered
                ]
                content = ""
                print(
                    "[orchestrator] Electron text→tool recovery: "
                    + ", ".join(c["function"]["name"] for c in tool_calls),
                    flush=True,
                )

        assistant_msg: dict[str, Any] = {"role": "assistant", "content": content or None}
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": str(tc.get("id") or f"call_{uuid.uuid4().hex[:12]}"),
                    "type": "function",
                    "function": {
                        "name": str((tc.get("function") or {}).get("name") or ""),
                        "arguments": _args_to_json(
                            (tc.get("function") or {}).get("arguments")
                        ),
                    },
                }
                for tc in tool_calls
                if (tc.get("function") or {}).get("name")
            ]
        self._messages.append(assistant_msg)

        output: list[Any] = []
        if content:
            output.append(_MessageItem(content=[_OutputText(text=content)]))

        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            name = str(fn.get("name") or tc.get("name") or "").strip()
            if not name:
                continue
            call_id = str(tc.get("id") or f"call_{uuid.uuid4().hex[:12]}")
            output.append(
                _FunctionCall(
                    name=name,
                    arguments=_args_to_json(fn.get("arguments")),
                    call_id=call_id,
                    id=f"fc_{uuid.uuid4().hex[:12]}",
                )
            )

        if not output:
            output.append(_MessageItem(content=[_OutputText(text="")]))

        return ElectronResponse(id=response_id, output=output)

    def _chat_stream(
        self,
        kwargs: dict[str, Any],
        *,
        llm_tts: Any,
        allowed: set[str],
    ) -> tuple[str, list[dict[str, Any]], str]:
        from low_latency_tts import decoded_message_prefix

        response_id = f"electron_{uuid.uuid4().hex[:16]}"
        llm_tts.start_stream(response_id)
        print(f"[orchestrator] streaming Electron {response_id}", flush=True)

        content_parts: list[str] = []
        # index -> {id, name, arguments}
        acc: dict[int, dict[str, str]] = {}
        streamed_msg_len = 0
        spoken_content_len = 0
        give_call_id: str | None = None

        try:
            stream = self._openai.chat.completions.create(**kwargs)
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    content_parts.append(delta.content)
                    # Speak filler immediately (Electron voice-agent pattern).
                    piece = "".join(content_parts)
                    if len(piece) > spoken_content_len:
                        llm_tts.add_text_chunk(piece[spoken_content_len:])
                        spoken_content_len = len(piece)

                for tc in delta.tool_calls or []:
                    idx = int(tc.index) if tc.index is not None else 0
                    slot = acc.setdefault(
                        idx, {"id": "", "name": "", "arguments": ""}
                    )
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function and tc.function.name:
                        slot["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        slot["arguments"] += tc.function.arguments

                    name = slot["name"]
                    if name == "give_response_to_user" or (
                        not name and decoded_message_prefix(slot["arguments"])
                    ):
                        if slot["id"]:
                            give_call_id = slot["id"]
                            llm_tts.bind_call(response_id, slot["id"])
                        decoded = decoded_message_prefix(slot["arguments"])
                        if len(decoded) > streamed_msg_len:
                            # Prefer tool message over filler once it starts.
                            llm_tts.add_text_chunk(decoded[streamed_msg_len:])
                            streamed_msg_len = len(decoded)
        except Exception:
            llm_tts.abandon(response_id)
            raise
        finally:
            llm_tts.stop_stream()

        content = "".join(content_parts).strip()
        tool_calls: list[dict[str, Any]] = []
        for idx in sorted(acc):
            slot = acc[idx]
            name = (slot.get("name") or "").strip()
            if not name:
                continue
            tool_calls.append(
                {
                    "id": slot.get("id")
                    or give_call_id
                    or f"call_{uuid.uuid4().hex[:12]}",
                    "function": {
                        "name": name,
                        "arguments": slot.get("arguments") or "{}",
                    },
                }
            )
        return content, tool_calls, response_id


_session: ElectronSession | None = None


def get_session(model: str) -> ElectronSession:
    global _session
    if _session is None:
        _session = ElectronSession(model=model or DEFAULT_MODEL)
        print(
            f"[orchestrator] Smallest Electron brain model={_session.model} "
            f"url={SMALLEST_BASE_URL}",
            flush=True,
        )
    elif model and _session.model != model:
        _session.model = model
    return _session


def warmup(model: str) -> None:
    """Best-effort ping so the first utterance is not cold."""
    if not using_smallest():
        return
    try:
        session = get_session(model)
        t0 = time.monotonic()
        session.create(
            model=model,
            tools=[],
            instructions="Reply with OK only.",
            input="ping",
        )
        session.reset()
        print(
            f"[orchestrator] Electron warmed {model} in {time.monotonic() - t0:.1f}s",
            flush=True,
        )
    except Exception as e:  # noqa: BLE001 — startup best-effort
        print(f"[orchestrator] Electron warmup skipped: {e}", flush=True)
