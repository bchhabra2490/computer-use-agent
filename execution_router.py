"""Deterministic fast/slow routing and specialist execution lanes.

The router intentionally avoids an LLM call. It supplies a strong execution
hint while every lane retains the full fallback toolset, so a bad route can
cost a little time but cannot make a task impossible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


ExecutionPath = Literal["fast", "slow"]
SpecialistLane = Literal["integration", "terminal", "browser", "desktop", "research", "visual"]


@dataclass(frozen=True)
class ExecutionRoute:
    path: ExecutionPath
    lane: SpecialistLane
    reason: str
    confidence: float
    recipe: str | None = None

    def prompt_block(self) -> str:
        lane_rules = {
            "integration": (
                "Use native tools, memory, timers, or MCP. Avoid desktop control unless "
                "the requested result truly requires visible UI interaction."
            ),
            "terminal": (
                "Use run_terminal for file, Git, script, and CLI work. Use the GUI only "
                "for a remaining step that cannot be verified from command output."
            ),
            "browser": (
                "Use browser_data first for public webpage reading and link discovery. "
                "Reuse the open browser state and use visual control for authentication, "
                "interactive page work, or a reported rendering fallback."
            ),
            "desktop": (
                "Prefer app skills, keyboard shortcuts, and Accessibility labels before "
                "screenshot coordinate actions."
            ),
            "research": (
                "Use connected search/API tools first, then browser_data for public sources. "
                "Collect only the evidence needed and use visual browser navigation only "
                "for authentication, interaction, or a reported rendering fallback."
            ),
            "visual": (
                "Use the screenshot and Accessibility together, verify each state change, "
                "and use app-specific skills for dense or unfamiliar interfaces."
            ),
        }
        speed = (
            "FAST PATH: attempt the deterministic or low-overhead method first. "
            "Fall back to visual computer use immediately if its verification fails."
            if self.path == "fast"
            else "SLOW PATH: prioritize visual grounding, verification, and careful multi-step execution."
        )
        recipe = f" Matching recipe candidate: {self.recipe}." if self.recipe else ""
        return (
            "Execution route (runtime-selected; advisory, fallback is allowed):\n"
            f"- path: {self.path}\n"
            f"- specialist lane: {self.lane}\n"
            f"- reason: {self.reason}\n"
            "- supporting specialists: safety verifier before sensitive effects; "
            "completion verifier before mark_done\n"
            f"- guidance: {speed} {lane_rules[self.lane]}{recipe}"
        )


_TERMINAL = re.compile(
    r"\b(git|repo(?:sitory)?|branch|commit|merge|rebase|file|folder|directory|"
    r"rename|move|copy|script|python|node|npm|pip|terminal|shell|command|disk space|storage)\b",
    re.I,
)
_BROWSER = re.compile(
    r"\b(browser|chrome|safari|edge|firefox|website|web page|url|google|search|"
    r"youtube|maps?|directions|gmail|amazon|netflix|linkedin|instagram|hacker news)\b|https?://",
    re.I,
)
_INTEGRATION = re.compile(
    r"\b(timer|remind|memory|remember|github issue|linear|mcp|weather|calendar|"
    r"what(?:'s| is) open|open tabs?|read (?:the )?screen)\b",
    re.I,
)
_DENSE_VISUAL = re.compile(
    r"\b(easyeda|kicad|cad|schematic|pcb|fusion 360|photoshop|figma|canvas|"
    r"drag|draw|diagram|pinout|form|checkout|upload|attach|settings pane|"
    r"multiple apps?|across apps?|compare visually)\b",
    re.I,
)
_SIMPLE_DESKTOP = re.compile(
    r"\b(open|launch|activate|focus|close|quit|switch to|press|shortcut|volume|"
    r"mute|unmute|pause|resume)\b",
    re.I,
)
_RESEARCH = re.compile(
    r"\b(research|investigate|look up|find information|compare|summarize sources?|"
    r"latest information|fact check|verify online)\b",
    re.I,
)


def _matching_recipe_name(text: str) -> str | None:
    try:
        from recipes import find_matching_recipe

        found = find_matching_recipe(text)
    except Exception:
        return None
    return found[0].name if found else None


def resolve_execution_route(task: str) -> ExecutionRoute:
    """Choose a cheap first approach and the specialist prompt lane."""
    text = (task or "").strip()
    recipe = _matching_recipe_name(text)
    if recipe:
        lane: SpecialistLane = (
            "integration"
            if _INTEGRATION.search(text)
            else "browser"
            if _BROWSER.search(text)
            else "desktop"
        )
        return ExecutionRoute("fast", lane, "A saved deterministic recipe matches.", 0.98, recipe)
    if _INTEGRATION.search(text):
        return ExecutionRoute("fast", "integration", "A native or connected tool can likely handle it.", 0.9)
    if _DENSE_VISUAL.search(text):
        return ExecutionRoute("slow", "visual", "The task needs dense visual grounding or careful multi-step UI work.", 0.92)
    if _TERMINAL.search(text):
        return ExecutionRoute("fast", "terminal", "CLI execution is likely faster and easier to verify.", 0.86)
    if _RESEARCH.search(text):
        return ExecutionRoute("fast", "research", "This is primarily information retrieval and synthesis.", 0.84)
    if _BROWSER.search(text):
        path: ExecutionPath = "slow" if re.search(r"\b(fill|submit|post|send|buy|checkout|login)\b", text, re.I) else "fast"
        return ExecutionRoute(path, "browser", "The work is primarily browser navigation.", 0.82)
    if _SIMPLE_DESKTOP.search(text):
        return ExecutionRoute("fast", "desktop", "This appears to be a short app or keyboard operation.", 0.78)
    return ExecutionRoute("slow", "visual", "No verified deterministic path was found.", 0.55)
