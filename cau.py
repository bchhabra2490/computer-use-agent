"""CLI for the computer-use-agent daemon: ``cau start`` / ``cau stop``.

Runs the voice orchestrator in the background (detached session, logs to
``logs/cau.log``). ``cau start`` also installs a ``cau`` shim on PATH when
possible so the command works from any directory.
"""

from __future__ import annotations

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
PID_PATH = RUNTIME_DIR / "cau.pid"
LOG_PATH = ROOT / "logs" / "cau.log"
SHIM_MARK = "# cau — computer-use-agent daemon CLI"

_STOP_WAIT_SECONDS = 8.0


def _python() -> str:
    venv = ROOT / ".venv" / "bin" / "python"
    if venv.is_file():
        return str(venv)
    return sys.executable


def _read_pid_file() -> int | None:
    try:
        raw = PID_PATH.read_text(encoding="utf-8").strip()
        pid = int(raw)
    except (OSError, ValueError):
        return None
    return pid if pid > 0 else None


def _write_pid_file(pid: int) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(f"{pid}\n", encoding="utf-8")


def _clear_pid_file() -> None:
    try:
        PID_PATH.unlink(missing_ok=True)
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
    script = ROOT / "cau.py"
    return f"""#!/bin/sh
{SHIM_MARK}
exec "{py}" "{script}" "$@"
"""


def _is_our_shim(path: Path) -> bool:
    try:
        return SHIM_MARK in path.read_text(encoding="utf-8")
    except OSError:
        return False


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
    """Write ``cau`` wrappers onto PATH. Returns paths written."""
    body = _shim_body()
    written: list[Path] = []
    for directory in _writable_bin_dirs():
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        dest = directory / "cau"
        if dest.exists() and not _is_our_shim(dest):
            continue
        try:
            dest.write_text(body, encoding="utf-8")
            dest.chmod(dest.stat().st_mode | 0o111)
            written.append(dest)
        except OSError:
            continue
    return written


def cau_on_path() -> bool:
    found = shutil.which("cau")
    return bool(found)


def cmd_start(*, no_auto: bool = False, max_steps: int = 25) -> int:
    pid = running_pid()
    if pid is not None:
        print(f"cau is already running (pid {pid})")
        return 0

    shims = install_shim()
    if shims and not cau_on_path():
        print(
            "Installed cau to "
            + ", ".join(str(p) for p in shims)
            + ' — add that directory to PATH if `cau` is not found.',
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
        log_fh.write(f"\n--- cau start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
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
            f"cau failed to start (exit {proc.returncode}). See {LOG_PATH}",
            file=sys.stderr,
        )
        return 1

    _write_pid_file(proc.pid)
    print(f"cau started (pid {proc.pid})")
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
        from app_status import pid_alive, read_status

        tray = read_status().get("tray_pid")
        if pid_alive(tray):
            try:
                os.kill(int(tray), signal.SIGTERM)
            except OSError:
                pass
    except Exception:
        pass


def cmd_stop() -> int:
    pid = running_pid()
    if pid is None:
        print("cau is not running")
        _clear_pid_file()
        return 0

    try:
        from app_status import request_quit

        request_quit()
    except Exception:
        pass

    stopped = _terminate(pid)
    _stop_tray()
    _clear_pid_file()
    if stopped:
        print(f"cau stopped (pid {pid})")
        return 0
    print(f"cau did not exit (pid {pid})", file=sys.stderr)
    return 1


def cmd_status() -> int:
    pid = running_pid()
    if pid is None:
        print("cau is not running")
        return 1
    print(f"cau is running (pid {pid})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cau",
        description="Start and stop the computer-use-agent daemon",
    )
    sub = parser.add_subparsers(dest="command", required=True)

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

    args = parser.parse_args(argv)
    if args.command == "start":
        return cmd_start(no_auto=args.no_auto, max_steps=args.max_steps)
    if args.command == "stop":
        return cmd_stop()
    if args.command == "status":
        return cmd_status()
    if args.command == "restart":
        cmd_stop()
        return cmd_start(no_auto=args.no_auto, max_steps=args.max_steps)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
