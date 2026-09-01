"""Canonical paths for user-facing files created by the computer-use agent."""

from __future__ import annotations

import os
from pathlib import Path


def default_output_dir() -> Path:
    """Default destination unless the user explicitly names another location."""
    configured = (os.environ.get("AGENT_OUTPUT_DIR") or "").strip()
    if configured:
        if configured == "~":
            return Path.home()
        if configured.startswith("~/"):
            return Path.home() / configured[2:]
        return Path(configured)
    return Path.home() / "Documents" / "Computer Use Agent"


def ensure_output_dir() -> Path:
    path = default_output_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def output_rule() -> str:
    path = default_output_dir()
    return (
        f"Default user-facing output folder: {path}. "
        "Save every file the agent creates or downloads there—including PNG, SVG, "
        "PDF, CSV, JSON, text, reports, exports, and generated media—unless the user "
        "explicitly specifies a different destination in the current request. "
        "Create the folder if needed. This rule overrides example Desktop/Downloads "
        "paths in skills. Internal logs, runtime state, caches, recipes, and memory "
        "screenshots stay in their project-managed locations."
    )
