"""CLI for the computer-use-agent daemon: ``cua start`` / ``cua stop``.

Runs the voice orchestrator in the background (detached session, logs to
``logs/cua.log``). ``cua start`` also installs a ``cua`` shim on PATH when
possible so the command works from any directory.

Full command reference::

    cua help

Passive desktop observer (separate process, drafts only)::

    cua observe start
    cua observe list
    cua observe accept 20260818T134913Z_google-chrome m1 s2

MCP apps (Linear, GitHub, …) connect with browser login::

    cua mcp login linear
    cua mcp status
    cua mcp logout linear

Rewrite verbose skill playbooks::

    cua skills condense
    cua skills condense --name open-app --dry-run
    cua skills merge --dry-run
    cua skills merge

Speaker enrollment (who is talking)::

    cua speaker enroll --name Bharat
    cua speaker list
    cua speaker test
    cua speaker test --speak-prompts

Fn-key dictation (hold Fn to paste speech into the focused field)::

    cua dictation start
    cua dictation stop
    cua dictation status

Blobatar face overlay::

    cua face
    cua face pebble
    cua face jarvis
"""

from __future__ import annotations

# Load .env before subcommands read OPENAI_* / TTS_* / etc.
from envfile import load_dotenv

load_dotenv()

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / ".runtime"
PID_PATH = RUNTIME_DIR / "cua.pid"
_LEGACY_PID_PATH = RUNTIME_DIR / "cau.pid"
LOG_PATH = ROOT / "logs" / "cua.log"
SHIM_MARK = "# cua — computer-use-agent daemon CLI"
_LEGACY_SHIM_MARK = "# cau — computer-use-agent daemon CLI"

_STOP_WAIT_SECONDS = 8.0


def _python() -> str:
    venv = ROOT / ".venv" / "bin" / "python"
    if venv.is_file():
        return str(venv)
    return sys.executable


def _read_pid_at(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
        pid = int(raw)
    except (OSError, ValueError):
        return None
    return pid if pid > 0 else None


def _read_pid_file() -> int | None:
    return _read_pid_at(PID_PATH) or _read_pid_at(_LEGACY_PID_PATH)


def _write_pid_file(pid: int) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(f"{pid}\n", encoding="utf-8")
    try:
        _LEGACY_PID_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def _clear_pid_file() -> None:
    for path in (PID_PATH, _LEGACY_PID_PATH):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _pid_alive(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _orchestrator_pid_from_status() -> int | None:
    try:
        from app_status import pid_alive, read_status

        pid = read_status().get("orchestrator_pid")
        return int(pid) if pid_alive(pid) else None
    except Exception:
        return None


def running_pid() -> int | None:
    """PID of a live orchestrator, if any (pid file or status.json)."""
    pid = _read_pid_file()
    if _pid_alive(pid):
        return pid
    if pid is not None:
        _clear_pid_file()
    return _orchestrator_pid_from_status()


def _shim_body() -> str:
    py = _python()
    script = ROOT / "cua.py"
    return f"""#!/bin/sh
{SHIM_MARK}
exec "{py}" "{script}" "$@"
"""


def _is_our_shim(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return SHIM_MARK in text or _LEGACY_SHIM_MARK in text


def _writable_bin_dirs() -> list[Path]:
    dirs: list[Path] = []
    local = Path.home() / ".local" / "bin"
    dirs.append(local)
    for raw in ("/opt/homebrew/bin", "/usr/local/bin"):
        path = Path(raw)
        if path.is_dir() and os.access(path, os.W_OK):
            dirs.append(path)
    return dirs


def install_shim() -> list[Path]:
    """Write ``cua`` wrappers onto PATH. Returns paths written."""
    body = _shim_body()
    written: list[Path] = []
    for directory in _writable_bin_dirs():
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        dest = directory / "cua"
        if dest.exists() and not _is_our_shim(dest):
            continue
        try:
            dest.write_text(body, encoding="utf-8")
            dest.chmod(dest.stat().st_mode | 0o111)
            written.append(dest)
        except OSError:
            continue
        # Retarget leftover ``cau`` shims so they still work after the rename.
        legacy = directory / "cau"
        if not legacy.exists() or _is_our_shim(legacy):
            try:
                legacy.write_text(body, encoding="utf-8")
                legacy.chmod(legacy.stat().st_mode | 0o111)
            except OSError:
                pass
    return written


def cua_on_path() -> bool:
    found = shutil.which("cua")
    return bool(found)


def cmd_install() -> int:
    shims = install_shim()
    if not shims:
        print("Could not install cua onto PATH", file=sys.stderr)
        return 1
    print("Installed cua to " + ", ".join(str(p) for p in shims))
    if not cua_on_path():
        print("Add that directory to PATH if `cua` is not found.", flush=True)
    return 0


def cmd_start(*, no_auto: bool = False, max_steps: int = 25) -> int:
    pid = running_pid()
    if pid is not None:
        print(f"cua is already running (pid {pid})")
        return 0

    shims = install_shim()
    if shims and not cua_on_path():
        print(
            "Installed cua to "
            + ", ".join(str(p) for p in shims)
            + " — add that directory to PATH if `cua` is not found.",
            flush=True,
        )

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    orch = ROOT / "orchestrator.py"
    cmd = [_python(), str(orch)]
    if not no_auto:
        cmd.append("--auto")
    if max_steps != 25:
        cmd.extend(["--max-steps", str(max_steps)])

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("PYTHONPATH", str(ROOT))

    log_fh = open(LOG_PATH, "a", encoding="utf-8")
    try:
        log_fh.write(f"\n--- cua start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        log_fh.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )
    finally:
        log_fh.close()

    time.sleep(0.4)
    if proc.poll() is not None:
        print(
            f"cua failed to start (exit {proc.returncode}). See {LOG_PATH}",
            file=sys.stderr,
        )
        return 1

    _write_pid_file(proc.pid)
    print(f"cua started (pid {proc.pid})")
    print(f"logs: {LOG_PATH}")
    return 0


def _terminate(pid: int, *, wait: float = _STOP_WAIT_SECONDS) -> bool:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return not _pid_alive(pid)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.15)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    time.sleep(0.2)
    return not _pid_alive(pid)


def _stop_tray() -> None:
    try:
        from status_tray import stop_tray

        stop_tray()
    except Exception:
        pass


def _stop_phone_gateway() -> None:
    try:
        from phone_gateway import stop_phone_gateway

        stop_phone_gateway()
    except Exception:
        pass


def cmd_stop() -> int:
    pid = running_pid()
    if pid is None:
        print("cua is not running")
        _clear_pid_file()
        return 0

    try:
        from app_status import request_quit

        request_quit()
    except Exception:
        pass

    stopped = _terminate(pid)
    _stop_tray()
    _stop_phone_gateway()
    _clear_pid_file()
    if stopped:
        print(f"cua stopped (pid {pid})")
        return 0
    print(f"cua did not exit (pid {pid})", file=sys.stderr)
    return 1


def cmd_status() -> int:
    pid = running_pid()
    if pid is None:
        print("cua is not running")
        return 1
    print(f"cua is running (pid {pid})")
    return 0


def format_help() -> str:
    """Full CLI reference for ``cua help``."""
    return f"""\
cua — personal computer-use agent (voice orchestrator + tools)

DAEMON
  cua start [--no-auto] [--max-steps N]
      Start the voice orchestrator in the background (logs: logs/cua.log).
      Installs a PATH shim on first run (~/.local/bin/cua).
  cua stop              Stop the orchestrator, tray, and phone gateway.
  cua restart           Stop then start.
  cua status            Print whether the daemon is running.
  cua install           Install the cua shim onto PATH.

VOICE (foreground — same orchestrator, attached terminal)
  python orchestrator.py [--auto]
  python agent.py --voice [--auto]

  Configure in .env (see README “Voice configuration”):
    OPENAI_API_KEY          required
    STT_PROVIDER=openai|sarvam|whisperflow
    TTS_PROVIDER=openai|sarvam|piper|kokoro
    WAKE_MODEL / WAKE_PHRASE / WAKE_MODE=model|phrase
    TTS_BARGE_IN=1          wake word interrupts speech
    TTS_CONFIRM_HEARD=1     speak “I heard: …” after each listen
    MIC_DEVICE=             sounddevice input name or index

OBSERVER (separate process — drafts only; not started by cua start)
  cua observe start       Watch your clicks; draft memories/skills after ~10 min.
  cua observe stop
  cua observe status
  cua observe list        Pending drafts (m1 / s1 item refs).
  cua observe accept ID [m1 s2 …] [--memory NAME] [--skill NAME]
  cua observe accept --all
  cua observe reject ID [items…] [--all]

SPEAKER ID (who is talking — set SPEAKER_ID=1 in .env)
  cua speaker enroll [--name YourName] [--speak-prompts]
  cua speaker list
  cua speaker test [--verbose] [--speak-prompts]
  cua speaker delete NAME

DICTATION (hold Fn → paste speech into focused field; DICTATION=1 in .env)
  cua dictation start
  cua dictation stop
  cua dictation status

FACE (blobatar overlay — any name, or pebble / droplet / cloud / sun)
  cua face              List blobatars (* = current)
  cua face pebble       Curated shortcut
  cua face jarvis       Any other name hashes to a unique blobatar

SKILLS (playbooks under skills/*/SKILL.md)
  cua skills condense [--name SKILL] [--force] [--dry-run]
  cua skills merge [--name SKILL …] [--dry-run]

MCP (Linear, GitHub, Notion, … — browser login)
  cua mcp login linear|github|notion
  cua mcp login SLUG --url https://…/mcp
  cua mcp login github --token ghp_…
  cua mcp logout NAME
  cua mcp status
  cua mcp apps

PHONE GATEWAY (companion app — PHONE_GATEWAY=1 in .env)
  Starts with cua start when enabled. HTTP on port 8742 (LAN / Tailscale).
  Token: .runtime/phone.token (max 5 chars).
  Pass "sink": "phone" on /v1/command|audio|photo for phone TTS playback.
  Run standalone: python phone_gateway.py

COMPUTER AGENT (typed task, no voice)
  python agent.py "Open Notes and write today's date" [--auto] [--max-steps N]

OTHER
  python status_tray.py   Menu-bar icon alone (auto-starts with orchestrator).
  cua help                Show this reference.

Docs: README.md in {ROOT.name}/
Env template: .env.example
"""


def cmd_help() -> int:
    print(format_help())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cua",
        description="Start and stop the computer-use-agent daemon",
        add_help=True,
    )
    sub = parser.add_subparsers(dest="command", required=False)

    start_p = sub.add_parser("start", help="Start the orchestrator in the background")
    start_p.add_argument(
        "--no-auto",
        action="store_true",
        help="Do not pass --auto (computer agent will confirm each step)",
    )
    start_p.add_argument("--max-steps", type=int, default=25)

    restart_p = sub.add_parser("restart", help="Stop, then start")
    restart_p.add_argument(
        "--no-auto",
        action="store_true",
        help="Do not pass --auto (computer agent will confirm each step)",
    )
    restart_p.add_argument("--max-steps", type=int, default=25)

    sub.add_parser("stop", help="Stop the background orchestrator")
    sub.add_parser("status", help="Print whether the daemon is running")
    sub.add_parser("install", help="Install the cua command on PATH")
    sub.add_parser("help", help="Show all commands (daemon, observe, speaker, …)")

    mcp_p = sub.add_parser(
        "mcp",
        help="Connect MCP apps by logging in (Linear, GitHub, …)",
    )
    mcp_sub = mcp_p.add_subparsers(dest="mcp_command", required=True)
    login_p = mcp_sub.add_parser(
        "login",
        help="Open a browser, log in to an app, enable it in mcp.json",
    )
    login_p.add_argument(
        "name",
        nargs="?",
        default=None,
        help="App name (linear, github, notion) or a custom slug with --url",
    )
    login_p.add_argument(
        "--url",
        default=None,
        help="Remote MCP URL (required for apps not in the known list)",
    )
    login_p.add_argument(
        "--token",
        default=None,
        help="Access token (GitHub PAT). Prefer `cua mcp login github` with gh CLI.",
    )
    logout_p = mcp_sub.add_parser("logout", help="Forget stored OAuth tokens")
    logout_p.add_argument("name", help="App name (linear, github, …)")
    mcp_sub.add_parser("status", help="Show which MCP apps are logged in")
    mcp_sub.add_parser("apps", help="List known apps you can log in to")

    skills_p = sub.add_parser("skills", help="Manage skills/ playbooks")
    skills_sub = skills_p.add_subparsers(dest="skills_command", required=True)
    condense_p = skills_sub.add_parser(
        "condense",
        help="Rewrite verbose SKILL.md files to use fewer tokens",
    )
    condense_p.add_argument(
        "--name",
        action="append",
        dest="names",
        metavar="SKILL",
        default=None,
        help="Only this skill (repeatable). Implies rewrite even if already short.",
    )
    condense_p.add_argument(
        "--force",
        action="store_true",
        help="Condense every skill, including short ones",
    )
    condense_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Call the model and print what would change; do not write",
    )
    condense_p.add_argument(
        "--min-chars",
        type=int,
        default=None,
        help="Length threshold (description + body). Default: 1800 or SKILL_CONDENSE_MIN_CHARS",
    )
    merge_p = skills_sub.add_parser(
        "merge",
        help="Fold duplicate playbooks into one and delete the extras",
    )
    merge_p.add_argument(
        "--name",
        action="append",
        dest="names",
        metavar="SKILL",
        default=None,
        help="Only consider these skills (repeatable). Need at least two.",
    )
    merge_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Propose merges; do not write or delete",
    )

    obs_p = sub.add_parser(
        "observe",
        help="Passive desktop observer (draft memories/skills from your own clicks)",
    )
    obs_sub = obs_p.add_subparsers(dest="observe_command", required=True)
    obs_sub.add_parser("start", help="Start the observer daemon (does not start with cua start)")
    obs_sub.add_parser("stop", help="Stop the observer daemon")
    obs_sub.add_parser("status", help="Show observer pid and pending draft count")
    obs_sub.add_parser("list", help="List proposed drafts")

    dict_p = sub.add_parser(
        "dictation",
        help="Hold-Fn dictation — Realtime STT into the focused text field",
    )
    dict_sub = dict_p.add_subparsers(dest="dictation_command", required=True)
    dict_sub.add_parser("start", help="Start the dictation hotkey daemon")
    dict_sub.add_parser("stop", help="Stop the dictation daemon")
    dict_sub.add_parser("status", help="Show dictation pid")

    face_p = sub.add_parser(
        "face",
        aliases=["blobatar"],
        help="Choose the blobatar face overlay (any name, or pebble/droplet/cloud/sun)",
    )
    face_p.add_argument(
        "name",
        nargs="*",
        help="preset name, or any seed (omit to list)",
    )

    accept_p = obs_sub.add_parser(
        "accept",
        help="Write a proposed draft into memory/ and skills/",
    )
    accept_p.add_argument(
        "id",
        nargs="?",
        default=None,
        help="Draft folder name (from cua observe list)",
    )
    accept_p.add_argument(
        "items",
        nargs="*",
        help="Item refs from list, e.g. m1 s2 (omit to accept the whole draft)",
    )
    accept_p.add_argument(
        "--memory",
        action="append",
        dest="memories",
        metavar="NAME",
        default=None,
        help="Accept this memory name (repeatable)",
    )
    accept_p.add_argument(
        "--skill",
        action="append",
        dest="skills",
        metavar="NAME",
        default=None,
        help="Accept this skill name (repeatable)",
    )
    accept_p.add_argument(
        "--all",
        action="store_true",
        dest="all_drafts",
        help="Accept every proposed draft",
    )
    reject_p = obs_sub.add_parser("reject", help="Discard a proposed draft or selected items")
    reject_p.add_argument(
        "id",
        nargs="?",
        default=None,
        help="Draft folder name (from cua observe list)",
    )
    reject_p.add_argument(
        "items",
        nargs="*",
        help="Item refs from list, e.g. m2 s1 (omit to reject the whole draft)",
    )
    reject_p.add_argument(
        "--memory",
        action="append",
        dest="memories",
        metavar="NAME",
        default=None,
        help="Drop this memory name (repeatable)",
    )
    reject_p.add_argument(
        "--skill",
        action="append",
        dest="skills",
        metavar="NAME",
        default=None,
        help="Drop this skill name (repeatable)",
    )
    reject_p.add_argument(
        "--all",
        action="store_true",
        dest="all_drafts",
        help="Reject every proposed draft",
    )

    speaker_p = sub.add_parser(
        "speaker",
        help="Enroll voices so Jarvis can tell who is speaking",
    )
    speaker_sub = speaker_p.add_subparsers(dest="speaker_command", required=True)
    speaker_enroll_p = speaker_sub.add_parser(
        "enroll",
        help="Read five passages (3 long + 2 short) to create a voice profile",
    )
    speaker_enroll_p.add_argument("--name", default=None, help="Your display name")
    speaker_enroll_p.add_argument(
        "--max-seconds",
        type=float,
        default=45.0,
        help="Max seconds per passage recording",
    )
    speaker_enroll_p.add_argument(
        "--speak-prompts",
        action="store_true",
        help="Speak brief TTS instructions before each passage",
    )
    speaker_sub.add_parser("list", help="List enrolled speakers")
    speaker_delete_p = speaker_sub.add_parser("delete", help="Remove a speaker profile")
    speaker_delete_p.add_argument("name", help="Name or slug")
    speaker_test_p = speaker_sub.add_parser(
        "test",
        help="Record once and identify who is speaking",
    )
    speaker_test_p.add_argument("--max-seconds", type=float, default=15.0)
    speaker_test_p.add_argument(
        "--verbose",
        action="store_true",
        help="Print similarity scores for every enrolled speaker",
    )
    speaker_test_p.add_argument(
        "--speak-prompts",
        action="store_true",
        help="After identification, speak Hey <name> or Hey Stranger via TTS",
    )

    args = parser.parse_args(argv)
    if args.command is None:
        return cmd_help()
    if args.command == "help":
        return cmd_help()
    if args.command == "start":
        return cmd_start(no_auto=args.no_auto, max_steps=args.max_steps)
    if args.command == "stop":
        return cmd_stop()
    if args.command == "status":
        return cmd_status()
    if args.command == "restart":
        cmd_stop()
        return cmd_start(no_auto=args.no_auto, max_steps=args.max_steps)
    if args.command == "install":
        return cmd_install()
    if args.command == "mcp":
        from mcp_auth import (
            cmd_mcp_login,
            cmd_mcp_logout,
            cmd_mcp_status,
            format_apps_help,
        )

        if args.mcp_command == "login":
            return cmd_mcp_login(args.name, url=args.url, token=args.token)
        if args.mcp_command == "logout":
            return cmd_mcp_logout(args.name)
        if args.mcp_command == "status":
            return cmd_mcp_status()
        if args.mcp_command == "apps":
            print(format_apps_help())
            return 0
        return 2
    if args.command == "skills":
        from skills import cmd_condense_skills, cmd_merge_skills

        if args.skills_command == "condense":
            return cmd_condense_skills(
                names=args.names,
                force=args.force,
                dry_run=args.dry_run,
                min_chars=args.min_chars,
            )
        if args.skills_command == "merge":
            return cmd_merge_skills(names=args.names, dry_run=args.dry_run)
        return 2
    if args.command == "observe":
        import observe as observe_mod

        if args.observe_command == "start":
            return observe_mod.cmd_start()
        if args.observe_command == "stop":
            return observe_mod.cmd_stop()
        if args.observe_command == "status":
            return observe_mod.cmd_status()
        if args.observe_command == "list":
            return observe_mod.cmd_list()
        if args.observe_command == "accept":
            return observe_mod.cmd_accept(
                name=args.id,
                all_drafts=args.all_drafts,
                items=args.items,
                memories=args.memories,
                skills=args.skills,
            )
        if args.observe_command == "reject":
            return observe_mod.cmd_reject(
                name=args.id,
                all_drafts=args.all_drafts,
                items=args.items,
                memories=args.memories,
                skills=args.skills,
            )
        return 2
    if args.command == "dictation":
        import dictation as dictation_mod

        if args.dictation_command == "start":
            return dictation_mod.cmd_start()
        if args.dictation_command == "stop":
            return dictation_mod.cmd_stop()
        if args.dictation_command == "status":
            return dictation_mod.cmd_status()
        return 2
    if args.command in {"face", "blobatar"}:
        from face_overlay import cmd_face

        return cmd_face(args.name)
    if args.command == "speaker":
        from speaker_enroll import cmd_delete, cmd_enroll, cmd_list, cmd_test

        if args.speaker_command == "enroll":
            return cmd_enroll(
                args.name,
                max_seconds=args.max_seconds,
                speak_prompts=args.speak_prompts,
            )
        if args.speaker_command == "list":
            return cmd_list()
        if args.speaker_command == "delete":
            return cmd_delete(args.name)
        if args.speaker_command == "test":
            return cmd_test(
                max_seconds=args.max_seconds,
                verbose=args.verbose,
                speak_prompts=args.speak_prompts,
            )
        return 2
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
