"""Pi launcher: same orchestrator as desktop, without computer-use.

Chat is the existing chat app, served in the browser (not a separate Pi UI).

    python pi_agent.py --env .env.pi --no-gpio
    python orchestrator.py --auto --pi
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from envfile import load_dotenv

ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Pi mode: orchestrator without computer-use; chat in the browser",
    )
    parser.add_argument("--env", default=".env.pi")
    parser.add_argument(
        "--no-gpio",
        action="store_true",
        help="Ignored; Pi mode uses the orchestrator wake word",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Load env and exit (does not probe arecord/GPIO)",
    )
    args = parser.parse_args(argv)
    loaded = load_dotenv(args.env, override=True)
    os.environ["COMPUTER_USE"] = "0"
    os.environ["CHAT_BROWSER"] = "1"
    os.environ.setdefault("CHAT_OVERLAY", "1")
    os.environ.setdefault("CHAT_BRIDGE_HOST", "0.0.0.0")
    if args.check:
        print(f"env={loaded or args.env}")
        print("Pi mode uses python orchestrator.py --auto --pi")
        return
    from orchestrator import main as orch_main

    orch_main(["--auto", "--pi"])


if __name__ == "__main__":
    main()
