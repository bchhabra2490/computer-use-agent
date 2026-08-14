# Plan

Five follow-on tracks. The voice loop (wake → STT → orchestrator → computer agent) stays as it is; these sit beside it or behind the same interfaces.

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

**Read path (first).** Treat Minimi as an MCP memory server the orchestrator can query before `start_task` / `give_response_to_user` — “what did I decide about X”, “which tab / thread”. Keep `memory/` markdown as the durable, user-editable store; Minimi is the high-volume activity index. One adapter (`memory_apps.py` or an MCP client) so swapping Minimi for another local memory app is a config change, not a rewrite.

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
