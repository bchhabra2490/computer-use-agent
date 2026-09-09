# Raspberry Pi / headless

Pi mode is the **same** `orchestrator.py` as desktop. It hides `start_task`
(computer-use) and serves the existing chat app in a browser. Wake word,
live voice, barge-in, TTS, memory, timers, MCP, and the phone gateway stay.

```bash
python orchestrator.py --auto --pi
```

Same thing via the thin launcher (loads `.env.pi` first):

```bash
python pi_agent.py --env .env.pi --no-gpio
```

`--no-gpio` is accepted and unused. Voice uses the orchestrator wake word,
not a GPIO button.

## Laptop (this checkout)

Use the desktop venv and `.env` (or `.env.pi` with your API key):

```bash
python orchestrator.py --auto --pi
```

The terminal prints chat URLs like `http://<lan-ip>:8743/`.
Open that in a browser. No pairing token. Do not run a second desktop orchestrator on the
same ports (phone **8742**, chat **8743**).

## Chat app

There is no separate Pi web UI. The Electron chat renderer
(`chat_app/renderer`) is served by `chat_bridge`. `--pi` skips Electron
and binds the bridge on `0.0.0.0`.

Keep `CHAT_OVERLAY=1` (set by `--pi`). `cua chat on` also works in this mode.

## What is hidden

Only the orchestrator computer-use tool (`start_task`). Everything else in
the orchestrator loop is unchanged.

## Pi hardware

A Pi Zero 2 W may not load the full desktop stack (wake models, NumPy).
This path is the laptop / capable-Pi profile. Install `requirements.txt`,
not `requirements-pi.txt`.

Copy `.env.pi.example` to `.env.pi`, set `OPENAI_API_KEY`, then:

```bash
python orchestrator.py --auto --pi --env .env.pi
```

systemd (`deploy/jarvis-pi.service`) should start that same command.
