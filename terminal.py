"""
Run local shell commands for the computer-use agent.

Captures stdout/stderr with a timeout and truncates oversized output so tool
results stay model-friendly.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

DEFAULT_TIMEOUT = float(os.environ.get("TERMINAL_TIMEOUT", "60"))
MAX_OUTPUT_CHARS = int(os.environ.get("TERMINAL_MAX_OUTPUT", "30000"))


def run_command(
    command: str,
    *,
    cwd: str | None = None,
    timeout_seconds: float | None = None,
    max_output_chars: int | None = None,
) -> str:
    """
    Execute `command` via the user's shell and return a text report.

    Uses the shell in $SHELL (fallback /bin/zsh on macOS, /bin/bash otherwise).
    """
    command = (command or "").strip()
    if not command:
        return "Error: empty command."

    timeout = DEFAULT_TIMEOUT if timeout_seconds is None else float(timeout_seconds)
    if timeout <= 0:
        return "Error: timeout_seconds must be positive."

    limit = MAX_OUTPUT_CHARS if max_output_chars is None else int(max_output_chars)
    if limit < 500:
        limit = 500

    workdir: str | None = None
    if cwd is not None and str(cwd).strip():
        path = Path(str(cwd).strip()).expanduser()
        if not path.is_dir():
            return f"Error: cwd does not exist or is not a directory: {path}"
        workdir = str(path.resolve())

    shell = os.environ.get("SHELL") or (
        "/bin/zsh" if os.path.exists("/bin/zsh") else "/bin/bash"
    )

    try:
        completed = subprocess.run(
            command,
            shell=True,
            executable=shell,
            cwd=workdir,
            capture_output=True,
            text=False,  # decode ourselves — OCR/cat of images must not crash the agent
            timeout=timeout,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired as e:
        out = _decode(e.stdout)
        err = _decode(e.stderr)
        return _format_report(
            command=command,
            cwd=workdir,
            exit_code=None,
            stdout=out,
            stderr=err,
            limit=limit,
            note=f"Timed out after {timeout:g}s (process killed).",
        )
    except OSError as e:
        return f"Error running command: {e}"

    return _format_report(
        command=command,
        cwd=workdir,
        exit_code=completed.returncode,
        stdout=_decode(completed.stdout),
        stderr=_decode(completed.stderr),
        limit=limit,
        note=None,
    )


def _decode(data: str | bytes | None) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    # PNG/JPEG dumps and odd OCR bytes are common; never raise into the agent loop.
    if data[:4] == b"\x89PNG" or data[:3] == b"\xff\xd8\xff":
        return (
            f"(binary image data, {len(data)} bytes — not shown as text. "
            "Do not cat/dump image files; use the computer tool + vision instead.)"
        )
    return data.decode("utf-8", errors="replace")


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    head = limit // 2
    tail = limit - head
    return (
        text[:head] + f"\n… [{len(text) - limit} chars omitted] …\n" + text[-tail:],
        True,
    )


def _format_report(
    *,
    command: str,
    cwd: str | None,
    exit_code: int | None,
    stdout: str,
    stderr: str,
    limit: int,
    note: str | None,
) -> str:
    # Split the budget roughly between streams when both are large.
    stdout_t, stdout_cut = _truncate(stdout, limit)
    stderr_budget = max(2000, limit - len(stdout_t))
    stderr_t, stderr_cut = _truncate(stderr, stderr_budget)

    lines = [
        f"command: {command}",
        f"cwd: {cwd or os.getcwd()}",
    ]
    if exit_code is None:
        lines.append("exit_code: (none — timed out)")
    else:
        lines.append(f"exit_code: {exit_code}")
    if note:
        lines.append(f"note: {note}")
    if stdout_cut or stderr_cut:
        lines.append("note: output truncated to fit tool result size.")

    lines.append("--- stdout ---")
    lines.append(stdout_t if stdout_t else "(empty)")
    lines.append("--- stderr ---")
    lines.append(stderr_t if stderr_t else "(empty)")
    return "\n".join(lines)
