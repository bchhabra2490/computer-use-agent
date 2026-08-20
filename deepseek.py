"""DeepSeek chat + tools helpers (OpenAI-compatible API)."""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

DEEPSEEK_API_KEY = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
DEEPSEEK_BASE_URL = (
    os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/")
    or "https://api.deepseek.com"
)
# Prefer V4 IDs (legacy deepseek-chat / deepseek-reasoner retired mid-2026).
COMPLEX_MODEL = (
    os.environ.get("COMPLEX_MODEL") or os.environ.get("DEEPSEEK_MODEL") or "deepseek-v4-pro"
).strip() or "deepseek-v4-pro"
AGENT_DEEPSEEK_MODEL = (
    os.environ.get("AGENT_DEEPSEEK_MODEL") or COMPLEX_MODEL
).strip() or COMPLEX_MODEL
COMPLEX_PLAN = os.environ.get("COMPLEX_PLAN", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
COMPLEX_THINKING = os.environ.get("COMPLEX_THINKING", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
# Thinking helps planning; for the CU tool loop default off (faster, cleaner tool_calls).
AGENT_DEEPSEEK_THINKING = os.environ.get("AGENT_DEEPSEEK_THINKING", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
COMPLEX_REASONING_EFFORT = (
    os.environ.get("COMPLEX_REASONING_EFFORT", "high").strip().lower() or "high"
)
COMPLEX_TIMEOUT = float(os.environ.get("COMPLEX_TIMEOUT", "90"))
AGENT_DEEPSEEK_TIMEOUT = float(
    os.environ.get("AGENT_DEEPSEEK_TIMEOUT", str(max(COMPLEX_TIMEOUT, 120)))
)


def configured() -> bool:
    return bool(DEEPSEEK_API_KEY)


def planning_enabled() -> bool:
    return COMPLEX_PLAN and configured()


def client(*, timeout: float | None = None) -> OpenAI:
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY is not set")
    return OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        timeout=COMPLEX_TIMEOUT if timeout is None else timeout,
    )


def _thinking_kwargs(*, thinking: bool) -> dict[str, Any]:
    if not thinking:
        return {}
    return {
        "reasoning_effort": COMPLEX_REASONING_EFFORT,
        "extra_body": {"thinking": {"type": "enabled"}},
    }


def chat(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    thinking: bool | None = None,
) -> str:
    """One chat completion. Returns assistant content (not reasoning_content)."""
    use_thinking = COMPLEX_THINKING if thinking is None else thinking
    kwargs: dict[str, Any] = {
        "model": (model or COMPLEX_MODEL).strip() or COMPLEX_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        **_thinking_kwargs(thinking=use_thinking),
    }
    resp = client().chat.completions.create(**kwargs)
    choice = (resp.choices or [None])[0]
    if choice is None or choice.message is None:
        return ""
    return (choice.message.content or "").strip()


def chat_with_tools(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    *,
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    thinking: bool | None = None,
) -> dict[str, Any]:
    """
    Chat completion with tools. Returns a serializable assistant message dict:
    ``{role, content, tool_calls?}`` suitable for appending to ``messages``.
    """
    use_thinking = AGENT_DEEPSEEK_THINKING if thinking is None else thinking
    kwargs: dict[str, Any] = {
        "model": (model or AGENT_DEEPSEEK_MODEL).strip() or AGENT_DEEPSEEK_MODEL,
        "messages": messages,
        "tools": tools,
        "temperature": temperature,
        "max_tokens": max_tokens,
        **_thinking_kwargs(thinking=use_thinking),
    }
    resp = client(timeout=AGENT_DEEPSEEK_TIMEOUT).chat.completions.create(**kwargs)
    choice = (resp.choices or [None])[0]
    if choice is None or choice.message is None:
        return {"role": "assistant", "content": ""}

    msg = choice.message
    out: dict[str, Any] = {
        "role": "assistant",
        "content": (msg.content or "") or "",
    }
    tool_calls = getattr(msg, "tool_calls", None) or []
    if tool_calls:
        serialized = []
        for tc in tool_calls:
            fn = getattr(tc, "function", None)
            serialized.append(
                {
                    "id": getattr(tc, "id", None) or f"call_{len(serialized)}",
                    "type": "function",
                    "function": {
                        "name": getattr(fn, "name", None) or "",
                        "arguments": getattr(fn, "arguments", None) or "{}",
                    },
                }
            )
        out["tool_calls"] = serialized
    return out


def args_dict(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            data = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
    return {}
