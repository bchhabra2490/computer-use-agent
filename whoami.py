"""who_am_i tool: load this project's README so the agent can describe itself."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
README_PATH = ROOT / "README.md"

_HTML_RE = re.compile(r"<[^>]+>", re.DOTALL)


def read_project_readme(
    *,
    readme_path: Path | None = None,
    max_chars: int = 24_000,
) -> str:
    """Return README markdown with HTML stripped (demo embeds, etc.)."""
    path = Path(readme_path) if readme_path is not None else README_PATH
    if not path.is_file():
        return (
            "README.md was not found. You are a personal computer-use voice "
            "assistant (Jarvis) that drives the Mac desktop with mouse, "
            "keyboard, and screenshots."
        )
    text = path.read_text(encoding="utf-8")
    text = _HTML_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n… (truncated)"
    return text


def format_whoami_output(*, readme_path: Path | None = None) -> str:
    readme = read_project_readme(readme_path=readme_path)
    return (
        "Project README follows. Answer who you are from this text. Then speak "
        "a short summary (one or two sentences) — do not read the README aloud, "
        "no markdown, no raw URLs unless asked.\n\n"
        f"{readme}"
    )


WHO_AM_I_TOOL = {
    "type": "function",
    "name": "who_am_i",
    "description": (
        "Read this project's README to answer who you are, what you can do, "
        "how you run, and how you were built. Call this when the user asks "
        "about you, this agent, Jarvis, Rekha, your capabilities, setup, or "
        "the computer-use-agent project. Do not start_task or guess."
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


def run_whoami_tool(_name: str = "who_am_i", _args: dict | None = None) -> str:
    return format_whoami_output()
