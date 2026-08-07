# Personal Computer Use Agent

Drives your real desktop (mouse, keyboard, screenshots) using OpenAI's `computer`
tool in the Responses API (`gpt-5.6`). Built for macOS; the executor uses
`pyautogui`, which also works on Windows/Linux with minor tweaks (see below).

## Setup

```bash
cd computer-use-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
```

### macOS permissions

System Settings → Privacy & Security → grant your terminal app (Terminal, iTerm,
or your IDE's terminal):
- **Screen Recording** — needed for `pyautogui.screenshot()`
- **Accessibility** — needed for `read_ui_text` (and `pyautogui` keyboard/mouse)
- **Microphone** — needed for voice input (`orchestrator.py`)

You'll need to restart the terminal app after granting these.

## Run

### Voice orchestrator (recommended)

```bash
python orchestrator.py
python orchestrator.py --auto          # computer agent skips per-step confirms
python agent.py --voice --auto         # same entry via agent.py
```

The orchestrator waits for the wake phrase **Hey Jarvis** (local openWakeWord),
then transcribes your request and lets an LLM choose tools:

| Tool | Role |
|------|------|
| `start_task` | Run the computer-use agent on a concrete UI task |
| `ask_user` | Speak a clarifying question and capture your answer (via orchestrator while a computer task is running) |
| `give_response_to_user` | Speak a reply (set `end_session` to stop) |

Say “Hey Jarvis” then “goodbye” / “quit” to stop. Mid-task updates: wake word,
then the instruction. While Jarvis is speaking, say “Hey Jarvis” again to
interrupt TTS and give a new command (`TTS_BARGE_IN=0` to disable;
`WAKE_BARGE_THRESHOLD` defaults higher than idle wake to reduce echo triggers).
Agent `ask_user` prompts skip the wake word (answer directly).

**Models (cost-aware defaults)**
- Orchestrator: `gpt-5-mini` (`ORCHESTRATOR_MODEL`)
- Computer agent: difficulty router picks `gpt-5.6-luna` / `gpt-5.6-terra` /
  `gpt-5.6` (`AGENT_ROUTE=1`; set `AGENT_MODEL` to force one model)
- N-step coach: every `EVAL_EVERY` turns (default 5) via `EVAL_MODEL=gpt-5-mini`
- STT: OpenAI Realtime `gpt-live-transcribe` (`STT_MODEL`); sends after
  `STT_IDLE_SECONDS` (default 3s) with no new transcribed words
- Wake models download once into `models/wake/` (`WAKE_THRESHOLD` tweaks sensitivity)

### Direct computer agent (typed task)

```bash
# Confirm each mouse/keyboard batch and each shell command
python agent.py "Open Notes and write today's date at the top"

# Skip confirms (use carefully)
python agent.py "Open Safari and go to https://news.ycombinator.com" --auto
python agent.py "..." --max-steps 25
```

**Example tasks**

```bash
# Desktop / UI
python agent.py --auto "Open Notes and write today's date at the top"
python agent.py --auto "Open System Settings and find the Displays pane"
python agent.py --auto "Open Safari, go to youtube.com, search for AC/DC Thunderstruck, and play the official video"

# Shell via run_terminal (prefer this over driving Terminal.app)
python agent.py --auto "Using the terminal, show disk free space and the top 5 largest folders in my home directory"
python agent.py --auto "Check git status in ~/Desktop/projects/computer-use-agent and summarize uncommitted changes"
python agent.py --auto "Create ~/Desktop/jarvis-demo.txt with the current date and list that folder"

# Mix UI + terminal
python agent.py --auto "Clone https://github.com/openai/openai-python into ~/Desktop if missing, then open that folder in Finder"
```

**Voice examples** (after `python orchestrator.py --auto`)

Say **Hey Jarvis**, then something like:
- “Open Notes and jot today’s date”
- “What’s my free disk space?” (agent can use `run_terminal`)
- “Open YouTube and play something by AC/DC”
- Mid-task: “Hey Jarvis, stop — open Chrome instead”
- While it’s speaking: “Hey Jarvis” again to barge in, then your new instruction
- “Goodbye” / “quit” to end the session

### Skills

Reusable playbooks live under `skills/<name>/SKILL.md` (YAML frontmatter with
`name` + `description`, then markdown steps). The computer agent sees the
catalog and loads full instructions with `read_skill`. Starter skills:
`open-app`, `web-search`, `hn-comments`.

Every computer-agent run writes a step log under `logs/<timestamp>_<task>/`.
When a task **completes**, it may propose a new skill (`Y/n` to save).

## Safety

- **Fail-safe**: slam your mouse into any screen corner to abort instantly
  (pyautogui's built-in fail-safe, left on).
- **Ctrl+C** between turns also stops it.
- Don't run `--auto` unattended on anything touching payments, deleting files,
  sending messages, or credentials — keep the confirmation gate on for those.
- Without `--auto`, computer actions and `run_terminal` commands ask for
  confirmation before executing.
- The model can run shell commands via `run_terminal` (stdout/stderr returned).
  Treat that like giving it a terminal on your machine.

## Extending it

- `orchestrator.py` — voice router (wake word → `start_task` / `ask_user` / `give_response_to_user`).
- `wake.py` — local “Hey Jarvis” wake-word detection (openWakeWord).
- `agent.py` — computer-use loop (tools, logging, optional skill creation).
- `terminal.py` — `run_terminal` shell executor (timeout + truncated output).
- `evaluator.py` — difficulty router + periodic coaching for the computer agent.
- `accessibility.py` — macOS AX tree → text for `read_ui_text`.
- `actions.py` — mouse/keyboard executor.
- `skills/` + `skills.py` — task playbooks.
- `task_log.py` — per-run logs under `logs/`.
- `stt.py` / `tts.py` — speech in/out.
- **Windows/Linux**: `pyautogui` is cross-platform; check display scaling vs the
  Retina handling in `DesktopController`.
