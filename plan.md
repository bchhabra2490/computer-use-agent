# Plan

Follow-on tracks. The voice loop (wake → STT → orchestrator → computer agent) stays as it is; these sit beside it or behind the same interfaces.

**Shipped:** passive activity tracking (`cua observe`); MCP client (`mcp_client.py`, `mcp_call`, `mcp.json`, `cua mcp login`); multi-display CU screenshots (`CU_ALL_DISPLAYS`, stitched `screen N` in `actions.py`); log + face overlays (`log_overlay.py`, `face_overlay.py`, tray toggles); phone gateway (`phone_gateway.py`, `PHONE_GATEWAY=1`); recipe prefix replay (`recipes.py`, `RECIPE_REPLAY`); difficulty router + step budgets (`evaluator.py`); post-task feedback (`task_feedback.py`); evaluator coaching; barge routing; realtime dictation paste.

## 1. Adapters for local STT, TTS, and LLM

Cloud providers are already switched by env (`STT_PROVIDER`, `TTS_PROVIDER`, `ORCHESTRATOR_MODEL`). Add a **local** implementation behind the same functions so the orchestrator and agent do not care where inference runs.

**STT** (`stt/` / `listen_for_utterance`). Same contract: mic PCM in, transcript out. **Shipped:** `STT_PROVIDER=whisperflow` (`stt/whisperflow.py`) — mlx-whisper on Apple Silicon, faster-whisper fallback, or `WHISPERFLOW_URL`. Keep Sarvam/OpenAI as other providers (`stt/openai.py`, `stt/sarvam.py`). Idle / Send / over-and-out stay in the capture loop, not in the model.

**TTS** (`tts/` / `synthesize` → WAV). Same contract: text in, WAV out. **Shipped:** `TTS_PROVIDER=piper` (`tts/piper.py`, CPU ONNX) and `TTS_PROVIDER=kokoro` (`tts/kokoro.py`, mlx-audio or kokoro-onnx). Clause streaming still goes through `tts/low_latency.py`. Keep wake-based speaker mapping (Jarvis / Rekha) as a *voice name* the adapter resolves. Cloud: `tts/openai.py`, `tts/sarvam.py`.

**LLM** (orchestrator + computer-use + memory captions).

- Orchestrator: OpenAI-compatible HTTP (`localhost:11434`, LM Studio, vLLM, MLX) so tool calling stays the same.
- Computer-use: harder — today’s path is OpenAI’s `computer` tool. Local CU needs either a CU-capable cloud model still, or a thinner loop (screenshot → local VLM → `DesktopController` actions). Ship the adapter interface first; local CU can lag STT/TTS/orchestrator.

**Config sketch.** `STT_PROVIDER=local`, `TTS_PROVIDER=local`, `LLM_PROVIDER=local` plus endpoint/model env vars. One adapter module per provider (`stt/local.py`, `tts/local.py`, `local_llm.py`) so cloud code paths stay untouched.

## 2. Virtual layer (don’t take over mouse and keyboard)

Today `DesktopController` in `actions.py` drives the **real** display via `pyautogui`. That seizes the user’s pointer and keys. Computer-use should run against an **isolated desktop** the user can watch, not the one they are typing on.

**Do this first: swap the executor, don’t rewrite the agent.** `agent.py` already talks to `DesktopController` for screenshot / click / type / scroll. Add `CU_MODE=local|virtual`:

- `local` — current pyautogui on the host (unchanged).
- `virtual` — same method names, different backend: a guest display (screenshot + inject input there only).

**Preferred isolation: Linux VM + VNC (or similar).**

- Guest has a full desktop (browser, files) the agent can operate.
- Host sees it in a window; host mouse/keyboard stay with the user.
- Screenshots and clicks are in guest coordinates, so Retina remapping in `DesktopController` becomes a backend detail.
- Skip “cloud sandbox that isn’t a GUI desktop.” A Vercel-style microVM is the wrong shape for this; we need a persistent GUI.

**Later.** Multiple agents → multiple guests, not multiple grabs of one Mac screen. `cua observe` can still watch the *host* if the user wants host memories, while CU stays in the VM.

**Done when.** `CU_MODE=virtual python orchestrator.py --auto` completes a Chrome task inside the guest while the user can keep using the Mac trackpad without the pointer jumping.

## 3. Integration with memory apps (Minimi and similar)

Don’t rebuild ambient recall from scratch. Apps like [Minimi](https://halotool.com/tool/minimi) already watch the Mac (tabs, docs, calls, Slack), keep an **on-device** vector store, and expose it to agents over **MCP**. Wire CUA as a consumer of that memory, and optionally as a writer.

**Read path (first).** Treat Minimi as one MCP server on the shipped client (`mcp_client.py` / `mcp_call`). The orchestrator queries it before `start_task` / `give_response_to_user` — “what did I decide about X”, “which tab / thread”. Keep `memory/` markdown as the durable, user-editable store; Minimi is the high-volume activity index. Swapping Minimi for another local memory app is a config change (`mcp.json` / env), not a rewrite.

**Write path (optional).** `cua observe` and explicit “save the screen / add memory” actions can also **push** summaries into Minimi (or equivalent) so CU tasks and spoken notes show up in the same recall surface the user already uses with Claude.

**Boundaries.**

- Opt-in: `MEMORY_APP=minimi|none` (plus MCP URL / connector). Off by default until the user installs and connects the app.
- No secrets in either store unless the user saved them. Don’t duplicate raw screenshots into a third-party index if Minimi already captured the screen.
- Observe vs Minimi: if Minimi is running, `cua observe` should skip overlapping capture (tabs / frontmost app) and only write CU-specific notes (skills, task outcomes, spoken preferences).

**Done when.** With Minimi connected, “Hey Jarvis, what was I reading about checkout?” can answer from Minimi context without a desktop takeover, and a finished CU task can be recalled later from the same memory layer.

## 4. Dense apps (EasyEDA, CAD, schematic / PCB)

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

**Virtual layer.** These apps are a good fit for `CU_MODE=virtual` (section 2): a dedicated guest with EasyEDA already logged in, so experiments don’t fight the user’s Mac session.

**Done when.** “Hey Rekha, open EasyEDA, new project named `usb-hub`, add a USB-C connector from the library, save” completes via menus/search/hotkeys (or a script), without the pointer hunting the canvas. Trace routing / 3D modeling stay out of scope until an API path exists.

## 5. Ideas from other computer-use agents (and how we stay faster)

Surveyed: [e2b-dev/open-computer-use](https://github.com/e2b-dev/open-computer-use), [showlab/computer_use_ootb](https://github.com/showlab/computer_use_ootb), [simular-ai/Agent-S](https://github.com/simular-ai/Agent-S), [ranpox/awesome-computer-use](https://github.com/ranpox/awesome-computer-use). They optimize for **OSWorld / demo accuracy**. We optimize for **voice-to-first-action on a personal Mac**. Copy the interfaces; do not copy the extra model hops.

### What they implement

**E2B Open Computer Use** — cloud **Linux desktop sandbox** (E2B) + VNC so the agent never touches the user’s machine. Split stack: **vision** (what’s on screen) + **action** (what to do) + **grounding** (OS-Atlas / ShowUI: where to click) + shell. Swap Groq / Fireworks / OpenRouter in `config.py`. User can pause and re-prompt. Matches our §2 virtual layer, but theirs is a **remote** microVM with extra RTT.

**Computer Use OOTB** — **no Docker**; pyautogui on the **host** Windows/macOS (same class as us). Gradio UI, even phone-as-remote. Two modes: unified **Claude Computer Use**, or **planner + actor** (GPT-4o / Qwen planner + ShowUI / UI-TARS actor). They shrink screenshot tokens at any resolution and offer 4-bit ShowUI + `max_pixels` for speed. Local ShowUI on an M2 is still **~15–20s/step** — too slow for spoken CU.

**Agent S (S3)** — research SOTA on OSWorld (~72.6% with Behavior Best-of-N). **Planner vs grounding split**: GPT-class manager + **UI-TARS** to turn “click Save” into coordinates (`OSWorldACI`). Hierarchical manager/worker, **narrative + episodic memory**, optional **reflection**, optional `call_code_agent` (Python/Bash instead of GUI). Best-of-N = several full rollouts then pick a winner — accuracy, not latency. Caps screenshot history (`max_trajectory_length=8`).

**Awesome Computer Use** — map of the field, not an agent. Useful clusters: **grounding VLMs** (OmniParser, OS-Atlas, SeeClick, UI-TARS), **workflow/experience memory** (Agent Workflow Memory, OS-Copilot — same job as our `skills/` + `memory/`), **AX-first desktop** ([Terminator](https://github.com/mediar-ai/terminator), [Fazm](https://github.com/m13v/fazm)), **local VM CU** ([trycua/cua](https://github.com/trycua/cua), ClawBox). Safety papers (popup injection) matter if we ever browse untrusted pages in a guest.

### What we should steal


| Idea                                     | From                                 | Why it helps us                                                       |
| ---------------------------------------- | ------------------------------------ | --------------------------------------------------------------------- |
| Isolated GUI guest, host pointer free    | E2B, trycua                          | §2 — prefer **local VM + VNC**, not E2B cloud RTT                     |
| Screenshot downscale / token cap         | OOTB                                 | Every CU step ships an image; smaller image = faster `computer` calls |
| Cap image turns in the trajectory        | Agent S                              | Don’t resend 20 full-res screenshots                                  |
| Code/script instead of GUI when possible | Agent S `call_code_agent`, E2B shell | Files, git, EasyEDA/KiCad APIs — 0 screenshots                        |
| Experience memory so we don’t re-explore | Agent S narrative/episodic, AWM      | **Recipes** + skills for repeatable prefixes; expand coverage         |
| AX / named UI before pixels              | Fazm, Terminator, our `read_ui_text` | Grounding VLM is a whole extra inference                              |
| Fast cheap model for routing only        | OOTB planner+actor, our evaluator    | Keep one CU model; use a small model to pick skill / skip CU          |




### What we should not copy (latency)

- **Three models per click** (vision + action + grounding). That’s 2–3 serial RTTs. Stay on **one** computer-use model; use AX/hotkeys/skills for coordinates.
- **Local ShowUI/UI-TARS on the Mac every step.** 15–20s/step kills voice. If we add a grounding model, it must be **optional** and only when AX is empty (CAD canvas).
- **Behavior Best-of-N / reflection every turn.** Fine for OSWorld overnight; not for “Hey Jarvis, open Chrome.” Reflect only on **stuck** (evaluator already coaches).
- **Cloud sandbox as the default path.** Extra screenshot upload + input inject latency. Local guest on the LAN (or same machine) is the low-latency virtual layer.
- **Gradio/demo loops** that wait for a full screenshot round-trip before the next keystroke. Batch type/hotkey; don’t screenshot between every character.



### Latency plan (remaining)

Today the slow path is: wake → STT → orchestrator LLM → `start_task` → **screenshot → cloud CU model → pyautogui → screenshot…** Voice TTS is already streamed. CU is not.

1. **Expand recipe coverage** so more easy opens (URL, app, search) skip the vision loop via `try_recipe` before `start_task`.
2. **Cheaper screenshots.** Downscale further where safe; JPEG/webp; send **diff or last N** frames (Agent S cap). Don’t attach a screenshot to every orchestrator turn — only the CU worker.
3. **Overlap, don’t stack.** Capture the next screenshot (and AX dump) **while** the last action is settling, not after the model returns. Prefetch skill/recipe when the orchestrator decides `start_task`.
4. **One hop to first action.** Orchestrator already knows the task; avoid a second “plan” model before the first click. No manager/worker split unless the task is evaluator-**hard**.
5. **Local/fast models only on the cheap path** (§1): STT, TTS, orchestrator. CU stays a strong cloud (or later local VLM) **without** a second grounding call.
6. **Virtual layer without WAN.** §2 guest on localhost/LAN so screenshot/click is milliseconds, not E2B round-trips.

**Done when.** Spoken “open Chrome, go to Hacker News” hits a **recipe** (no CU model) when the prefix matches, and falls back to vision only if verify fails. Hard CAD tasks may still use vision; easy tasks must not.

## 6. Point-at overlay (from Clicky)

Log and face overlays ship on a non-activating `NSPanel` (`log_overlay.py`). Remaining work: a **teacher cursor** that points without stealing the pointer or replacing `start_task`.

### 6a. Point-at flow

Add a cheap orchestrator action (e.g. `point_at`) beside `start_task` / `ask_user` / `give_response_to_user`.

**Loop.** Screenshot the relevant display(s) → model names a target → overlay flies there → optional one-sentence TTS. No `pyautogui` click. Parse tags like Clicky’s `[POINT:x,y:label:screenN]`, map `screenN` to `list_monitors()` geometry, animate on a bezier, then fade out after TTS (transient presence — not a permanent buddy cursor).

**When to use it.** “Where is that button?”, mid-task coaching, confirm a target before `--auto` clicks. CU remains the hands; point-at is the teacher. Overlay xy is ephemeral UI, **not** durable skills/recipes.

**Done when.** “Hey Jarvis, point at the Displays pane” speaks a short hint and the overlay lands on the right control on the correct monitor, while the user’s real pointer does not jump.

### 6b. Teacher cursor on the overlay panel

Reuse the existing click-through overlay window class. Add a drawn cursor/label that can sit on any monitor (move frame to `list_monitors()` rect for `screenN`) while CU still injects clicks elsewhere. Fade in for wake / `point_at` / mid-CU coach; fade out after TTS + idle. Optional: tiny cursor while a CU job runs so the user sees where the agent is about to click, without the panel becoming key.

**Done when.** You can type in a focused window on one display while the overlay points at a control on another, Spaces/fullscreen do not hide it, and clicking through the overlay does not steal focus or interrupt `DesktopController`.

## 7. macOS `.app` + DMG (ship as an Apple application)

Today the product is a **Python daemon** (`cua start` → `orchestrator.py`) with mic, Accessibility, Screen Recording, tray, skills, and `.env` secrets — not a normal GUI app. Goal: double-clickable `Jarvis.app` (or `CUA.app`) and an installer `Jarvis.dmg` that drags into `/Applications`, without forcing users to clone the repo and activate a venv.

**What ships.**

```
Jarvis.app/Contents/
  MacOS/Jarvis          # launcher (PyInstaller binary or stub → cua start / orchestrator)
  Resources/            # Python code, skills/, recipes/, wake models, icon
  Info.plist            # bundle id, name, NSMicrophoneUsageDescription
```

DMG wraps that `.app` with the usual “drag to Applications” layout (`create-dmg` or `hdiutil`).

**Preferred build path: PyInstaller →** `.app` **→ DMG.**

1. Entry point = `cua start` (or a tiny `app_main.py` that starts orchestrator + tray), `--windowed` so no Terminal window.
2. Bundle `skills/`, `recipes/`, `models/`, `not_to_do.md` via `--add-data`. Expect hidden-import fights for `pyautogui`, `sounddevice`, ONNX wake models, ZeroMQ — use `--collect-all` where needed.
3. **Config outside the bundle.** Do not bake `.env` into the app. First launch writes to `~/Library/Application Support/Jarvis/.env` (same for `memory/`, `logs/`, `.runtime/`); `envfile.py` loads that path.
4. **Sign + notarize** for anyone else: Developer ID Application, `codesign --options runtime`, `notarytool` + `stapler`. Unsigned builds get Gatekeeper-blocked. Personal-only: ad-hoc sign is enough.
5. DMG: `create-dmg` (or `hdiutil create -srcfolder dist/Jarvis.app …`).

**Permissions (the real catch).** After install, the user grants **Jarvis.app** (not Terminal): Screen Recording, Accessibility, Microphone, Automation (Chrome/Safari). Those stick to **bundle ID + code signature** — rebuild/re-sign and users may need to re-grant.

**Alternatives (don’t start here).** Briefcase (heavier), py2app (legacy), Platypus (thin wrapper still needs a packaged Python). For power users, keep `cua` CLI + optional Homebrew cask as a parallel distribution path.

**Scaffold when ready.** `app_main.py`, `Jarvis.spec`, `scripts/build_dmg.sh` → `dist/Jarvis.app` + `dist/Jarvis.dmg`.

**Done when.** A notarized DMG installs `Jarvis.app` under `/Applications`; double-click starts the voice orchestrator (tray + wake word) with config under Application Support; mic / Accessibility / Screen Recording prompts appear for the app itself; a spoken easy task still completes without opening Terminal.

## 8. Voice-only package (no computer-use / no device control)

Ship a **second product slice** for (a) hosts whose model/API has no `computer` tool, and (b) users who will not grant Accessibility, Screen Recording, or Automation. Same wake → STT → orchestrator → TTS loop; **no** `start_task`, **no** `agent.py`, **no** `pyautogui`, **no** pointer capture.

**Who it is for.**

- OpenAI (or other) accounts limited to chat + tools — no computer-use preview.
- Privacy-first users: voice assistant + MCP + memory only.
- Locked-down Macs where IT blocks screen-recording / accessibility for helper apps.
- Smaller install (PyInstaller bundle without CU deps, wake models optional).

**What still works (orchestrator tools only).**

- `give_response_to_user`, `ask_user`, `who_am_i`
- `list_memories` / `read_memory` / `save_memory` / `save_screen_memory` (screen save needs opt-in Screen Recording — off by default in this mode)
- `mcp_call` — GitHub, Linear, PostHog, hardware MCP, Minimi, search APIs
- `set_timer` / `list_timers` / `cancel_timer`
- Phone gateway (text/audio in; no agent screen JPEG unless user enables desktop read)

**What is disabled.**

- `start_task` and the whole computer-agent thread (recipes, evaluator CU router, `DesktopController`, post-task feedback on CU runs).
- `cua observe` (Accessibility). Tray can hide **Add Memory** / agent status when nothing runs.
- Default **off:** `read_screen`, `list_open_apps`, orchestrator desktop snapshot (`ORCHESTRATOR_DESKTOP_*=0`) — each needs Screen Recording and/or Automation; enable per permission the user actually grants.

**Implementation sketch.**

1. **Mode flag.** `COMPUTER_USE=0` or `CUA_MODE=voice` (env + `cua start --voice-only`). Single source of truth in `tools_registry.orchestrator_tools()` — omit `START_TASK_TOOL` and agent-only paths in `orchestrator.py` (`_launch_agent_job`, `_supervise_agent`, bus to agent).
2. **Prompt.** Voice-only variant of `orchestrator_prompts.py`: never mention `start_task`; on “open Chrome / click / play music” → `give_response_to_user` explaining the limit, or `mcp_call` if an API can do it; never pretend desktop work ran.
3. **Packaging.** Separate artifact: `Jarvis Voice.app` / `cua-voice` PyInstaller spec — entry `orchestrator.py --voice-only`, exclude `agent.py`, `actions.py`, `recipes` shell steps, heavy CU deps. Document in README as **Voice** vs **Desktop** SKU.
4. **Model choice.** Orchestrator model only (`gpt-5-mini`, Electron, local LLM via §1). No `AGENT_MODEL_`* / difficulty router / computer tool registration.
5. **Permissions copy.** First-run sheet: **Microphone** required; Screen Recording / Accessibility **not** requested unless user toggles “Read my screen” or “List open apps” in tray settings.

**Relationship to §2 virtual layer.** Virtual CU is for users who *want* automation in a guest. Voice-only is for users who *reject* host control entirely — do not conflate; optional future “remote CU you opt into” is a third SKU.

**Done when.** `COMPUTER_USE=0 python orchestrator.py --auto` (or `cua start --voice-only`) runs with **mic only**; “Hey Jarvis, what’s the status of checkout in Linear?” answers via `mcp_call`; “open Spotify and play X” gets an honest spoken refusal (or MCP/hardware path), not a silent `start_task` failure; PyInstaller voice bundle installs without pyautogui and passes a smoke test on a Mac with no Accessibility/Screen Recording grants.

## 9. Phone companion over Tailscale

The phone gateway ships (`phone_gateway.py`, `PHONE_GATEWAY=1`). On the **same Wi‑Fi** or Android hotspot, the phone hits the Mac’s LAN URL. **Tailscale** is the path when the phone is on cellular or iPhone Personal Hotspot (which often blocks LAN to the Mac).

**Setup (today).**

1. Install [Tailscale](https://tailscale.com) on Mac and phone; same tailnet.
2. Mac: `PHONE_GATEWAY=1 python orchestrator.py --auto` (or `cua start`). Note the printed URLs — includes `http://100.x.x.x:8742` and MagicDNS hostname when `tailscale` CLI is available.
3. Phone app / browser: base URL `http://<mac-tailscale-ip>:8742` (or `http://your-mac.tailnet-name.ts.net:8742` with MagicDNS).
4. Auth: `Authorization: Bearer <token>` — 5-char token from `.runtime/phone.token` or `PHONE_GATEWAY_TOKEN` (easy to type on phone).
5. SSE: `GET /v1/events?token=…` for live status; `POST /v1/command`, `/v1/audio`, `/v1/photo`, `/v1/control` as in README.

**Security.**

- Gateway binds `0.0.0.0` — reachable on LAN **and** tailnet, not the public internet (unless you expose the port elsewhere).
- Rely on Tailscale ACLs + short Bearer token; treat token like a garage-door PIN.
- Optional: restrict `PHONE_GATEWAY_HOST=100.x.x.x` to tailnet interface only (advanced).

**Limitations / future.**

- HTTP only (no TLS on port 8742). Acceptable on tailnet; optional **Tailscale Serve** or reverse proxy for HTTPS later.
- No first-party phone app in repo yet — any HTTP client; native app is a separate track.
- `advertise_urls()` prints Tailscale IP + MagicDNS when the CLI is installed; manual `tailscale ip -4` still works if not.

**Done when.** Mac on Tailscale, phone on LTE, companion reaches `/v1/health` and queues a command that Jarvis speaks on the Mac — no same-Wi‑Fi requirement.