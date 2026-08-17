"""Per-turn ephemeral context (not durable memory).

Live desktop occupancy, skill/MCP catalogs, and the memory *index* are rebuilt
each turn with a character budget. Facts the user would edit stay in
``memory/``; the last occupancy snapshot is only written under ``.runtime/``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app_status import RUNTIME_DIR

# Soft caps so the system prompt does not grow without bound.
BUDGET_DISPLAYS = int(os.environ.get("CONTEXT_BUDGET_DISPLAYS", "2500"))
BUDGET_SKILLS = int(os.environ.get("CONTEXT_BUDGET_SKILLS", "2000"))
BUDGET_MEMORIES = int(os.environ.get("CONTEXT_BUDGET_MEMORIES", "2500"))
BUDGET_MCP = int(os.environ.get("CONTEXT_BUDGET_MCP", "3500"))


@dataclass
class ContextBundle:
    displays: str
    skills: str
    memories: str
    mcp: str
    geometry: str = ""

    def desktop_block(self) -> str:
        parts = [p for p in (self.geometry, self.displays) if p.strip()]
        return "\n\n".join(parts)


def _clip(text: str, limit: int) -> str:
    body = (text or "").strip()
    if limit <= 0 or len(body) <= limit:
        return body
    keep = max(0, limit - 18)
    return body[:keep].rstrip() + "\n… (truncated)"


def persist_ephemeral_desktop(
    text: str,
    *,
    runtime_dir: Path | None = None,
) -> Path | None:
    """Write the live layout next to status.json — not under memory/."""
    body = (text or "").strip()
    if not body:
        return None
    root = Path(runtime_dir) if runtime_dir is not None else RUNTIME_DIR
    try:
        root.mkdir(parents=True, exist_ok=True)
        path = root / "desktop.txt"
        path.write_text(body + "\n", encoding="utf-8")
        return path
    except OSError as e:
        print(f"[context] could not save desktop snapshot: {e}", flush=True)
        return None


def assemble_context(
    *,
    monitors: list[dict] | None = None,
    screenshot_size: tuple[int, int] | None = None,
    include_geometry: bool = False,
    persist: bool = True,
    runtime_dir: Path | None = None,
    occupancy: list[dict[str, Any]] | None = None,
    frontmost: str | None = None,
) -> ContextBundle:
    """Build the catalogs injected into orchestrator / agent prompts."""
    from actions import format_display_context
    from displays import format_monitor_occupancy
    from mcp_client import format_mcp_catalog
    from memory import format_memory_catalog
    from skills import format_skill_catalog

    geometry = ""
    if include_geometry:
        geometry = format_display_context(monitors, screenshot_size=screenshot_size)
    displays = format_monitor_occupancy(
        monitors=monitors,
        occupancy=occupancy,
        frontmost=frontmost,
    )
    if persist:
        persist_ephemeral_desktop(displays, runtime_dir=runtime_dir)

    bundle = ContextBundle(
        displays=_clip(displays, BUDGET_DISPLAYS),
        skills=_clip(format_skill_catalog(), BUDGET_SKILLS),
        memories=_clip(format_memory_catalog(), BUDGET_MEMORIES),
        mcp=_clip(format_mcp_catalog(), BUDGET_MCP),
        geometry=_clip(geometry, BUDGET_DISPLAYS) if geometry else "",
    )
    return bundle
