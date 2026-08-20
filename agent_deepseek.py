"""DeepSeek-driven computer-use loop with OpenAI vision for screenshots.

DeepSeek cannot use OpenAI's native ``computer`` tool. Instead:
  - DeepSeek chooses tools / desktop actions (chat completions + function calling)
  - After each action batch we capture a screenshot and ask an OpenAI vision
    model to describe it (with coordinates), then feed that text back to DeepSeek
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from openai import OpenAI

import deepseek as ds
from evaluator import EVAL_EVERY
from task_log import TaskLog
from tools_registry import agent_tools

CU_VISION_MODEL = (
    os.environ.get("CU_VISION_MODEL")
    or os.environ.get("MEMORY_VISION_MODEL")
    or "gpt-4o-mini"
).strip() or "gpt-4o-mini"

AGENT_BACKEND = (os.environ.get("AGENT_BACKEND") or "openai").strip().lower() or "openai"


def using_deepseek_agent() -> bool:
    return AGENT_BACKEND in {"deepseek", "ds"} and ds.configured()


def responses_tools_to_chat(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Responses-style function tools (+ synthetic computer) to chat tools."""
    out: list[dict[str, Any]] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        if tool.get("type") == "computer":
            out.append(_computer_chat_tool())
            continue
        if tool.get("type") not in {None, "function"}:
            continue
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else None
        name = str((fn or {}).get("name") or tool.get("name") or "").strip()
        if not name:
            continue
        description = str((fn or {}).get("description") or tool.get("description") or "")
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
    # Ensure computer tool is present even if agent_tools() shape changes.
    if not any(
        (t.get("function") or {}).get("name") == "computer" for t in out if isinstance(t, dict)
    ):
        out.insert(0, _computer_chat_tool())
    return out


def _computer_chat_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "computer",
            "description": (
                "Run one or more mouse/keyboard actions on the real Mac desktop, "
                "then receive an OpenAI vision description of the new screenshot. "
                "Coordinates (x, y) are in screenshot pixel space "
                "(origin top-left of the combined multi-monitor image). "
                "Prefer small batches (1–4 actions). Use wait only when the UI is loading."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "actions": {
                        "type": "array",
                        "description": "Ordered desktop actions to run before the next screenshot.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": [
                                        "click",
                                        "double_click",
                                        "move",
                                        "scroll",
                                        "keypress",
                                        "type",
                                        "drag",
                                        "wait",
                                        "screenshot",
                                    ],
                                },
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                                "button": {
                                    "type": "string",
                                    "enum": ["left", "right", "middle"],
                                },
                                "text": {"type": "string"},
                                "keys": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "scroll_x": {"type": "number"},
                                "scroll_y": {"type": "number"},
                                "ms": {"type": "number"},
                                "path": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "x": {"type": "number"},
                                            "y": {"type": "number"},
                                        },
                                    },
                                },
                            },
                            "required": ["type"],
                        },
                    }
                },
                "required": ["actions"],
            },
        },
    }


@dataclass
class _FnCall:
    type: str = "function_call"
    name: str = ""
    arguments: str = ""
    call_id: str = ""


def describe_screenshot(
    openai_client: OpenAI,
    screenshot_b64: str,
    *,
    width: int,
    height: int,
    task: str,
    last_actions: str = "",
) -> str:
    """Ask OpenAI vision what is on screen; return text for DeepSeek."""
    prompt = (
        f"You are the eyes for a desktop computer-use agent. "
        f"Screenshot size: {width}x{height} pixels (origin top-left). "
        f"Monitors may be stitched and labeled screen N.\n\n"
        f"User goal:\n{task}\n\n"
    )
    if last_actions:
        prompt += f"Actions just taken:\n{last_actions}\n\n"
    prompt += (
        "Describe what is visible now for the agent that cannot see images:\n"
        "1) Active app / window titles\n"
        "2) Key UI elements with approximate (x,y) centers in screenshot pixels\n"
        "3) Whether the goal looks done, blocked, or needs a specific next click/type\n"
        "4) Any dialogs, errors, or loading states\n"
        "Be concrete and coordinate-heavy. No markdown fences."
    )
    try:
        response = openai_client.responses.create(
            model=CU_VISION_MODEL,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{screenshot_b64}",
                            "detail": "high",
                        },
                    ],
                }
            ],
        )
    except Exception as e:
        return f"(OpenAI vision failed: {e}. Use read_ui_text / list_open_apps if needed.)"

    parts: list[str] = []
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) != "message":
            continue
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", None) == "output_text":
                text = (getattr(part, "text", None) or "").strip()
                if text:
                    parts.append(text)
    text = "\n".join(parts).strip()
    return text or "(Vision returned an empty description.)"


def _normalize_actions(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    actions: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        atype = str(item.get("type") or "").strip()
        if not atype:
            continue
        action = {"type": atype}
        for key in (
            "x",
            "y",
            "button",
            "text",
            "keys",
            "scroll_x",
            "scroll_y",
            "ms",
            "path",
        ):
            if key in item and item[key] is not None:
                action[key] = item[key]
        actions.append(action)
    return actions


def _action_summary(actions: list[dict[str, Any]]) -> str:
    bits = []
    for a in actions:
        t = a.get("type")
        if t in {"click", "double_click", "move"}:
            bits.append(f"{t}({a.get('x')},{a.get('y')})")
        elif t == "type":
            bits.append(f"type({str(a.get('text') or '')[:40]!r})")
        elif t == "keypress":
            bits.append(f"keypress({a.get('keys')})")
        elif t == "scroll":
            bits.append(f"scroll({a.get('scroll_x')},{a.get('scroll_y')})")
        elif t == "wait":
            bits.append(f"wait({a.get('ms')}ms)")
        else:
            bits.append(str(t))
    return "; ".join(bits)


def run_deepseek_computer_loop(
    *,
    openai_client: OpenAI,
    desktop: Any,
    task: str,
    prompt_body: str,
    log: TaskLog,
    max_steps: int,
    auto: bool,
    handle_function_call: Callable[..., dict],
    pending_user_context: Callable[[], str | None],
    coach: Callable[..., str | None] | None = None,
    shot_w: int,
    shot_h: int,
    consume_mark_done: Callable[[], None] | None = None,
    voice: bool = False,
) -> tuple[str, list[str]]:
    """
    DeepSeek tool loop. ``handle_function_call`` / ``consume_mark_done`` may raise
    the same TaskMarkedDone used by the OpenAI path. Returns
    (status, last_assistant_messages) when the model stops without mark_done.
    """
    tools = responses_tools_to_chat(agent_tools())
    model = ds.AGENT_DEEPSEEK_MODEL
    print(
        f"[agent] backend=deepseek model={model} vision={CU_VISION_MODEL}",
        flush=True,
    )

    # Initial eyes: screenshot → OpenAI vision → text for DeepSeek.
    shot = desktop.capture_screenshot()
    import base64

    shot_b64 = base64.b64encode(shot).decode("utf-8")
    # Prefer live model dimensions from the controller after capture.
    width = int(getattr(desktop, "_model_w", 0) or shot_w or 0) or shot_w
    height = int(getattr(desktop, "_model_h", 0) or shot_h or 0) or shot_h
    vision = describe_screenshot(
        openai_client,
        shot_b64,
        width=width,
        height=height,
        task=task,
    )
    log.record(
        "cu_vision",
        vision[:200],
        {"model": CU_VISION_MODEL, "chars": len(vision), "bytes": len(shot)},
    )
    print(f"[vision] {vision[:160].replace(chr(10), ' ')}", flush=True)

    system = (
        "You are a desktop computer-use agent on macOS. You cannot see images — "
        "OpenAI vision describes each screenshot in text with (x,y) coordinates. "
        "Use the computer tool for clicks/typing; use other tools for skills, "
        "memory, MCP, terminal, timers, and mark_done when finished. "
        f"Screenshot coordinate space is {width}x{height} pixels (top-left origin). "
        "Never invent coordinates outside that space. Prefer skills/MCP when listed."
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": (
                f"{prompt_body}\n\n"
                f"=== Current screen (OpenAI vision, {width}x{height}) ===\n{vision}"
            ),
        },
    ]

    last_messages: list[str] = []
    steps = 0
    while steps < max_steps:
        if consume_mark_done is not None:
            consume_mark_done()  # may raise TaskMarkedDone

        assistant = ds.chat_with_tools(messages, tools, model=model)
        messages.append(assistant)
        content = str(assistant.get("content") or "").strip()
        if content:
            # Strip leaked text tool dumps if any.
            print(f"\n[agent/deepseek] {content[:300]}")
            last_messages.append(content)
            log.record("llm_response", content[:500], {"text": content[:4000]})

        tool_calls = list(assistant.get("tool_calls") or [])
        if not tool_calls:
            # Recover name\\n{json} tool dumps occasionally emitted by local-style models.
            recovered = _recover_text_tools(content, tools)
            if recovered:
                tool_calls = recovered
                assistant["tool_calls"] = recovered
                assistant["content"] = ""
                messages[-1] = assistant
            else:
                leftover = pending_user_context()
                if leftover:
                    messages.append({"role": "user", "content": leftover})
                    continue
                break

        last_shot_b64: str | None = None
        computer_ran = False
        for tc in tool_calls:
            fn = tc.get("function") if isinstance(tc, dict) else {}
            name = str((fn or {}).get("name") or "").strip()
            call_id = str(tc.get("id") or f"call_{uuid.uuid4().hex[:10]}")
            args_raw = (fn or {}).get("arguments")
            args = ds.args_dict(args_raw)

            if name == "computer":
                computer_ran = True
                actions = _normalize_actions(args.get("actions"))
                summary = _action_summary(actions)
                print(f"[computer] {summary}", flush=True)
                log.record("computer_actions", f"{len(actions)} action(s)", {"actions": actions})
                if not actions:
                    result = "Error: computer requires a non-empty actions array."
                else:
                    try:
                        desktop.run_actions(actions)
                        shot_bytes = desktop.capture_screenshot()
                        last_shot_b64 = base64.b64encode(shot_bytes).decode("utf-8")
                        width = int(getattr(desktop, "_model_w", 0) or width) or width
                        height = int(getattr(desktop, "_model_h", 0) or height) or height
                        vision = describe_screenshot(
                            openai_client,
                            last_shot_b64,
                            width=width,
                            height=height,
                            task=task,
                            last_actions=summary,
                        )
                        log.record(
                            "cu_vision",
                            vision[:200],
                            {
                                "model": CU_VISION_MODEL,
                                "chars": len(vision),
                                "bytes": len(shot_bytes),
                            },
                        )
                        print(
                            f"[vision] {vision[:160].replace(chr(10), ' ')}",
                            flush=True,
                        )
                        result = (
                            f"Actions executed: {summary}\n"
                            f"Screenshot {width}x{height} (OpenAI vision):\n{vision}"
                        )
                    except Exception as e:
                        result = f"Computer actions failed: {e}"
                        log.record("computer_error", str(e), {"error": str(e)})
                messages.append(
                    {"role": "tool", "tool_call_id": call_id, "content": result}
                )
                continue

            # Reuse OpenAI agent function handlers via a duck-typed call object.
            call = _FnCall(
                name=name,
                arguments=json.dumps(args) if not isinstance(args_raw, str) else (args_raw or "{}"),
                call_id=call_id,
            )
            out = handle_function_call(
                openai_client, call, log, auto=auto, voice=voice
            )
            output_text = str(out.get("output") or "")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": output_text,
                }
            )

        steps += 1
        mid = pending_user_context()
        if mid:
            messages.append({"role": "user", "content": mid})

        if (
            coach is not None
            and computer_ran
            and EVAL_EVERY > 0
            and steps % EVAL_EVERY == 0
        ):
            tip = coach(last_shot_b64, steps)
            if tip:
                messages.append({"role": "user", "content": tip})

    return "completed", last_messages


_TEXT_TOOL = re.compile(
    r"(?ms)^\s*([a-zA-Z_][\w]{0,64})\s*\n\s*(\{.*\})\s*$"
)


def _recover_text_tools(
    content: str, tools: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    allowed = {
        str((t.get("function") or {}).get("name") or "")
        for t in tools
        if isinstance(t, dict)
    }
    allowed.discard("")
    m = _TEXT_TOOL.match((content or "").strip())
    if not m or m.group(1) not in allowed:
        return []
    try:
        args = json.loads(m.group(2))
    except json.JSONDecodeError:
        return []
    if not isinstance(args, dict):
        return []
    return [
        {
            "id": f"call_{uuid.uuid4().hex[:10]}",
            "type": "function",
            "function": {
                "name": m.group(1),
                "arguments": json.dumps(args),
            },
        }
    ]
