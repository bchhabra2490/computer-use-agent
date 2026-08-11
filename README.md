# Personal Computer Use Agent

Drives your real desktop (mouse, keyboard, screenshots) using OpenAI's `computer`
tool in the Responses API (`gpt-5.6`). Built for macOS; the executor uses
`pyautogui`, which also works on Windows/Linux with minor tweaks (see below).

## Demo

<p align="center">
  <a href="https://youtu.be/j0y-5g9Z_FU">
    <img src="https://img.youtube.com/vi/j0y-5g9Z_FU/maxresdefault.jpg" alt="Watch demo on YouTube" width="800" />
  </a>
  <br />
  <a href="https://youtu.be/j0y-5g9Z_FU"><strong>▶ Watch demo on YouTube</strong></a>
</p>

## Setup

```bash
cd computer-use-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then set OPENAI_API_KEY (and optional WAKE_*)
# .env is loaded automatically by orchestrator.py / agent.py
```

### macOS permissions

System Settings → Privacy & Security → grant your terminal app (Terminal, iTerm,
or your IDE's terminal):
- **Screen Recording** — needed for `pyautogui.screenshot()`
- **Accessibility** — needed for `read_ui_text` (and `pyautogui` keyboard/mouse)
- **Microphone** — needed for voice input (`orchestrator.py`)

You'll need to restart the terminal app after granting these.

## Run

### Daemon (recommended)

```bash
cau start          # background orchestrator (--auto); installs `cau` on PATH
cau stop           # SIGTERM, then SIGKILL if needed
cau status
cau restart
```

`cau start` detaches the voice orchestrator, writes a pid file under `.runtime/`,
and appends logs to `logs/cau.log`. The first start also installs a `cau` shim
to `~/.local/bin` (and Homebrew `bin` if writable) so the command works from any
directory. If `cau` is not found, run `./cau start` from this repo, then add
`~/.local/bin` to your PATH.

Keyboard barge-in (Space / Esc / Enter) needs a focused terminal — use the wake
word to interrupt TTS when running as a daemon.

### Voice orchestrator (foreground)

```bash
python orchestrator.py
python orchestrator.py --auto          # computer agent skips per-step confirms
python agent.py --voice --auto         # same entry via agent.py
./cau start --no-auto                  # daemon without --auto
```

The orchestrator waits for a wake phrase (local openWakeWord by default),
then transcribes your request and lets an LLM choose tools:

| Tool | Role |
|------|------|
| `start_task` | Run the computer-use agent on a concrete UI task |
| `ask_user` | Speak a clarifying question and capture your answer (via orchestrator while a computer task is running) |
| `give_response_to_user` | Speak a reply (set `end_session` to stop) |

Say the wake phrase then “goodbye” / “quit” to stop. Mid-task updates: wake word,
then the instruction. While Jarvis is speaking, say the wake word again to
interrupt TTS and give a new command (`TTS_BARGE_IN=1` by default). Wake barge-in
is armed **before** the ready TTS and stays on for the whole session (paused only
while STT owns the mic — the same capture is still scanned so saying the wake
word again **ends listening** and starts processing, like menu **Send**). You can
also press **Space**, **Esc**, or **Enter** in
the orchestrator terminal (`TTS_KEYBOARD_BARGE=1`) to stop TTS and start listening.
Set `TTS_BARGE_IN=0` if an open mic during speech causes
hiss; `WAKE_BARGE_THRESHOLD` defaults higher than idle wake to reduce echo triggers.
Agent `ask_user` prompts skip the wake word (answer directly).

**Low-latency TTS** (default on): the orchestrator streams Responses API
partial `give_response_to_user` arguments into `low_latency_tts.py`, which
chunks text and overlaps synthesis with playback (afplay on macOS — not
PortAudio). Markers go to `tts_latency.log` (`response_ready`,
`first_audio_play`, and their delta). Tune with `TTS_STREAM`,
`TTS_CHUNK_MIN_CHARS`, `TTS_CHUNK_MAX_CHARS`, `TTS_WARMUP`. Set `TTS_STREAM=0`
for the older synchronous `speak()` path (still used as fallback and for
barge-in-capable lines).

`TTS_PROVIDER=openai` (default) uses `gpt-4o-mini-tts`. `TTS_PROVIDER=sarvam`
streams Bulbul audio (`SARVAM_TTS_MODEL=bulbul:v3`, voice `shubh`; needs
`SARVAM_API_KEY`) through the same clause pipeline.

### Wake word (any phrase)

**Default (offline model):** `Hey Jarvis` or `Jarvis` via openWakeWord
(`WAKE_PHRASE=Hey Jarvis,Jarvis`). Comma-separate multiple spoken forms.

```bash
# Other pretrained models
WAKE_MODEL=alexa WAKE_PHRASE=Alexa python orchestrator.py
WAKE_MODEL=hey_mycroft WAKE_PHRASE="Hey Mycroft" python orchestrator.py

# Your own trained ONNX (see “Custom wake ONNX” below)
WAKE_MODEL=~/models/hey_bob.onnx WAKE_PHRASE="Hey Bob" python orchestrator.py

# Any phrases without training — matches via STT (uses API; no barge-in)
WAKE_MODE=phrase WAKE_PHRASE="Okay Computer,Computer" python orchestrator.py
```

Pretrained aliases: `hey_jarvis`, `alexa`, `hey_mycroft`, `hey_rhasspy`, `timer`,
`weather`. Tune sensitivity with `WAKE_THRESHOLD` / `WAKE_BARGE_THRESHOLD`.
Note: the stock `hey_jarvis` ONNX is trained on the full “Hey Jarvis”; short
“Jarvis” is accepted for STT stripping and phrase-mode. For offline acoustic
detection of short forms, add a custom `.onnx` to `WAKE_MODEL`.

#### Custom wake ONNX

A custom wake word needs a **trained** openWakeWord `.onnx` — setting `WAKE_PHRASE`
alone does not create one.

**Easiest: Google Colab (official)**

1. Open the [openWakeWord custom training Colab](https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb?usp=sharing).
2. Enter your wake phrase (e.g. `hey bob`).
3. Run the notebook — it synthesizes samples and trains a model (often under an hour).
4. Download the resulting `.onnx` file.

**Use it here**

```bash
WAKE_MODE=model \
WAKE_MODEL=/path/to/hey_bob.onnx \
WAKE_PHRASE="Hey Bob" \
python orchestrator.py
```

Or put the file under `models/wake/` and refer to it by name:

```bash
WAKE_MODEL=hey_bob.onnx WAKE_PHRASE="Hey Bob" python orchestrator.py
```

**Other training options**

- [livekit-wakeword](https://github.com/livekit/livekit-wakeword) — local CLI
  (`generate` → `augment` → `train` → `export`) from a YAML config; can export
  openWakeWord-compatible ONNX/TFLite.
- [openwakeword.com](https://openwakeword.com/) — hosted training; download the
  ONNX when finished.
- Community Docker trainers if you want GPU training without Colab.

**Tips**

- Short, distinctive 2–3 word phrases work best (`hey nova`, `okay atlas`).
- Shared feature models (`melspectrogram.onnx`, `embedding_model.onnx`) live in
  `models/wake/` and download automatically.
- For “any phrase” with **no** training, use `WAKE_MODE=phrase` (API-based; no ONNX).
- Upstream docs: [openWakeWord — Training New Models](https://github.com/dscripka/openWakeWord#training-new-models).

### Menu-bar status (macOS)

A small **menu-bar icon** starts with the orchestrator or agent:

- **Hover** — live state (waiting / listening / speaking / agent) + recent log lines
- **Click** — **Send** (while listening: stop recording and transcribe now;
  saying the wake word does the same),
  **Add Memory** (screenshot + description), in-progress agents,
  **Mark Task Done**, recent logs, **Quit Orchestrator**, open latest `logs/`
  run folder, quit the icon

While a computer task is running, **Mark Task Done** (menu bar) or saying
“mark it done” / “no other action is required” stops that job. The agent also
calls `mark_done` itself when the request is finished.

```bash
python status_tray.py          # run the icon alone (optional)
STATUS_TRAY=0 python orchestrator.py   # disable auto-start
```

**Models (cost-aware defaults)**
- Orchestrator: `gpt-5-mini` (`ORCHESTRATOR_MODEL`)
- Computer agent: difficulty router picks `gpt-5.6-luna` / `gpt-5.6-terra` /
  `gpt-5.6` (`AGENT_ROUTE=1`; set `AGENT_MODEL` to force one model)
- N-step coach: every `EVAL_EVERY` turns (default 5) via `EVAL_MODEL=gpt-5-mini`
- STT: `STT_PROVIDER=openai` (default) uses Realtime `gpt-live-transcribe`
  (`STT_MODEL`); ends after `STT_IDLE_SECONDS` with no new words.
  `STT_PROVIDER=sarvam` records until silence then Sarvam Saaras
  (`SARVAM_STT_MODEL=saaras:v3`, needs `SARVAM_API_KEY`)
- Wake models download once into `models/wake/` (`WAKE_MODEL`, `WAKE_PHRASE`,
  `WAKE_MODE=model|phrase`, `WAKE_THRESHOLD`)

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
`open-app`, `web-search`, `hn-comments`, `read-memory`.

### Memories

Durable notes live under `memory/personal/` (who the user is),
`memory/apps/` (per-application usernames, quirks, usual workflows), and
`memory/screens/` (screenshot + LLM description). The orchestrator and
computer agent use `read_memory` / `save_memory` / `save_screen_memory`
(skill `read-memory`). Say “remember that…” to store a fact, or “save the
screen as memory” to snapshot the display. Those folders are gitignored.

Every computer-agent run writes a step log under `logs/<timestamp>_<task>/`.
When a task **completes**, reusable workflows are saved automatically as skills
(`SKILL_AUTO_SAVE=0` to require confirmation again).

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

- `cau` / `cau.py` — daemon CLI (`cau start` / `cau stop`).
- `orchestrator.py` — voice router (wake word → `start_task` / `ask_user` / `give_response_to_user`).
- `status_tray.py` / `app_status.py` — macOS menu-bar status + shared live log ring.
- `wake.py` — wake-word detection (openWakeWord models or any STT phrase).
- `agent.py` — computer-use loop (tools, logging, optional skill creation).
- `terminal.py` — `run_terminal` shell executor (timeout + truncated output).
- `evaluator.py` — difficulty router + periodic coaching for the computer agent.
- `accessibility.py` — macOS AX tree → text for `read_ui_text`.
- `actions.py` — mouse/keyboard executor.
- `skills/` + `skills.py` — task playbooks.
- `memory/` + `memory.py` — personal and per-app notes (`read_memory` / `save_memory`).
- `task_log.py` — per-run logs under `logs/`.
- `stt.py` / `sarvam_stt.py` / `tts.py` / `sarvam_tts.py` — speech in/out
  (OpenAI or Sarvam).
- **Windows/Linux**: `pyautogui` is cross-platform; check display scaling vs the
  Retina handling in `DesktopController`.
