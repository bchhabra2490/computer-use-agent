# Plan

Eight follow-on tracks. The voice loop (wake → STT → orchestrator → computer agent) stays as it is; these sit beside it or behind the same interfaces.

## 1. Passive activity tracker (skills + memories)

A **separate process**, not the computer-use agent. It watches what the user is already doing and writes durable notes. It must not click, type, or steal focus.

**Why separate.** The CU agent is task-driven and takes the desktop. A tracker that shares that process would fight the user for the mouse and mix “do this” with “notice that.” Run it as its own daemon (e.g. `cua track`), with its own pid/log, pauseable from the tray.

**Observe, don’t act.**

- Periodic screenshots and/or Accessibility UI snapshots (frontmost app, window title, URL if Chrome).
- Optional: app-switch events, not a keylogger. No clipboard scraping unless the user opts in.
- Rate-limit (e.g. every N seconds, only when the foreground app changes) so it stays cheap and private.

**Write into the existing stores.**

- Memories: `memory/apps/`, `memory/personal/`, `memory/screens/` — same markdown shape the agent already reads (`read_memory` / `save_memory`).
- Skills: propose or update `skills/*/SKILL.md` when a repeated UI flow is obvious (same app, same steps). Prefer drafts the user can accept (tray **Add Memory** / a “proposed skill” folder) over silent overwrites.

**Safety.** Tracker is read-only on the desktop. It never calls `DesktopController`. Secrets stay out of files unless the user explicitly saves them. Easy kill switch (`cua track stop` / tray).

## 2. Adapters for local STT, TTS, and LLM

Cloud providers are already switched by env (`STT_PROVIDER`, `TTS_PROVIDER`, `ORCHESTRATOR_MODEL`). Add a **local** implementation behind the same functions so the orchestrator and agent do not care where inference runs.

**STT** (`stt.py` / `listen_for_utterance`). Same contract: mic PCM in, transcript out. Local options: Whisper.cpp / faster-whisper, or a small streaming model. Keep Sarvam/OpenAI as other providers. Idle / Send / over-and-out stay in the capture loop, not in the model.

**TTS** (`tts.py` / `synthesize` → WAV). Same contract: text in, WAV out. Local options: Piper, Kokoro, or MLX speech. Keep wake-based speaker mapping (Jarvis → Shubh, Rekha → Priya) as a *voice name* the adapter resolves (cloud speaker vs local voice file).

**LLM** (orchestrator + computer-use + memory captions).

- Orchestrator: OpenAI-compatible HTTP (`localhost:11434`, LM Studio, vLLM, MLX) so tool calling stays the same.
- Computer-use: harder — today’s path is OpenAI’s `computer` tool. Local CU needs either a CU-capable cloud model still, or a thinner loop (screenshot → local VLM → `DesktopController` actions). Ship the adapter interface first; local CU can lag STT/TTS/orchestrator.

**Config sketch.** `STT_PROVIDER=local`, `TTS_PROVIDER=local`, `LLM_PROVIDER=local` plus endpoint/model env vars. One adapter module per modality (`local_stt.py`, `local_tts.py`, `local_llm.py`) so cloud code paths stay untouched.

## 3. Virtual layer (don’t take over mouse and keyboard)

Today `DesktopController` in `actions.py` drives the **real** display via `pyautogui`. That seizes the user’s pointer and keys. Computer-use should run against an **isolated desktop** the user can watch, not the one they are typing on.

**Do this first: swap the executor, don’t rewrite the agent.** `agent.py` already talks to `DesktopController` for screenshot / click / type / scroll. Add `CU_MODE=local|virtual`:

- `local` — current pyautogui on the host (unchanged).
- `virtual` — same method names, different backend: a guest display (screenshot + inject input there only).

**Preferred isolation: Linux VM + VNC (or similar).**

- Guest has a full desktop (browser, files) the agent can operate.
- Host sees it in a window; host mouse/keyboard stay with the user.
- Screenshots and clicks are in guest coordinates, so Retina remapping in `DesktopController` becomes a backend detail.
- Skip “cloud sandbox that isn’t a GUI desktop.” A Vercel-style microVM is the wrong shape for this; we need a persistent GUI.

**Later.** Multiple agents → multiple guests, not multiple grabs of one Mac screen. The passive tracker (section 1) can still watch the *host* if the user wants host memories, while CU stays in the VM.

**Done when.** `CU_MODE=virtual python orchestrator.py --auto` completes a Chrome task inside the guest while the user can keep using the Mac trackpad without the pointer jumping.

## 4. Integration with memory apps (Minimi and similar)

Don’t rebuild ambient recall from scratch. Apps like [Minimi](https://halotool.com/tool/minimi) already watch the Mac (tabs, docs, calls, Slack), keep an **on-device** vector store, and expose it to agents over **MCP**. Wire CUA as a consumer of that memory, and optionally as a writer.

**Read path (first).** Treat Minimi as one MCP server on the general client in §7. The orchestrator queries it before `start_task` / `give_response_to_user` — “what did I decide about X”, “which tab / thread”. Keep `memory/` markdown as the durable, user-editable store; Minimi is the high-volume activity index. Swapping Minimi for another local memory app is a config change (`mcp.json` / env), not a rewrite.

**Write path (optional).** The passive tracker (section 1) and explicit “save the screen / add memory” actions can also **push** summaries into Minimi (or equivalent) so CU tasks and spoken notes show up in the same recall surface the user already uses with Claude.

**Boundaries.**

- Opt-in: `MEMORY_APP=minimi|none` (plus MCP URL / connector). Off by default until the user installs and connects the app.
- No secrets in either store unless the user saved them. Don’t duplicate raw screenshots into a third-party index if Minimi already captured the screen.
- Tracker vs Minimi: if Minimi is running, the tracker should skip overlapping capture (tabs / frontmost app) and only write CU-specific notes (skills, task outcomes, spoken preferences).

**Done when.** With Minimi connected, “Hey Jarvis, what was I reading about checkout?” can answer from Minimi context without a desktop takeover, and a finished CU task can be recalled later from the same memory layer.

## 5. Dense apps (EasyEDA, CAD, schematic / PCB)

Screenshot-and-click is a poor fit for canvas tools. EasyEDA, KiCad, Fusion, and similar apps draw the work surface in WebGL / custom widgets, so `read_ui_text` often returns almost nothing (already noted in `accessibility.py`). The evaluator already treats this class as **hard**. Goal: CUA can open, navigate, and do routine work in these apps without guessing at pixels.

**Don’t drive the canvas by click coordinates.** Prefer, in order:

1. **Official API / scripting** — KiCad Python, Fusion 360 API, EasyEDA export/CLI or plugin if it exists. Add a thin `run_app_script` (or reuse `run_terminal`) that runs a known-safe script inside the app instead of dragging traces with the mouse.
2. **Keyboard and named UI** — menus, search palettes (Cmd+K / type-to-filter), documented hotkeys. Skills should list those, not “click the left toolbar ~40px down.”
3. **AX where it works** — ribbon, dialogs, project tree. Fall back to screenshots only for confirming the canvas, not for choosing tools.
4. **Last resort: labeled UI maps** — a per-app overlay or saved atlas (`memory/apps/easyeda.md` + reference screenshots) of tool names → regions, regenerated when the window size changes. Still better than the model inventing coordinates every turn.

**Per-app packs (start with EasyEDA).** Today `skills/use-easyeda` only covers open + new project + save. Expand into a small pack, not one giant skill:

- Window map: project tree, canvas, properties, library.
- Navigation: pan/zoom, select vs wire vs place, how to get back to schematic vs PCB.
- Library / search: add a part by name without hunting icons.
- Safe edits: rename, save, export Gerber/PDF — operations that don’t require freehand drawing.
- “Don’t”: redraw nets, move footprints, or route unless an API/script does it.

Same pattern later for KiCad / other CAD: one pack per app, same structure, loaded via `read_skill` when the task names that software.

**How the agent chooses.** Orchestrator / agent: if the task mentions EasyEDA, KiCad, CAD, schematic, PCB → load the pack first, set a **keyboard-first** policy, and skip long screenshot loops for tool picking. If AX is empty, say so and use the pack’s hotkeys rather than clicking the canvas.

**Virtual layer.** These apps are a good fit for `CU_MODE=virtual` (section 3): a dedicated guest with EasyEDA already logged in, so experiments don’t fight the user’s Mac session.

**Done when.** “Hey Rekha, open EasyEDA, new project named `usb-hub`, add a USB-C connector from the library, save” completes via menus/search/hotkeys (or a script), without the pointer hunting the canvas. Trace routing / 3D modeling stay out of scope until an API path exists.

## 6. Ideas from other computer-use agents (and how we stay faster)

Surveyed: [e2b-dev/open-computer-use](https://github.com/e2b-dev/open-computer-use), [showlab/computer_use_ootb](https://github.com/showlab/computer_use_ootb), [simular-ai/Agent-S](https://github.com/simular-ai/Agent-S), [ranpox/awesome-computer-use](https://github.com/ranpox/awesome-computer-use). They optimize for **OSWorld / demo accuracy**. We optimize for **voice-to-first-action on a personal Mac**. Copy the interfaces; do not copy the extra model hops.

### What they implement

**E2B Open Computer Use** — cloud **Linux desktop sandbox** (E2B) + VNC so the agent never touches the user’s machine. Split stack: **vision** (what’s on screen) + **action** (what to do) + **grounding** (OS-Atlas / ShowUI: where to click) + shell. Swap Groq / Fireworks / OpenRouter in `config.py`. User can pause and re-prompt. Matches our §3 virtual layer, but theirs is a **remote** microVM with extra RTT.

**Computer Use OOTB** — **no Docker**; pyautogui on the **host** Windows/macOS (same class as us). Gradio UI, even phone-as-remote. Two modes: unified **Claude Computer Use**, or **planner + actor** (GPT-4o / Qwen planner + ShowUI / UI-TARS actor). They shrink screenshot tokens at any resolution and offer 4-bit ShowUI + `max_pixels` for speed. Local ShowUI on an M2 is still **~15–20s/step** — too slow for spoken CU.

**Agent S (S3)** — research SOTA on OSWorld (~72.6% with Behavior Best-of-N). **Planner vs grounding split**: GPT-class manager + **UI-TARS** to turn “click Save” into coordinates (`OSWorldACI`). Hierarchical manager/worker, **narrative + episodic memory**, optional **reflection**, optional `call_code_agent` (Python/Bash instead of GUI). Best-of-N = several full rollouts then pick a winner — accuracy, not latency. Caps screenshot history (`max_trajectory_length=8`).

**Awesome Computer Use** — map of the field, not an agent. Useful clusters: **grounding VLMs** (OmniParser, OS-Atlas, SeeClick, UI-TARS), **workflow/experience memory** (Agent Workflow Memory, OS-Copilot — same job as our `skills/` + `memory/`), **AX-first desktop** ([Terminator](https://github.com/mediar-ai/terminator), [Fazm](https://github.com/m13v/fazm)), **local VM CU** ([trycua/cua](https://github.com/trycua/cua), ClawBox). Safety papers (popup injection) matter if we ever browse untrusted pages in a guest.

### What we should steal

| Idea | From | Why it helps us |
|------|------|-----------------|
| Isolated GUI guest, host pointer free | E2B, trycua | §3 — prefer **local VM + VNC**, not E2B cloud RTT |
| Screenshot downscale / token cap | OOTB | Every CU step ships an image; smaller image = faster `computer` calls |
| Cap image turns in the trajectory | Agent S | Don’t resend 20 full-res screenshots |
| Code/script instead of GUI when possible | Agent S `call_code_agent`, E2B shell | Files, git, EasyEDA/KiCad APIs — 0 screenshots |
| Experience memory so we don’t re-explore | Agent S narrative/episodic, AWM | Skills stay for the model; **action traces** replay easy tasks with no vision |
| AX / named UI before pixels | Fazm, Terminator, our `read_ui_text` | Grounding VLM is a whole extra inference |
| Fast cheap model for routing only | OOTB planner+actor, our evaluator | Keep one CU model; use a small model to pick skill / skip CU |

### What we should not copy (latency)

- **Three models per click** (vision + action + grounding). That’s 2–3 serial RTTs. Stay on **one** computer-use model; use AX/hotkeys/skills for coordinates.
- **Local ShowUI/UI-TARS on the Mac every step.** 15–20s/step kills voice. If we add a grounding model, it must be **optional** and only when AX is empty (CAD canvas).
- **Behavior Best-of-N / reflection every turn.** Fine for OSWorld overnight; not for “Hey Jarvis, open Chrome.” Reflect only on **stuck** (evaluator already coaches).
- **Cloud sandbox as the default path.** Extra screenshot upload + input inject latency. Local guest on the LAN (or same machine) is the low-latency virtual layer.
- **Gradio/demo loops** that wait for a full screenshot round-trip before the next keystroke. Batch type/hotkey; don’t screenshot between every character.

### Latency plan for this repo (concrete)

Today the slow path is: wake → STT → orchestrator LLM → `start_task` → **screenshot → cloud CU model → pyautogui → screenshot…** Voice TTS is already streamed. CU is not.

### Easy-task action traces (record and replay)

Markdown skills (`maybe_create_skill`) tell the **model** what to do; the model still screenshots and thinks. For **easy** tasks we should save the **actions themselves** and play them back through `DesktopController` with **no vision loop**.

`agent.py` already logs each batch (`computer_actions` with the raw `call.actions`). After a successful easy/medium run, persist that sequence as a **trace**, not only a SKILL.md:

```json
{
  "name": "open-chrome-url",
  "match": ["open chrome", "go to", "open url"],
  "params": ["url"],
  "actions": [
    {"type": "keypress", "keys": ["cmd", "space"]},
    {"type": "type", "text": "Google Chrome"},
    {"type": "keypress", "keys": ["enter"]},
    {"type": "wait", "ms": 800},
    {"type": "keypress", "keys": ["cmd", "l"]},
    {"type": "type", "text": "{{url}}"},
    {"type": "keypress", "keys": ["enter"]}
  ],
  "verify": {"ax_app": "Google Chrome"}
}
```

**Record (first time).** Evaluator says easy (or the run was short and succeeded). Strip one-off clicks; keep hotkeys, typed strings, and waits. Substitute the user’s variable bits (`url`, `query`, `filename`) so the next utterance can fill them. Store under `skills/*/trace.json` (or `traces/`) next to the optional SKILL.md. Prefer **named actions** (keypress, type, open-app) over raw click coordinates — coordinates rot when windows move.

**Replay (next time).** Orchestrator / a tiny matcher: if the utterance hits a trace, bind params, call `desktop.run_actions(trace)` **without** `start_task` / screenshots / CU model. Optional cheap verify: `read_ui_text` or frontmost app name. If verify fails (wrong app, dialog in the way), **fall back** to the current vision CU and refresh the trace from that run.

**Don’t replay blindly.** No traces for CAD canvas, checkout, or anything evaluator-**hard**. No click-xy-only traces unless the window map is stable. User can still say the wake word mid-replay to barge in.

This is Agent S episodic memory, but **executable** — the latency win is skipping the model entirely on the second “open Chrome, go to Hacker News.”

### Latency plan for this repo (concrete)

1. **Skip the vision loop on easy tasks** via traces above. First success records; later matches replay. Skill + AX + hotkeys + `run_terminal` still apply when there is no trace yet. Easy evaluator route should not open a full CU session if a trace matches.
2. **Cheaper screenshots.** Downscale like OOTB; JPEG/webp; send **diff or last N** frames (Agent S cap). Don’t attach a screenshot to every orchestrator turn — only the CU worker (and never on a successful replay).
3. **Overlap, don’t stack.** Capture the next screenshot (and AX dump) **while** the last action is settling, not after the model returns. Prefetch skill/trace when the orchestrator decides `start_task`.
4. **One hop to first action.** Orchestrator already knows the task; avoid a second “plan” model before the first click. No manager/worker split unless the task is evaluator-**hard**.
5. **Local/fast models only on the cheap path** (§2): STT, TTS, orchestrator. CU stays a strong cloud (or later local VLM) **without** a second grounding call.
6. **Virtual layer without WAN.** §3 guest on localhost/LAN so screenshot/click is milliseconds, not E2B round-trips.
7. **Stuck, not always-on, reflection.** Evaluator coaching + mark-done already exist; don’t add a reflector that runs every step.
8. **MCP instead of browse/scrape** (§7). Search, GitHub, Linear, analytics: one tool call on the orchestrator, not a CU session or `requests` in `run_terminal`.

**Done when.** Spoken “open Chrome, go to Hacker News” **replays a saved trace** (no CU model) after the first successful run, and falls back to vision only if Chrome isn’t frontmost or verify fails. Hard CAD tasks may still use vision; easy tasks must not.

## 7. Integrate MCP servers (tools without the desktop)

The orchestrator today has `start_task`, `ask_user`, `give_response_to_user`, and local memory tools. The computer agent has `computer`, skills, AX, `run_terminal`, and the same memory tools. Anything that is already an **API** (search, GitHub, Linear, PostHog, calendar, docs) currently goes through **screenshots** or a `run_terminal` scrape — slow, brittle, and what the last spoiler-search run did (DuckDuckGo/Google/Reddit via `requests`, empty results, timeouts).

**Be an MCP client first.** Load servers from a config file (`mcp.json` or `MCP_SERVERS` env: command/args or URL). On startup, list tools and expose a **small allowlist** to the orchestrator (and optionally the CU agent). One module (`mcp_client.py`) owns connect / list / call / errors so neither `orchestrator.py` nor `agent.py` speaks MCP JSON-RPC.

**Where the tools live.**

- **Orchestrator (default).** Voice Q&A and “look this up” should not call `start_task`. Search, issue trackers, analytics, calendar, Minimi (§4) belong here. The model speaks the answer via `give_response_to_user`.
- **Computer agent (opt-in).** Only when a desktop task needs an API mid-run (e.g. EasyEDA export, GitHub gist, fetch a URL the UI won’t give). Do not dump the full MCP catalog into the CU model — that fights the `computer` tool and burns tokens every screenshot turn.
- **Not a replacement for CU.** If the user said “open this in Chrome and click play,” still `start_task` / traces. MCP is for structured data and side effects that already have an API.

**Don’t flood the voice model.** MCP servers often advertise dozens of tools. Namespace (`linear_list_issues`, `posthog_query_trends`), cap the prompt with a catalog + `mcp_call(server, tool, args)` if the set is large, or enable servers per session (`MCP_ENABLE=linear,web-search`). Off by default until the user adds a server.

**Prefer MCP over scrape / click**, in order:

1. MCP / official API
2. `run_terminal` with a known-safe local command
3. Keyboard + named UI
4. Screenshot click

Skills should say “use the GitHub MCP” (or search MCP) instead of “open the site and copy the text.”

**Safety.**

- Opt-in per server. No auto-discovery of every Cursor/Claude MCP on the machine unless `MCP_INHERIT=1`.
- Don’t pass secrets from `.env` into MCP args in logs. Don’t let MCP tools drive `DesktopController`.
- Write/delete tools (post comment, archive, buy) need the same spoken confirm path as risky CU actions, or stay read-only until configured otherwise (`MCP_READ_ONLY=1`).

**Later (optional).** Expose CUA itself as an MCP **server** (`start_task`, `ask_user`, memories, traces) so Cursor or another agent can hand a desktop job to this process. Client-in-the-voice-loop is the latency win; server-out is for IDE integration.

**Done when.** With a search (or Linear) server in `mcp.json`, “Hey Rekha, what’s in Linear for checkout?” answers from MCP without taking the mouse, and a CU run that needs a URL/issue id calls the same client instead of scraping Google in `run_terminal`. Minimi (§4) is just another server on this client.

## 8. Point-at overlay + all-display screenshots (from Clicky)

Steal three ideas from [Clicky](https://github.com/farzaa/clicky): a **teacher overlay that points** without stealing the pointer, **every monitor in the vision prompt** with an index, and a **non-activating overlay** that can sit on any display while CU runs elsewhere. Clicky is a companion that explains; we stay a doer that can also *show*. Do not replace `start_task` with overlay-only.

### 8a. Point-at flow

Add a cheap orchestrator action (e.g. `point_at`) beside `start_task` / `ask_user` / `give_response_to_user`.

**Loop.** Screenshot the relevant display(s) → model names a target → overlay flies there → optional one-sentence TTS. No `pyautogui` click. Window behavior is §8c. Parse tags like Clicky’s `[POINT:x,y:label:screenN]`, map `screenN` to `list_monitors()` geometry, animate on a bezier, then fade out after TTS (transient presence — not a permanent buddy cursor).

**When to use it.** “Where is that button?”, mid-task coaching, confirm a target before `--auto` clicks. CU remains the hands; point-at is the teacher. Overlay xy is ephemeral UI, **not** durable skills/traces (those stay menus/hotkeys/AX).

**Done when.** “Hey Jarvis, point at the Displays pane” speaks a short hint and the overlay lands on the right control on the correct monitor, while the user’s real pointer does not jump.

### 8b. Screenshots from all displays, index-marked

Today occupancy text lists which app sits on which monitor. Computer-use
screenshots stitch every display, labeled `screen N`, and clicks map through
the virtual desktop (pyautogui origin = main display). `CU_ALL_DISPLAYS=0`
reverts to primary-only.

**Capture.** On each CU turn (and on `point_at`), grab every attached display (Quartz / ScreenCaptureKit / per-`display_id` capture already used by observe). Downscale like today’s CU cap. Attach images as `screen 0 (Built-in, secondary)`, `screen 1 (Studio Display, main / primary)` — same indexes as `list_monitors()` / occupancy.

**Prompt.** Geometry + occupancy already exist in `format_display_context` / `format_monitor_occupancy`. Add: “Image N is monitor index N. Coordinates in POINT or computer actions are relative to that image, not a stitched virtual desktop.” If token cost hurts, send all displays on the first turn of a task (and on `point_at`), then only the display that holds the target app until focus changes.

**Done when.** A window on the Studio Display is visible to the model as `screen 1`, `point_at` can land there, and CU is no longer guessing from a primary-only PNG plus a text hint that Slack is on another monitor.

### 8c. Non-activating overlay (not the tray)

The macOS **tray is status** (idle / listening / agent running). It does not teach. Clicky’s overlay is a transparent `NSPanel` that **joins all Spaces** and **does not become key** (`nonactivatingPanel`): the user keeps typing in Chrome while the buddy cursor moves. That is the right shape here.

**First slice (logs).** A click-through, non-activating panel in the tray process shows live `app_status` logs. Prefers a **secondary** display. CU screenshots include every monitor, so the panel hides for each capture and comes back after. Toggle **Log Overlay** in the menu-bar icon. Point-at cursor comes later on this same window class.

**Window.** Borderless, ignore-mouse except the drawn cursor/label if we want hover later (default: click-through so it never fights CU or the user). `canJoinAllSpaces` + `fullScreenAuxiliary` so it survives Space switches and fullscreen apps. Never `makeKeyAndOrderFront`. Never dock icon for this window.

**Which display.** The overlay can sit on the **Studio Display** (or whichever `screenN` the tag names) while computer-use still injects clicks on **primary**, or the reverse. Do not assume one fullscreen panel covering the virtual desktop; one panel per target monitor (or move a single panel’s frame to that display’s `list_monitors()` rect). Pointing on monitor 1 must not require the real pointer to leave monitor 0.

**Lifetime.** Fade in for the turn (wake / `point_at` / mid-CU coach), fade out after TTS + a short idle. Optional: keep a tiny cursor while a CU job is running so the user can see where the *agent* is about to click, still without becoming key.

**Done when.** You can type in a focused window on one display while the overlay points at a control on another, Spaces/fullscreen do not hide it, and clicking through the overlay does not steal focus or interrupt `DesktopController`.

## 9. Phone gateway (companion app)

Optional LAN HTTP+SSE process (`PHONE_GATEWAY=1`, default off). Phone sends text / mark-done; Mac orchestrator still owns CU and TTS. Agent screenshots are saved as `.runtime/phone-screen.jpg` and served at `GET /v1/screen`. Same Wi‑Fi or phone hotspot; Tailscale only off-LAN. See `phone_gateway.py`.
