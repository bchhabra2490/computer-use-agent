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

## Ecosystem

Companion projects that pair with this Mac agent:

| Repo | What it does |
|------|----------------|
| [computer-use-mobile-app](https://github.com/bchhabra2490/computer-use-mobile-app) | **Jarvis Remote** — Expo phone app. Send text / hold-to-talk / camera stills to the Mac phone gateway (`PHONE_GATEWAY=1`); live status + last screen/speech over HTTP + SSE. Not a second agent. |
| [computer-use-hardware](https://github.com/bchhabra2490/computer-use-hardware) | ESP32 + MQTT + MCP middleware so the agent can turn lamps/fans on and off and wait for `action_end` confirmation. |

## Setup

```bash
cd computer-use-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then configure voice (see below)
# .env is loaded automatically by orchestrator.py / agent.py
```

### macOS permissions

System Settings → Privacy & Security → grant your terminal app (Terminal, iTerm,
or your IDE's terminal):
- **Screen Recording** — needed for `pyautogui.screenshot()`
- **Accessibility** — needed for `read_ui_text` (and `pyautogui` keyboard/mouse)
- **Microphone** — needed for voice input (`orchestrator.py`)
- **Automation** — needed to list Chrome/Safari tabs (`list_open_apps`); grant
  your terminal app control of those browsers when macOS prompts

You'll need to restart the terminal app after granting these.

### Voice configuration

Voice runs through `.env`. Copy the example file, set at least `OPENAI_API_KEY`,
then tune STT, TTS, and wake word before `cua start` or `python orchestrator.py`.

**1. API keys (required)**

```bash
cp .env.example .env
# Edit .env:
OPENAI_API_KEY=sk-...
```

OpenAI covers the orchestrator LLM, live STT, and TTS with the defaults below.
For Sarvam speech in/out, also set `SARVAM_API_KEY` (from [Sarvam AI](https://sarvam.ai)).

**2. Speech-to-text (`STT_PROVIDER`)**

| Provider | When to use | Key settings |
|----------|-------------|--------------|
| `openai` (default) | Low-latency streaming mic; ends after silence | `STT_MODEL=gpt-live-transcribe`, `STT_IDLE_SECONDS=6` |
| `sarvam` | Indian English / Hindi / codemix; record-then-upload | `SARVAM_API_KEY`, `SARVAM_STT_MODEL=saaras:v3`, optional `SARVAM_STT_LANGUAGE=en-IN` |
| `whisperflow` | Local Whisper (audio stays on the Mac) | `mlx-whisper` on Apple Silicon, or `faster-whisper`; optional `WHISPERFLOW_URL` |

```bash
# OpenAI (default — nothing extra needed)
STT_PROVIDER=openai

# Sarvam example
STT_PROVIDER=sarvam
SARVAM_API_KEY=sk_...
SARVAM_STT_MODEL=saaras:v3

# Local WhisperFlow (record until silence, then on-device Whisper)
STT_PROVIDER=whisperflow
# WHISPERFLOW_MODEL=mlx-community/whisper-large-v3-turbo
# WHISPERFLOW_LANGUAGE=en
# Or point at a local OpenAI-compatible server:
# WHISPERFLOW_URL=http://127.0.0.1:7777/v1
```

Noise / VAD: `STT_NOISE_REDUCTION=far_field`, `STT_HIGHPASS_HZ=140`, `STT_VAD_THRESHOLD=0.55`.
Wrong mic? Set `MIC_DEVICE` to a sounddevice index or name (list devices with
`python -c "import sounddevice; print(sounddevice.query_devices())"`).

**3. Text-to-speech (`TTS_PROVIDER`)**

| Provider | When to use | Key settings |
|----------|-------------|--------------|
| `openai` (default) | `gpt-4o-mini-tts` | optional `TTS_VOICE=onyx` |
| `sarvam` | Bulbul voices (Indian English) | `SARVAM_API_KEY`, `SARVAM_TTS_MODEL=bulbul:v3` |
| `piper` | Local ONNX (CPU, fast) | `pip install piper-tts`; `PIPER_VOICE=en_GB-alan-medium` |
| `kokoro` | Local Kokoro-82M | `pip install mlx-audio` (Mac) or `KOKORO_ONNX_MODEL`; `KOKORO_VOICE=bm_george` |

Wake word picks a speaker: **Hey Jarvis** / **Hey Rekha**
(`TTS_VOICE_JARVIS` / `TTS_VOICE_REKHA`). Sarvam defaults are `shubh` / `priya`;
Piper `en_GB-alan-medium` / `en_US-lessac-medium`; Kokoro `bm_george` / `af_heart`.

```bash
# OpenAI (default)
TTS_PROVIDER=openai

# Sarvam example
TTS_PROVIDER=sarvam
SARVAM_API_KEY=sk_...
SARVAM_TTS_MODEL=bulbul:v3
TTS_VOICE_JARVIS=shubh
TTS_VOICE_REKHA=priya

# Local Piper (first run downloads the ONNX into models/piper/)
TTS_PROVIDER=piper
PIPER_VOICE=en_GB-alan-medium

# Local Kokoro (Apple Silicon)
TTS_PROVIDER=kokoro
KOKORO_VOICE=bm_george
```

Streaming playback (default): `TTS_STREAM=1`, `TTS_CHUNK_MIN_CHARS=20`,
`TTS_WARMUP=1`. Echo or hiss during speech? Set `TTS_BARGE_IN=0`. Skip the
“I heard: …” confirmation with `TTS_CONFIRM_HEARD=0`.

Compare synthesis time across providers (warmup is on by default so model load
is not counted):

```bash
python tts_race.py
python tts_race.py --providers piper,kokoro --rounds 3 --play
python stt_race.py   # same idea for STT
```

**4. Wake word**

Defaults: offline openWakeWord (`WAKE_MODE=model`), `WAKE_MODEL=hey_jarvis`,
`WAKE_PHRASE=Hey Jarvis`. Say **over and out** (or tray **Send**) to finish a
listen. Sensitivity: `WAKE_THRESHOLD=0.5`, `WAKE_BARGE_THRESHOLD=0.6`.

```bash
WAKE_MODE=model
WAKE_MODEL=hey_jarvis,Hey_Rekha.onnx   # custom ONNX in models/wake/
WAKE_PHRASE=Hey Jarvis,Hey Rekha
WAKE_END_PHRASE=over and out
```

Audio cues: `STT_START_CHIME=1` when the mic opens, `STT_END_CHIME=1` when it
closes. Custom wake ONNX training and phrase-mode (`WAKE_MODE=phrase`) are covered
in [Wake word (any phrase)](#wake-word-any-phrase) below.

**5. Speaker ID (optional)**

Recognize your voice on the Mac mic and pass your name into the agent context.

```bash
# In .env
SPEAKER_ID=1

# Enroll (reads five passages — allow mic access in Terminal.app)
cua speaker enroll --name Bharat
cua speaker list
cua speaker test              # speak; prints match + scores
cua speaker test --speak-prompts   # TTS reads prompts for you
```

Re-enroll after changing `SPEAKER_ID_MODEL` or if scores drift. Thresholds:
`SPEAKER_ID_THRESHOLD`, `SPEAKER_ID_SHORT_THRESHOLD`.

**6. Phone companion audio (optional)**

With `PHONE_GATEWAY=1`, pass `"sink": "phone"` on `/v1/command`, `/v1/audio`, or
`/v1/photo` so TTS is synthesized on the Mac but played on the phone via
`GET /v1/speech`. See [Phone gateway](#phone-gateway-optional) below.

**7. Start and smoke-test**

```bash
cua start --auto
# or: python orchestrator.py --auto

# Say "Hey Jarvis" → give a command → "over and out"
# Tray icon should show listening / speaking states
```

If wake never fires: lower `WAKE_THRESHOLD`, confirm mic permission, try
`WAKE_MODE=phrase WAKE_PHRASE="Hey Jarvis"` (uses STT instead of ONNX). If STT
is empty or cuts off early: raise `STT_IDLE_SECONDS` or check `MIC_DEVICE`.

## Run

### Default output folder

User-facing files created, downloaded, exported, or generated by the agent are
saved under `~/Documents/Computer Use Agent/` unless the user explicitly names a
different destination for that request. This includes images (PNG/SVG), PDFs,
spreadsheets, JSON, text reports, and media. Set `AGENT_OUTPUT_DIR` to change the
default globally. Internal logs, runtime state, recipes, and memory screenshots
keep their existing project-managed locations.

### Daemon (recommended)

```bash
cua start          # background orchestrator (--auto); installs `cua` on PATH
cua stop           # SIGTERM, then SIGKILL if needed
cua status
cua restart
cua help           # all commands: observe, speaker, skills, MCP, voice env, …
cua skills condense            # rewrite verbose skills/*/SKILL.md (LLM)
cua skills condense --dry-run  # show what would change; do not write
cua skills merge --dry-run     # propose duplicate merges; do not delete
cua skills merge               # merge duplicates and remove the extras
cua observe start              # separate daemon: log your clicks, draft memories/skills
cua observe list               # pending drafts; numbered m1 / s1 items
cua observe accept <id> m1 s2  # write selected memories/skills; leave the rest
cua observe accept --all       # write every item in every draft
cua observe reject <id> m2     # drop one item from a draft
cua observe reject --all       # discard every proposed draft
cua observe stop
cua face                       # list blobatars (* = current)
cua face droplet               # curated shortcut
cua face jarvis                # any name hashes to a unique blobatar
```

`cua start` detaches the voice orchestrator, writes a pid file under `.runtime/`,
and appends logs to `logs/cua.log`. The first start also installs a `cua` shim
to `~/.local/bin` (and Homebrew `bin` if writable) so the command works from any
directory. If `cua` is not found, run `./cua start` from this repo, then add
`~/.local/bin` to your PATH.

`cua observe` is a **separate** process (not started by `cua start`). It watches
your own mouse activity, logs cheap metadata (app, window, URL), and takes a
screenshot when you switch context or sit idle for 3 seconds (the display
that currently holds the focused window, not only the primary). Those captures
accumulate for **10 minutes** (`OBSERVE_DRAFT_SECONDS=600`) before an extract
is written to `.runtime/observe/proposed/` — nothing is written to `memory/` or
`skills/` until `cua observe accept`. Stopping earlier than 10 minutes does not
create a draft. Grant Accessibility to the terminal that runs the observer so
the listen-only event tap can see clicks; password managers are skipped. The
observer pauses while a computer-use job is driving the pointer.

Keyboard barge-in (Space / Esc / Enter) needs a focused terminal — use the wake
word to interrupt TTS when running as a daemon.

### Voice orchestrator (foreground)

```bash
python orchestrator.py
python orchestrator.py --auto          # computer agent skips per-step confirms
python agent.py --voice --auto         # same entry via agent.py
./cua start --no-auto                  # daemon without --auto
```

The orchestrator waits for a wake phrase (local openWakeWord by default),
then transcribes your request and lets an LLM choose tools:

| Tool | Role |
|------|------|
| `who_am_i` | Read `README.md` and answer who this agent is / what it can do |
| `start_task` | Run the computer-use agent on a concrete UI task |
| `set_timer` | Native countdown / reminder (notification; TTS if they asked to be reminded) |
| `browser_data` | Safely read public HTTP(S) pages as Markdown or links without taking over the visible browser |
| `ask_user` | Speak a clarifying question and capture your answer (via orchestrator while a computer task is running) |
| `give_response_to_user` | Speak a reply (set `end_session` to stop) |
| `mcp_call` | Tools from servers in `mcp.json` (search, GitHub, Linear, …) when configured |

**Recipes** (`recipes/*.json`) are better when the first step is `open` a URL: a matching recipe is chosen from phrases/templates, then `EVAL_MODEL` fills `{{placeholders}}` from the full task text (regex only if the LLM fails or `RECIPE_LLM_FILL=0`). If you also asked to zoom or screenshot, the vision agent continues from that page and is told not to redo the prefix. After a successful run the agent may save a new recipe (`RECIPE_RECORD=0` to disable).

### Fast/slow execution routing

Every request is classified locally before agent execution—there is no extra
LLM routing call—into a **fast** or **slow** path and a specialist lane:

- **Integration/API** — native timers, memory, MCP, and connected services.
- **Terminal** — files, Git, scripts, and other verifiable CLI work.
- **Browser** — `browser_data` for public reading, then recipes/direct URLs and visual interaction.
- **Desktop** — app skills, keyboard, and Accessibility before coordinates.
- **Research** — connected retrieval and `browser_data` first, visual inspection when needed.
- **Visual** — dense or unfamiliar interfaces with screenshot verification.

Fast routes use the inexpensive agent model and easy step budget, attempting
recipes, APIs, CLI, keyboard, or Accessibility first. Failed verification falls
back to normal visual computer use. Slow routes retain difficulty-based model
routing and evaluator coaching. Every route also carries safety-verifier and
completion-verifier guidance. The selected path/lane is written into the task
log and voice latency trace.

### Public webpage data

`browser_data` gives both agent brains a fast, isolated path for static public
webpages. It supports full-page Markdown, phrase-focused extraction, and link
discovery. Requests are limited by timeout, response size, content type, and
public-address validation; redirects are checked too. It never reuses the
user's browser cookies or profile. Thin JavaScript application shells return a
`fallback_required: lightpanda` signal so the browser lane can escalate instead
of treating an empty page as a successful read. The Lightpanda backend runs an
isolated one-shot process, obeys robots.txt, disables telemetry, and enforces a
hard deadline. If it is unavailable or cannot render the page, the result carries
forward its evidence and failure reason to isolated headless Chromium. Chromium
uses a new temporary `--user-data-dir` on every request and deletes it afterward;
it never opens or copies the user's normal Chrome profile. If Chromium also
fails, the result carries `fallback_required: desktop` for the visible browser
lane. Set `LIGHTPANDA_BIN` for a non-PATH executable,
`LIGHTPANDA_WAIT_MS` to tune rendering wait time, and `BROWSER_DATA_TIMEOUT` for
the overall deadline. `CHROMIUM_BIN` selects another Chrome/Chromium executable,
and `CHROMIUM_WAIT_MS` tunes its DOM-capture wait.

### WebMCP page tools

`browser_webmcp` lets both agent brains discover structured tools registered by
public HTTPS pages through `document.modelContext`, then invoke a selected tool
inside an isolated headless Chrome profile. Discovery records the page URL,
origin, schemas, annotations, and tool descriptions. Calls rediscover the tool
and verify its name, origin, and read-only annotation before execution, validate
common JSON Schema input constraints, bound returned data, and discard the
temporary profile afterward.

Use `operation=list` before DOM automation. Tools marked `readOnlyHint: true` can
run on the fast path. Other tools return `confirmation_required` unless
`allow_mutation=true`; set that only when the user explicitly requested or
confirmed the exact side effect. All page-supplied metadata and results remain
untrusted input. This path does not inherit signed-in Chrome cookies; authenticated
WebMCP remains in the visible browser lane. Chrome must support WebMCP and Node.js
22+ must be available for the CDP bridge. Optional settings:
`WEBMCP_NODE_BIN`, `WEBMCP_TIMEOUT`, `WEBMCP_WAIT_MS`, and
`WEBMCP_MAX_RESULT_CHARS`.

Say the wake phrase then “goodbye” / “quit” to stop. Mid-task updates: wake word,
then the instruction. While Jarvis is speaking, say the wake word again to
interrupt TTS and give a new command (`TTS_BARGE_IN=1` by default). Wake barge-in
is armed **before** the ready TTS and stays on for the whole session (paused only
while STT owns the mic — the same capture is scanned for the closer
**over and out** (`WAKE_END_PHRASE`), which **ends listening** like menu
**Send**). You can
also press **Space**, **Esc**, or **Enter** in
the orchestrator terminal (`TTS_KEYBOARD_BARGE=1`) to stop TTS and start listening.
After each listen, Jarvis plays a short start chime when the mic is open
(`STT_START_CHIME`; includes mid-task — not on wake detect). **Over and out**
plays the wake Tink (`WAKE_CHIME_SOUND`), then an end chime when capture stops
(`STT_END_CHIME`), then speaks one short confirmation (`I heard: …`; set
`TTS_CONFIRM_HEARD=0` to disable). Set `TTS_BARGE_IN=0` if an open mic during speech causes
hiss; `WAKE_BARGE_THRESHOLD` defaults higher than idle wake to reduce echo triggers.
Agent `ask_user` prompts skip the wake word (answer directly).

**Low-latency TTS** (default on): the orchestrator streams Responses API
partial `give_response_to_user` arguments into `tts/low_latency.py`, which
chunks text and overlaps synthesis with playback (afplay on macOS — not
PortAudio). Status lines and `start_task` do not wait for playback — the
computer agent starts immediately while speech continues. Markers go to
`tts_latency.log` (`response_ready`, `first_audio_play`, and their delta).
Tune with `TTS_STREAM`, `TTS_CHUNK_MIN_CHARS`, `TTS_CHUNK_MAX_CHARS`,
`TTS_WARMUP`. Set `TTS_STREAM=0`
for the older synchronous `speak()` path (still used as fallback and for
barge-in-capable lines).

`TTS_PROVIDER=openai` (default) uses `gpt-4o-mini-tts`. `TTS_PROVIDER=sarvam`
streams Bulbul audio (`SARVAM_TTS_MODEL=bulbul:v3`; needs `SARVAM_API_KEY`).
`TTS_PROVIDER=piper` runs local ONNX (downloads into `models/piper/`).
`TTS_PROVIDER=kokoro` uses mlx-audio Kokoro on Apple Silicon (`pip install mlx-audio num2words 'spacy==3.8.16' phonemizer` — do not use `misaki[en]` on Python 3.14), or `kokoro-onnx`
when `KOKORO_ONNX_MODEL` is set. Wake word picks the speaker: **Hey Jarvis** /
**Hey Rekha** (`TTS_VOICE_JARVIS` / `TTS_VOICE_REKHA`).

### Wake word (any phrase)

**Default (offline model):** `Hey Jarvis` / `Jarvis` or `Hey Rekha` / `Rekha`
via openWakeWord (`WAKE_MODEL=hey_jarvis,Hey_Rekha.onnx` when that ONNX is in
`models/wake/`). Comma-separate multiple spoken forms. Logs and tray status name
the wake that fired (`Hey Rekha heard — listening`).

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
`weather`. Start listening with `WAKE_MODEL` (default `hey_jarvis`). End a listen
with `WAKE_END_MODEL` (default `over_and_out.onnx` when that file is in
`models/wake/`). Say **over and out** — the closer is also matched in the
transcript (`WAKE_END_PHRASE`). Tune sensitivity with `WAKE_THRESHOLD` /
`WAKE_BARGE_THRESHOLD`.
Note: the stock `hey_jarvis` ONNX is trained on the full “Hey Jarvis”; short
“Jarvis” is accepted for STT stripping and phrase-mode. For offline acoustic
detection of short forms, add a custom `.onnx` to `WAKE_MODEL`.

#### Custom wake ONNX

A custom wake word needs a **trained** openWakeWord `.onnx` — setting `WAKE_PHRASE`
alone does not create one.

**Recommended: [wake-word-classifier](https://github.com/bchhabra2490/wake-word-classifier)**

Local trainer for a custom phrase (US, UK, and Indian English TTS). Use Python
3.12.8, then:

```bash
git clone https://github.com/bchhabra2490/wake-word-classifier
cd wake-word-classifier
~/.pyenv/versions/3.12.8/bin/python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
.venv/bin/python train_wake_word.py --phrase "hey rekha" --n-samples 10000 --n-samples-val 500
```

The ONNX lands in `my_custom_model/` (spaces become underscores, e.g.
`hey_rekha.onnx`). Copy it into this repo’s `models/wake/`, then set
`WAKE_MODEL` (start listening) or `WAKE_END_MODEL` (stop listening / send).
`--n-samples 1000` is enough to try the pipeline; **10000** is the working
dataset size. Mic testing needs Terminal.app (not Cursor) for microphone
permission — see that repo’s README.

**Alternative: Google Colab (official openWakeWord)**

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
- **On-screen overlay** — the same logs on a transparent, click-through panel
  (prefers a second display). Hides for each screenshot, then comes back.
  Toggle **Log Overlay** in the menu-bar icon.
- **Face overlay** — a click-through blobatar at the top center of the main
  display. Mood follows session state (wink when awake / sleep when Sleep mode /
  listen / unsure / speak / think). Hidden
  from computer-use screenshots. Toggle **Face Overlay** in the menu-bar icon,
  or set `FACE_OVERLAY=0`.
- **Sleep** — ignore the wake word (menu **Sleep** or **⌘⌃S** / `cua sleep on`).
  Face uses the sleep expression; turn Sleep off to wink and listen again.
- **Listen now** — press **⌘⌃J** to start normal Jarvis command listening
  immediately, without saying the wake word.
- **Chat** — Electron desktop front-end for the **orchestrator** (same queue as
  the wake word and phone `/v1/command`). Sidebar of saved chats, camera attach,
  and spoken replies in bubbles. History is SQLite under `.runtime/chat/`. Needs
  `python orchestrator.py --auto` and once: `cd chat_app && npm install`. Toggle
  **Chat** in the menu bar, **⌘⌃C**, or `cua chat on`.
- **Click** — **Send** (while listening: stop recording and transcribe now;
  saying **over and out** does the same),
  **Add Memory** (screenshot + description), **Log Overlay**, **Face Overlay**,
  **Chat**,
  in-progress agents, **Mark Task Done**, recent logs, **Quit Orchestrator**,
  open latest `logs/` run folder, quit the icon

While a computer task is running, **Mark Task Done** (menu bar) or saying
“mark it done” / “no other action is required” stops that job. The agent also
calls `mark_done` itself when the request is finished.

```bash
python status_tray.py          # run the icon alone (optional)
STATUS_TRAY=0 python orchestrator.py   # disable auto-start
```

**Blobatars.** Switch without restarting. `pebble`, `droplet`, `cloud`, and
`sun` are curated shortcuts; **any other name** hashes to a unique creature
(same seed always looks the same, in the spirit of [blobatar.dev](https://blobatar.dev/)):

| Name | Look |
|------|------|
| `pebble` | teal round pebble (default) |
| `droplet` | coral teardrop |
| `cloud` | lavender cloud |
| `sun` | amber sun with petals |
| *anything else* | hashed silhouette + hue from the name |

```bash
cua face              # list (* = current)
cua face pebble
cua face droplet
cua face jarvis
cua face rekha
# alias: cua blobatar sun
```

Pin one at startup with `FACE_OVERLAY_PRESET=jarvis` in `.env`. Leave
`FACE_OVERLAY_HUE` unset so each name keeps its own color; that env value
overrides hue for every blobatar.

### Phone gateway (optional)

A small HTTP + SSE server on the Mac so a companion app can send text commands
and read live status. **Off by default** (`PHONE_GATEWAY=0`). It does not drive
the mouse; it queues text the same way speech does.

```bash
PHONE_GATEWAY=1 python orchestrator.py --auto
# prints LAN URLs and a 5-character Bearer token (.runtime/phone.token)
```

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/health` | liveness (no auth) |
| GET | `/v1/status` | state, logs (incl. LLM replies), last spoken / last LLM |
| GET | `/v1/events` | SSE stream of the same payload |
| GET | `/v1/screen` | last agent screenshot (JPEG) |
| GET | `/v1/speech` | last Mac-synthesized reply WAV when `reply_sink` is `phone` |
| POST | `/v1/command` | `{ "text": "…", "sink": "phone" }` — optional `sink` (`phone` \| `mac`) |
| POST | `/v1/audio` | clip → Mac STT → command queue; optional `sink` in JSON/multipart |
| POST | `/v1/photo` | camera still → Jarvis looks at it; optional `sink` in JSON/multipart |
| POST | `/v1/control` | `{ "action": "send" \| "mark_done" \| "quit" \| "sink", "sink": "phone" }` |

Send `Authorization: Bearer <token>` (or `?token=` on SSE / `/v1/screen` / `/v1/speech`). Same Wi‑Fi or an
Android hotspot is enough. iPhone Personal Hotspot often blocks LAN to the Mac —
use Tailscale or USB tethering. Tailscale is only required off the LAN.

**Tailscale (phone on cellular).** Install Tailscale on Mac and phone (same tailnet). With
`PHONE_GATEWAY=1`, startup prints LAN URLs plus `http://100.x.x.x:8742` and a MagicDNS hostname
when the `tailscale` CLI is installed. Point the companion at that URL; token is in
`.runtime/phone.token` (max 5 chars). Example:

```bash
tailscale ip -4   # on Mac, if URLs were not printed
curl -s -H "Authorization: Bearer $TOKEN" http://100.x.x.x:8742/v1/health
```

`/v1/status` includes `screen_at` when the computer-use agent has captured a
frame. Refetch `/v1/screen` when that timestamp changes — there is no extra
screenshot; it is the same PNG the model just saw, saved as a phone-sized JPEG.

TTS is always synthesized on the Mac. Pass `"sink": "phone"` on `/v1/command`,
`/v1/audio`, or `/v1/photo` to route **that turn’s** replies to the phone:
playback skips Mac speakers, `speech_at` updates, and you refetch `/v1/speech`
(WAV) to play locally. The next command without `sink: "phone"` (wake word, chat,
or API) switches back to Mac `afplay`. `POST /v1/control` with `"action": "sink"`
sets the speaker until the next command.

LLM replies are in `logs` as `[llm]`, `[agent]`, `[tts]`, or `[mark_done]`
lines (up to ~2000 characters). `last_llm` is the newest of those; `last_spoken`
is the last line actually sent to TTS.

`POST /v1/audio` is hold-to-talk from the phone. Send a WAV/M4A body
(`Content-Type: audio/m4a`), multipart `audio` file, or JSON
`{ "audio": "<base64>", "mime": "audio/m4a" }`. Optional `text` skips STT and
queues that string (edited caption). The Mac transcribes with the same
`STT_PROVIDER` as the desktop mic, then enqueues the transcript like `/v1/command`.
Cap is ~30s / `PHONE_AUDIO_MAX_BYTES` (default 2.5MB). Response:
`{ "ok": true, "queued": true, "text": "…", "source": "audio" }`.

`POST /v1/photo` is a camera still from the phone. Send a JPEG/PNG/HEIC body
(`Content-Type: image/jpeg`), multipart `photo` file, or JSON
`{ "photo": "<base64>", "mime": "image/jpeg" }`. Optional `text` / `caption`
is the question ("what does this label say?"). Optional mic clip is transcribed
on the Mac and used as that caption: multipart field `audio`, or JSON
`{ "photo": "<base64>", "audio": "<base64>", "audio_mime": "audio/m4a" }`.
Explicit `text` wins over audio. With neither, Jarvis explains the photo and
waits for follow-ups. The Mac resizes the still, attaches it to the
orchestrator vision turn, and keeps it for later questions in the same
session. Cap `PHONE_PHOTO_MAX_BYTES` (default 6MB) plus `PHONE_AUDIO_MAX_BYTES`
for the clip. Response:
`{ "ok": true, "queued": true, "text": "…", "source": "photo", "caption_source": "audio", "width": 1280, "height": 960 }`.
Status includes `photo_at` when a still is stored.

```bash
TOKEN=$(cat .runtime/phone.token)
curl -s http://127.0.0.1:8742/v1/health
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8742/v1/status
curl -s -H "Authorization: Bearer $TOKEN" -o /tmp/jarvis.jpg \
  http://127.0.0.1:8742/v1/screen
curl -s -H "Authorization: Bearer $TOKEN" -o /tmp/jarvis.wav \
  http://127.0.0.1:8742/v1/speech
curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"text":"open notes"}' http://127.0.0.1:8742/v1/command
curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: audio/m4a" \
  --data-binary @clip.m4a http://127.0.0.1:8742/v1/audio
curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: image/jpeg" \
  --data-binary @shot.jpg http://127.0.0.1:8742/v1/photo
python phone_gateway.py          # run the server alone (optional)
```

**Models (cost-aware defaults)**
- Orchestrator: `gpt-5-mini` (`ORCHESTRATOR_MODEL`). Set `ORCHESTRATOR_MODEL=deepseek-v4-pro`
  (and `DEEPSEEK_API_KEY`) to reason with DeepSeek; STT/TTS stay on OpenAI/Sarvam/etc.
  Screenshots/photos use `ORCHESTRATOR_VISION_MODEL` / `DEEPSEEK_VISION_MODEL` when needed.
- Computer agent: difficulty router picks `gpt-5.6-luna` / `gpt-5.6-terra` /
  `gpt-5.6` and max-steps **25 / 100 / 200** (`AGENT_ROUTE=1`; set `AGENT_MODEL` to force one model).
  DeepSeek agents (`AGENT_MODEL=deepseek-v4-pro`) use the `desktop_actions` function tool
  instead of OpenAI’s built-in `computer` tool.
- N-step coach: every `EVAL_EVERY` turns (default 5) via `EVAL_MODEL=gpt-5-mini`
- STT: `STT_PROVIDER=openai` (default) uses Realtime `gpt-live-transcribe`
  (`STT_MODEL`); ends after `STT_IDLE_SECONDS` with no new words.
  `STT_PROVIDER=sarvam` records until silence then Sarvam Saaras
  (`SARVAM_STT_MODEL=saaras:v3`, needs `SARVAM_API_KEY`).
  `STT_PROVIDER=whisperflow` records until silence then local Whisper
  (`mlx-whisper` / `faster-whisper`, or `WHISPERFLOW_URL`).
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
`open-app`, `web-search`, `hn-comments`, `read-memory`. Auto-saved skills from
completed runs can get long; rewrite them on demand (does not run in the
voice loop):

```bash
cua skills condense                 # skills over ~1800 chars (description + body)
cua skills condense --name open-app
cua skills condense --force         # every skill
cua skills condense --dry-run       # model only; no writes
cua skills merge --dry-run          # propose duplicate groups; nothing deleted
cua skills merge                    # write the survivor, delete the duplicates
```

Set `SKILL_CONDENSE_MODEL` / `SKILL_CONDENSE_MIN_CHARS` in `.env` if needed.
Merge only folds skills that are the same workflow (same app and outcome).
Related-but-different playbooks (Amazon search vs checkout, HN comments vs
submit) stay separate. Companion files in a dropped folder are moved into the
kept skill.

### Memories

Durable notes live under `memory/personal/profile.md` (who the user is — one
file, re-condensed after every personal write),
`memory/apps/` (per-application usernames, quirks, usual workflows), and
`memory/screens/` (screenshot + LLM description). The orchestrator and
computer agent use `read_memory` / `save_memory` / `save_screen_memory`
(skill `read-memory`). After every voice turn and computer-use run, the
full user request plus each LLM step (replies, tool calls, results) is
reviewed and durable facts are appended automatically — GitHub repos,
songs played, usernames, preferences, and similar. Extraction runs in a
background thread so it does not block listening or the computer agent.
A second background pass then condenses those files (drops repeated
bullets, keeps the latest preference) so later prompts stay short.
With more than one display attached, each voice turn and computer-use
run snapshots which apps/windows are on which monitor and injects that
into the model prompt (live context under `.runtime/desktop.txt`, not
durable `memory/`). The same snapshot includes **running apps** and
**open browser tabs** (Chrome / Chromium / Brave / Edge / Safari titles and
URLs via AppleScript; browsers are not launched). Call `list_open_apps` for
a fresh list. Set `DESKTOP_LIST_TABS=0` to skip tab enumeration. Screenshots
and click coordinates stay on the primary display.
Say “remember that…” to store a fact yourself, or “save the screen as
memory” to snapshot the display. Set `MEMORY_EXTRACT=0` or
`MEMORY_CONDENSE=0` to disable. Those folders are gitignored.

### MCP servers

Connect apps by **logging in** in the browser (OAuth). No API key required for
Linear / GitHub / Notion:

```bash
cua mcp login linear     # opens Linear OAuth
cua mcp login github     # GitHub CLI browser login (`gh auth login`)
cua mcp login notion
cua mcp status
```

GitHub’s hosted MCP server does **not** support automatic OAuth registration.
`cua mcp login github` uses the GitHub CLI instead (install with `brew install gh`).
Already signed in to `gh`? The command reuses that session. Or pass a PAT:
`cua mcp login github --token ghp_…`.

Restart the orchestrator after login. Tokens live in `.runtime/mcp-auth/`
(not git). `cua mcp logout linear` forgets them.

Custom remote MCP:

```bash
cua mcp login acme --url https://mcp.example.com/mcp
```

API keys still work if you put `Authorization: Bearer …` in `mcp.json` instead
of `"auth": "oauth"`. On startup CUA lists each server’s tools and exposes
**`mcp_call`**. Voice questions that an MCP tool can answer skip `start_task`.
Writes are allowed unless `MCP_READ_ONLY=1`. `mcp.json` is gitignored.

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

- `cua` / `cua.py` — daemon CLI (`cua start` / `cua stop` / `cua chat` / `cua face` / `cua observe` / `cua skills condense` / `cua skills merge`).
- `observe.py` — passive click/scroll observer; drafts under `.runtime/observe/proposed/`.
- `orchestrator.py` — voice router (wake word → `start_task` / `ask_user` / `give_response_to_user`).
- `status_tray.py` / `app_status.py` — macOS menu-bar status + shared live log ring.
- `face_overlay.py` — top-center blobatar (`cua face NAME`, or curated pebble/droplet/cloud/sun).
- `chat_app/` / `chat_bridge.py` / `chat_store.py` — Electron chat UI + localhost
  bridge for the orchestrator (`cua chat on`; SQLite history + screenshots).
- `chat_overlay.py` — tray/CLI launcher for the Electron chat app.
- `wake.py` — wake-word detection (openWakeWord models or any STT phrase).
- `agent.py` — computer-use loop (tools, logging, optional skill creation).
- `terminal.py` — `run_terminal` shell executor (timeout + truncated output).
- `evaluator.py` — difficulty router + periodic coaching for the computer agent.
- `accessibility.py` — macOS AX tree → text for `read_ui_text`.
- `displays.py` — live windows, running apps, and browser tabs for prompt context
  (`list_open_apps`).
- `actions.py` — mouse/keyboard executor.
- `skills/` + `skills.py` — task playbooks (`cua skills condense` / `cua skills merge`).
- `recipes/` + `recipes.py` — parameterized `open` URL/app prefixes with optional computer-use handoff.
- `memory/` + `memory.py` — personal and per-app notes (`read_memory` / `save_memory`); auto-extract then condense after each run.
- `whoami.py` — `who_am_i` reads `README.md` when the user asks about this agent.
- `mcp.json` + `mcp_client.py` + `mcp_auth.py` — MCP servers (`cua mcp login linear`).
- `task_log.py` — per-run logs under `logs/`.
- `stt/` — speech-in (`stt.openai`, `stt.sarvam`, `stt.whisperflow`; `STT_PROVIDER`).
- `tts/` — speech-out (`tts.openai`, `tts.sarvam`, `tts.piper`, `tts.kokoro`, `tts.low_latency`; `TTS_PROVIDER`).
- **Windows/Linux**: `pyautogui` is cross-platform; check display scaling vs the
  Retina handling in `DesktopController`.

## License

This project is open source under the [MIT License](LICENSE).
