"""Local Ollama backend for the voice orchestrator (chat + tools).

Emulates enough of the OpenAI Responses shape (``.id``, ``.output`` with
``function_call`` / ``message`` items) so ``orchestrator._process_response``
can stay unchanged. STT/TTS keep using the real OpenAI/Sarvam clients.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any

ORCHESTRATOR_BACKEND = (
    os.environ.get("ORCHESTRATOR_BACKEND", "openai").strip().lower() or "openai"
)
OLLAMA_URL = (
    os.environ.get("ORCHESTRATOR_OLLAMA_URL", "http://127.0.0.1:11434").strip().rstrip("/")
)
OLLAMA_TIMEOUT = float(os.environ.get("ORCHESTRATOR_OLLAMA_TIMEOUT", "120"))
# qwen3 thinking tokens burn latency; keep off unless explicitly enabled.
OLLAMA_THINK = os.environ.get("ORCHESTRATOR_OLLAMA_THINK", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

_TOOL_TEXT_BLOCK = re.compile(
    r"(?ms)^\s*([a-zA-Z_][\w]{0,64})\s*\n\s*(\{.*\})\s*$"
)
_TOOL_XML = re.compile(
    r"(?is)<tool_call>\s*(\{.*?\})\s*</tool_call>"
)
_TOOL_HINT = (
    "CRITICAL: Use the API tool_calls mechanism only. Never print a tool name "
    "followed by JSON in your message content. Never reply with plain assistant "
    "text when a tool applies — call the tool."
)


def using_ollama() -> bool:
    return ORCHESTRATOR_BACKEND in {"ollama", "local"}


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
class OllamaResponse:
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


def _new_function_call(name: str, arguments: Any) -> _FunctionCall:
    return _FunctionCall(
        name=name,
        arguments=_args_to_json(arguments),
        call_id=f"call_{uuid.uuid4().hex[:12]}",
        id=f"fc_{uuid.uuid4().hex[:12]}",
    )


def parse_text_tool_calls(content: str, allowed: set[str]) -> list[_FunctionCall]:
    """
    Some local models (esp. with large tool lists) emit:
        give_response_to_user
        {"message": "...", "final": true}
    instead of structured tool_calls. Recover those so the orchestrator loop works.
    """
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
        name = m.group(1)
        try:
            args = json.loads(m.group(2))
        except json.JSONDecodeError:
            return []
        if isinstance(args, dict):
            return [_new_function_call(name, args)]

    # Bare JSON that includes a tool name field.
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


def responses_tools_to_ollama(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Convert Responses-style function tools to Ollama/OpenAI chat tools."""
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
            "(A phone photo was attached, but the local text model cannot see images. "
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
            messages.append(
                {
                    "role": "tool",
                    "content": str(item.get("output") or ""),
                }
            )
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


class OllamaSession:
    """Stateful chat history for one orchestrator process."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str = OLLAMA_URL,
        timeout: float = OLLAMA_TIMEOUT,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._system: str = ""
        self._messages: list[dict[str, Any]] = []

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
        **_kwargs: Any,
    ) -> OllamaResponse:
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

        ollama_tools = responses_tools_to_ollama(tools)
        allowed = {
            str(t["function"]["name"]) for t in ollama_tools if t.get("function")
        }
        body: dict[str, Any] = {
            "model": self.model,
            "messages": payload_messages,
            "stream": False,
            "think": OLLAMA_THINK,
            "options": {"temperature": 0},
        }
        if ollama_tools:
            body["tools"] = ollama_tools

        raw = self._chat(body)
        message = raw.get("message") if isinstance(raw, dict) else None
        if not isinstance(message, dict):
            message = {"role": "assistant", "content": ""}

        content = str(message.get("content") or "").strip()
        tool_calls = list(message.get("tool_calls") or [])

        # Recover text-shaped tool calls into structured ones for the local loop.
        if not tool_calls and content and allowed:
            recovered = parse_text_tool_calls(content, allowed)
            if recovered:
                tool_calls = [
                    {
                        "id": c.call_id,
                        "function": {
                            "name": c.name,
                            "arguments": json.loads(c.arguments or "{}"),
                        },
                    }
                    for c in recovered
                ]
                message = {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": tool_calls,
                }
                content = ""
                print(
                    "[orchestrator] Ollama text→tool recovery: "
                    + ", ".join(c.name for c in recovered),
                    flush=True,
                )

        self._messages.append(message)

        response_id = f"ollama_{uuid.uuid4().hex[:16]}"
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
            item_id = f"fc_{uuid.uuid4().hex[:12]}"
            output.append(
                _FunctionCall(
                    name=name,
                    arguments=_args_to_json(fn.get("arguments")),
                    call_id=call_id,
                    id=item_id,
                )
            )

        if not output:
            output.append(_MessageItem(content=[_OutputText(text="")]))

        return OllamaResponse(id=response_id, output=output)

    def _chat(self, body: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:400]
            raise RuntimeError(f"Ollama HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            raise RuntimeError(f"Ollama request failed: {e}") from e


_session: OllamaSession | None = None


def get_session(model: str) -> OllamaSession:
    global _session
    if _session is None:
        _session = OllamaSession(model=model)
        print(
            f"[orchestrator] local Ollama brain model={model} url={OLLAMA_URL}",
            flush=True,
        )
    elif model and _session.model != model:
        _session.model = model
    return _session


def warmup(model: str) -> None:
    """Best-effort model load so the first utterance is not cold."""
    if not using_ollama():
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
            f"[orchestrator] Ollama warmed {model} in {time.monotonic() - t0:.1f}s",
            flush=True,
        )
    except Exception as e:  # noqa: BLE001 — startup best-effort
        print(f"[orchestrator] Ollama warmup skipped: {e}", flush=True)
