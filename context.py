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
BUDGET_DISPLAYS = int(os.environ.get("CONTEXT_BUDGET_DISPLAYS", "4500"))
BUDGET_SKILLS = int(os.environ.get("CONTEXT_BUDGET_SKILLS", "2000"))
BUDGET_MEMORIES = int(os.environ.get("CONTEXT_BUDGET_MEMORIES", "2500"))
BUDGET_MCP = int(os.environ.get("CONTEXT_BUDGET_MCP", "3500"))


NOT_TO_DO_PATH = Path(__file__).resolve().parent / "not_to_do.md"
BUDGET_NOT_TO_DO = int(os.environ.get("CONTEXT_BUDGET_NOT_TO_DO", "1200"))
BUDGET_ORCH_DESKTOP_TEXT = int(os.environ.get("ORCHESTRATOR_DESKTOP_TEXT_CHARS", "12000"))
BUDGET_ORCH_AX = int(os.environ.get("ORCHESTRATOR_DESKTOP_AX_CHARS", "8000"))


@dataclass
class ContextBundle:
    displays: str
    skills: str
    memories: str
    mcp: str
    geometry: str = ""
    not_to_do: str = ""

    def desktop_block(self) -> str:
        parts = [p for p in (self.geometry, self.displays) if p.strip()]
        return "\n\n".join(parts)


def _clip(text: str, limit: int) -> str:
    body = (text or "").strip()
    if limit <= 0 or len(body) <= limit:
        return body
    keep = max(0, limit - 18)
    return body[:keep].rstrip() + "\n… (truncated)"


def format_not_to_do(*, path: Path | None = None) -> str:
    """Always-on don'ts for the agent and orchestrator."""
    src = Path(path) if path is not None else NOT_TO_DO_PATH
    try:
        text = src.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    try:
        from artifact_paths import output_rule

        text = text + "\n\n- " + output_rule()
    except Exception:
        pass
    return text


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
        not_to_do=_clip(format_not_to_do(), BUDGET_NOT_TO_DO),
    )
    return bundle


@dataclass(frozen=True)
class TurnDesktopContext:
    """Live desktop snapshot attached to one orchestrator user turn."""

    text: str
    screenshot_png: bytes | None = None


def orchestrator_desktop_enabled() -> bool:
    return os.environ.get("ORCHESTRATOR_DESKTOP_CONTEXT", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _orchestrator_desktop_ax_enabled() -> bool:
    return os.environ.get("ORCHESTRATOR_DESKTOP_AX", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _orchestrator_desktop_screenshot_enabled() -> bool:
    return os.environ.get("ORCHESTRATOR_DESKTOP_SCREENSHOT", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _capture_desktop_context(
    *,
    enable_screenshot: bool,
    enable_ax: bool,
    header: str,
    log_prefix: str = "orchestrator",
) -> TurnDesktopContext:
    monitors: list[dict] | None = None
    screenshot_png: bytes | None = None
    screenshot_size: tuple[int, int] | None = None

    try:
        from actions import DesktopController, list_monitors

        monitors = list_monitors()
        if enable_screenshot:
            desktop = DesktopController()
            screenshot_png = desktop.capture_screenshot()
            screenshot_size = (desktop._model_w, desktop._model_h)
    except Exception as e:
        print(f"[{log_prefix}] desktop screenshot failed: {e}", flush=True)

    desktop_text = ""
    try:
        bundle = assemble_context(
            monitors=monitors,
            screenshot_size=screenshot_size,
            include_geometry=True,
            persist=False,
        )
        desktop_text = bundle.desktop_block()
    except Exception as e:
        desktop_text = f"(display context unavailable: {e})"

    ax_text = ""
    if enable_ax:
        try:
            from accessibility import read_ui_text

            ax_text = read_ui_text(max_chars=BUDGET_ORCH_AX)
        except Exception as e:
            ax_text = f"(accessibility unavailable: {e})"

    parts = [header, desktop_text]
    if ax_text.strip():
        parts.extend(["", "Accessibility text (frontmost app):", ax_text.strip()])
    if screenshot_png:
        parts.extend(
            [
                "",
                "A screenshot of the attached display(s) is included with this message. "
                "Use it with the text above to answer what is on screen.",
            ]
        )

    text = _clip("\n\n".join(p for p in parts if p), BUDGET_ORCH_DESKTOP_TEXT)
    if screenshot_png:
        kb = len(screenshot_png) / 1024.0
        print(
            f"[{log_prefix}] desktop context: {len(text)} chars, screenshot {kb:.0f} KB",
            flush=True,
        )
    elif text.strip():
        print(f"[{log_prefix}] desktop context: {len(text)} chars (no screenshot)", flush=True)

    return TurnDesktopContext(text=text, screenshot_png=screenshot_png)


def read_screen() -> TurnDesktopContext:
    """
    Explicit screen read for the read_screen tool — display layout, AX text,
    and screenshot (always attempted).
    """
    return _capture_desktop_context(
        enable_screenshot=True,
        enable_ax=True,
        header="Screen read (read_screen):",
        log_prefix="read_screen",
    )


def read_screen_vision_input(png: bytes) -> dict[str, Any]:
    """Follow-up user message so the model sees the read_screen PNG."""
    import base64

    b64 = base64.b64encode(png).decode("ascii")
    return {
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": (
                    "Screenshot from read_screen (same moment as the tool output above). "
                    "Use it with the accessibility and display text."
                ),
            },
            {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{b64}",
                "detail": "high",
            },
        ],
    }


def capture_turn_desktop_context() -> TurnDesktopContext:
    """
    Capture display occupancy, accessibility text, and a desktop screenshot
    for one orchestrator question (what the user is looking at now).
    """
    if not orchestrator_desktop_enabled():
        return TurnDesktopContext("")

    return _capture_desktop_context(
        enable_screenshot=_orchestrator_desktop_screenshot_enabled(),
        enable_ax=_orchestrator_desktop_ax_enabled(),
        header="Desktop snapshot for this question (what the user is looking at on the Mac now):",
        log_prefix="orchestrator",
    )
