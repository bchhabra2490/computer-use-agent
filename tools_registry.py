"""Single registry of function tools for the orchestrator and computer agent.

Schemas live here once. ``openai_tools(brain)`` filters by who may call them.
Shared handlers (memory, who_am_i, MCP) are dispatched from both loops.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from memory import MEMORY_TOOLS, run_memory_tool
from whoami import WHO_AM_I_TOOL, run_whoami_tool

Brain = Literal["orchestrator", "agent"]

ORCHESTRATOR: Brain = "orchestrator"
AGENT: Brain = "agent"


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
        "short spoken question, not a numbered list. Under the computer agent the "
        "orchestrator speaks this so the two loops do not compete for the mic."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": (
                    "One short question to speak. Natural wording; titles "
                    "instead of raw URLs. Not a numbered list."
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

LIST_SKILLS_TOOL = {
    "type": "function",
    "name": "list_skills",
    "description": (
        "List available project skills (name + description). Call this if you "
        "need to refresh the catalog; prefer matching the task to a skill, then "
        "call read_skill before acting."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "unused": {
                "type": "boolean",
                "description": "Unused. Always pass false.",
            },
        },
        "required": ["unused"],
        "additionalProperties": False,
    },
    "strict": True,
}

READ_SKILL_TOOL = {
    "type": "function",
    "name": "read_skill",
    "description": (
        "Load the full instructions for a skill by name (from skills/<name>/SKILL.md). "
        "Always read a relevant skill before performing that kind of task. Optionally "
        "read a companion file inside the skill folder."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Skill name (e.g. open-app, web-search).",
            },
            "file": {
                "type": ["string", "null"],
                "description": (
                    "Optional relative path inside the skill folder to read instead "
                    "of SKILL.md (e.g. reference.md). Pass null to load the main skill."
                ),
            },
        },
        "required": ["name", "file"],
        "additionalProperties": False,
    },
    "strict": True,
}

READ_UI_TEXT_TOOL = {
    "type": "function",
    "name": "read_ui_text",
    "description": (
        "Read visible UI text via the macOS Accessibility API (no screenshot). "
        "Prefer this over screenshots when you need labels, field values, menu "
        "items, or window titles. Returns a compact AX tree with optional click "
        "centers in screen points. Many Electron/WebGL/CAD apps expose little AX "
        "data — if the result says no nodes were found, use the computer tool "
        "screenshot instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "app": {
                "type": ["string", "null"],
                "description": ("App name or bundle id to inspect. Pass null for the " "frontmost application."),
            },
        },
        "required": ["app"],
        "additionalProperties": False,
    },
    "strict": True,
}

RUN_TERMINAL_TOOL = {
    "type": "function",
    "name": "run_terminal",
    "description": (
        "Run a shell command on this Mac and return stdout, stderr, and exit code. "
        "Prefer this for file/git/CLI work, checking paths, installing packages, or "
        "anything faster than driving the Terminal GUI. Do not use for interactive "
        "programs that need a TTY (vim, ssh password prompts, etc.). Avoid "
        "destructive commands (rm -rf, diskutil erase, etc.) unless the user "
        "explicitly asked."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute.",
            },
            "cwd": {
                "type": ["string", "null"],
                "description": (
                    "Working directory for the command. Pass null to use the " "agent process current directory."
                ),
            },
            "timeout_seconds": {
                "type": ["number", "null"],
                "description": (
                    "Seconds before the process is killed. Pass null for the " "default (60, or TERMINAL_TIMEOUT)."
                ),
            },
        },
        "required": ["command", "cwd", "timeout_seconds"],
        "additionalProperties": False,
    },
    "strict": True,
}

MARK_DONE_TOOL = {
    "type": "function",
    "name": "mark_done",
    "description": (
        "End this computer-use run. Call when the user's request is fully "
        "satisfied and no other UI or tool action is required — do not keep "
        "clicking or taking screenshots. Also call if the user says to mark "
        "the task done."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": (
                    "One or two spoken sentences on what was completed. Write as "
                    "if talking to the user: natural wording, names and titles "
                    "(the Hacker News post, the YouTube video), never raw URLs, "
                    "markdown, or https links that are painful to hear."
                ),
            },
        },
        "required": ["summary"],
        "additionalProperties": False,
    },
    "strict": True,
}

COMPUTER_TOOL = {"type": "computer"}

SHARED_TOOL_NAMES = frozenset(
    {
        "who_am_i",
        "list_memories",
        "read_memory",
        "save_memory",
        "save_screen_memory",
        "mcp_call",
    }
)


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    schema: dict[str, Any]
    brains: frozenset[str]


def _entry(schema: dict[str, Any], *brains: Brain) -> RegisteredTool:
    return RegisteredTool(name=str(schema["name"]), schema=schema, brains=frozenset(brains))


REGISTRY: tuple[RegisteredTool, ...] = (
    _entry(WHO_AM_I_TOOL, ORCHESTRATOR, AGENT),
    _entry(START_TASK_TOOL, ORCHESTRATOR),
    _entry(ASK_USER_TOOL, ORCHESTRATOR, AGENT),
    _entry(GIVE_RESPONSE_TOOL, ORCHESTRATOR),
    *(_entry(tool, ORCHESTRATOR, AGENT) for tool in MEMORY_TOOLS),
    _entry(LIST_SKILLS_TOOL, AGENT),
    _entry(READ_SKILL_TOOL, AGENT),
    _entry(READ_UI_TEXT_TOOL, AGENT),
    _entry(RUN_TERMINAL_TOOL, AGENT),
    _entry(MARK_DONE_TOOL, AGENT),
)


def openai_tools(brain: Brain) -> list[dict[str, Any]]:
    """OpenAI Responses tool list for one brain, plus MCP when connected."""
    from mcp_client import mcp_openai_tools

    tools: list[dict[str, Any]] = []
    if brain == AGENT:
        tools.append(COMPUTER_TOOL)
    for item in REGISTRY:
        if brain in item.brains:
            tools.append(item.schema)
    tools.extend(mcp_openai_tools(for_agent=(brain == AGENT)))
    return tools


def orchestrator_tools() -> list[dict[str, Any]]:
    return openai_tools(ORCHESTRATOR)


def agent_tools() -> list[dict[str, Any]]:
    return openai_tools(AGENT)


def tool_names(brain: Brain) -> set[str]:
    names = {item.name for item in REGISTRY if brain in item.brains}
    if brain == AGENT:
        names.add("computer")
    names.add("mcp_call")
    return names


def run_shared_tool(
    name: str,
    args: dict[str, Any] | None = None,
    *,
    client: Any | None = None,
) -> str:
    """Execute tools that both brains share. Raises KeyError if not shared."""
    args = args or {}
    if name == "who_am_i":
        return run_whoami_tool(name, args)
    if name in {"list_memories", "read_memory", "save_memory", "save_screen_memory"}:
        return run_memory_tool(name, args, client=client)
    if name == "mcp_call":
        from mcp_client import run_mcp_tool

        return run_mcp_tool(name, args)
    raise KeyError(f"Not a shared tool: {name}")
