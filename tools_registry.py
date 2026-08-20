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
                    "The user's goal in their words (or a short leftover step). "
                    "Do not write a UI screenplay: no Chrome/Spotlight/new-tab/"
                    "keypress steps, no 'wait for the page', no fallback apps. "
                    "Recipes and the computer agent decide how."
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
        "Speak the answer once at an appropriate length for speech, then stop. "
        "Complete but concise — not a teaser and not a long lecture. "
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
                    "What to say aloud. Match depth to the question: one or two "
                    "sentences for simple facts; brief coverage of each part for "
                    "comparisons or specs. Natural spoken sentences — no teaser, "
                    "no filler. Use titles and names, not raw URLs or https links "
                    "(painful to hear). No markdown."
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

SET_TIMER_TOOL = {
    "type": "function",
    "name": "set_timer",
    "description": (
        "Start a native countdown (no Clock app, no sleep, no computer-use). "
        "Use for 'set a 5 minute timer' and for reminders ('remind me in 5 minutes "
        "to check the oven'). Convert the duration to seconds. Always posts a "
        "macOS notification when it ends. Set speak=true and message when they "
        "asked to be reminded of something (Jarvis will say it). Returns immediately; "
        "do not wait for the timer and do not start_task."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "seconds": {
                "type": "number",
                "description": "Duration in seconds (1 to 86400).",
            },
            "label": {
                "type": "string",
                "description": "Short name, e.g. pasta, oven, tea.",
            },
            "speak": {
                "type": "boolean",
                "description": (
                    "True if they asked to be reminded of something (TTS). "
                    "False for a silent countdown plus notification only."
                ),
            },
            "message": {
                "type": ["string", "null"],
                "description": (
                    "What to say (and show) when it fires if speak is true. "
                    "Pass null to use '{label} is done.'"
                ),
            },
        },
        "required": ["seconds", "label", "speak", "message"],
        "additionalProperties": False,
    },
    "strict": True,
}

LIST_TIMERS_TOOL = {
    "type": "function",
    "name": "list_timers",
    "description": "List active native timers (id, label, remaining seconds).",
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

CANCEL_TIMER_TOOL = {
    "type": "function",
    "name": "cancel_timer",
    "description": (
        "Cancel a native timer by id (from set_timer / list_timers) or by label. "
        "Pass null for the unused field."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "id": {
                "type": ["string", "null"],
                "description": "Timer id (e.g. t1). Pass null to match by label.",
            },
            "label": {
                "type": ["string", "null"],
                "description": "Cancel all timers with this label. Pass null if using id.",
            },
        },
        "required": ["id", "label"],
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

WEB_SEARCH_TOOL = {
    "type": "function",
    "name": "web_search",
    "description": (
        "Search the public web and return titles, snippets, and links. Use this "
        "for live facts (weather, news, who/what/when) when no MCP search tool "
        "fits. Pass a normal search query, not a URL. Then give_response_to_user "
        "from the results — do not ask permission to look it up. Follow a "
        "specific result URL with http_get only if you need the page body."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query, e.g. Mohali weather today.",
            },
            "max_results": {
                "type": "number",
                "description": "How many results to return (1–8). Use 5 if unsure.",
            },
        },
        "required": ["query", "max_results"],
        "additionalProperties": False,
    },
    "strict": True,
}

HTTP_GET_TOOL = {
    "type": "function",
    "name": "http_get",
    "description": (
        "Fetch a public https URL and return text (HTML stripped). Use when you "
        "already have a specific URL (from web_search or the user). Not a search "
        "box — for a query, call web_search first. Do not use for localhost."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Full https URL to GET.",
            },
        },
        "required": ["url"],
        "additionalProperties": False,
    },
    "strict": True,
}

LIST_OPEN_APPS_TOOL = {
    "type": "function",
    "name": "list_open_apps",
    "description": (
        "Live snapshot of running Mac apps, visible windows by display, and "
        "open browser tabs with titles/URLs (Chrome, Chromium, Brave, Edge, "
        "Safari). Does not launch browsers. Use when the user asks what is open "
        "or which tabs they have, or when you need a fresh occupancy list."
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
        "programs that need a TTY (vim, ssh password prompts, etc.). Do not sleep "
        "to wait out a song or video, and do not use macOS `say` for user-facing "
        "speech (use mark_done / ask_user). Avoid destructive commands (rm -rf, "
        "diskutil erase, etc.) unless the user explicitly asked."
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
        "web_search",
        "http_get",
        "list_open_apps",
        "set_timer",
        "list_timers",
        "cancel_timer",
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
    _entry(LIST_OPEN_APPS_TOOL, ORCHESTRATOR, AGENT),
    _entry(WEB_SEARCH_TOOL, ORCHESTRATOR, AGENT),
    _entry(HTTP_GET_TOOL, ORCHESTRATOR, AGENT),
    _entry(SET_TIMER_TOOL, ORCHESTRATOR, AGENT),
    _entry(LIST_TIMERS_TOOL, ORCHESTRATOR, AGENT),
    _entry(CANCEL_TIMER_TOOL, ORCHESTRATOR, AGENT),
    _entry(LIST_SKILLS_TOOL, AGENT),
    _entry(READ_SKILL_TOOL, AGENT),
    _entry(READ_UI_TEXT_TOOL, AGENT),
    _entry(RUN_TERMINAL_TOOL, AGENT),
    _entry(MARK_DONE_TOOL, AGENT),
)


def openai_tools(
    brain: Brain,
    *,
    exclude: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    """OpenAI Responses tool list for one brain, plus MCP when connected."""
    from mcp_client import mcp_openai_tools

    skip = exclude or frozenset()
    tools: list[dict[str, Any]] = []
    if brain == AGENT:
        tools.append(COMPUTER_TOOL)
    for item in REGISTRY:
        if brain in item.brains and item.name not in skip:
            tools.append(item.schema)
    tools.extend(mcp_openai_tools(for_agent=(brain == AGENT)))
    return tools


def orchestrator_tools(*, exclude: frozenset[str] | None = None) -> list[dict[str, Any]]:
    return openai_tools(ORCHESTRATOR, exclude=exclude)


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
    if name == "list_open_apps":
        from displays import format_monitor_occupancy

        return format_monitor_occupancy()
    if name == "http_get":
        from http_get import run_http_get

        return run_http_get(args)
    if name == "web_search":
        from web_search import run_web_search

        return run_web_search(args)
    if name in {"set_timer", "list_timers", "cancel_timer"}:
        from timers import run_timer_tool

        return run_timer_tool(name, args)
    raise KeyError(f"Not a shared tool: {name}")
