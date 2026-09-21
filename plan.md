# Plan

This document lists only work that is not yet implemented.

## 1. Local LLM and computer-use models

Complete the local-inference model layer used for reasoning and computer control.

1. Add an OpenAI-compatible endpoint adapter for the orchestrator and memory
   captions, supporting Ollama, LM Studio, vLLM, and MLX servers through explicit
   endpoint and model configuration.
2. Preserve the existing tool schemas and streaming behavior so switching between
   cloud and local inference does not change orchestrator behavior.
3. Define a computer-use adapter independent of OpenAI's `computer` tool:
   screenshot → local VLM decision → `DesktopController` actions.
4. Keep local computer use optional until a model meets the latency, grounding,
   and completion-verification requirements of the cloud path.

**Done when.** The orchestrator can run against a configured local endpoint with
the same tools, and an experimental local computer-use model can complete a
verified desktop task without changing the execution API.

## 2. Virtual desktop layer

Computer use currently controls the host Mac. Add an isolated desktop backend so
automation does not take over the user's pointer or keyboard.

1. Introduce `CU_MODE=local|virtual` behind the existing `DesktopController`
   screenshot, click, type, keypress, and scroll methods.
2. Use a persistent local Linux VM with a full GUI and VNC or an equivalent local
   display/input transport.
3. Keep guest coordinates, scaling, clipboard, file transfer, and screenshots
   inside the backend abstraction.
4. Support one isolated guest per concurrent agent in a later phase.

**Done when.** `CU_MODE=virtual` completes a browser task inside the guest while
the user continues using the Mac without pointer or keyboard interference.

## 3. External memory-app integration

Connect optional local memory products such as Minimi through the existing MCP
client without replacing the editable `memory/` store.

1. Add an opt-in `MEMORY_APP=minimi|none` configuration and documented MCP setup.
2. Query the connected memory app for high-volume activity context before asking
   the user or starting desktop work.
3. Optionally write completed task summaries and explicit spoken notes back to the
   memory app.
4. Prevent duplicate capture when both the external app and `cua observe` watch
   the same activity. Never duplicate raw screenshots or secrets automatically.

**Done when.** A question about earlier activity can be answered from the external
memory index without desktop takeover, and a completed task can be recalled there.

## 4. Dense professional applications

Improve reliability in EasyEDA, KiCad, CAD, schematic, PCB, and other canvas-heavy
applications where Accessibility exposes little useful structure.

1. Prefer official scripting and application APIs over canvas coordinates.
2. Expand EasyEDA into focused skills for window layout, navigation, library
   search, safe edits, save, and export.
3. Add equivalent packs for KiCad and other prioritized applications.
4. Create resize-aware labeled UI maps only where APIs, keyboard commands, and
   Accessibility cannot reach a control.
5. Keep freehand routing and precision modeling out of scope until an API-backed
   workflow exists.

**Done when.** The agent can create and safely edit a basic project through named
controls, search, hotkeys, or scripts without hunting the canvas by coordinates.

## 5. Remaining latency and context optimizations

Improve visual-task latency and context efficiency:

1. Expand recipe coverage for frequently repeated applications and websites.
2. Reduce computer-use image cost beyond the existing width cap with efficient
   encodings, frame diffs, and a bounded screenshot history.
3. Capture the next screenshot and Accessibility snapshot while the previous
   action settles where this can be done without observing an intermediate state.
4. Prefetch likely skills and recipes during task handoff.
5. Use the virtual desktop locally or over the LAN so isolation does not add a WAN
   round trip.

**Done when.** Common tasks consistently take the deterministic path, and visual
tasks reduce image bytes and idle gaps without lowering completion accuracy.

## 6. Point-at teacher overlay

Add a visual teaching cursor that never moves the user's real pointer.

1. Add a `point_at` orchestrator action for questions such as “where is that
   button?” and for optional pre-click confirmation.
2. Resolve the target from the current screenshot and Accessibility information,
   then place a click-through overlay on the correct display.
3. Animate a cursor and short label, optionally speak one sentence, and fade the
   overlay after completion.
4. Ensure the overlay remains non-activating across displays, Spaces, and
   fullscreen applications.

**Done when.** The overlay points to a requested control on any display while the
user retains focus and full control of the real pointer and keyboard.

## 7. macOS application and DMG distribution

Package the Python daemon as a signed, double-clickable macOS application.

1. Add an application entry point and PyInstaller specification for a windowless
   `Jarvis.app` containing required code, skills, recipes, and model assets.
2. Store configuration, memory, logs, and runtime state under
   `~/Library/Application Support/Jarvis`; never bundle `.env` secrets.
3. Add first-launch permission guidance for Microphone, Accessibility, Screen
   Recording, and browser Automation.
4. Add reproducible signing, hardened runtime, notarization, stapling, and DMG
   creation scripts.
5. Keep the existing `cua` CLI as a parallel power-user installation path.

**Done when.** A notarized DMG installs `Jarvis.app`, double-click starts the tray
and voice orchestrator, permissions attach to the stable application identity,
and an easy spoken task completes without Terminal.

## 8. Voice-only distribution

Create a smaller mode for users who do not want computer control or cannot grant
Accessibility and Screen Recording permissions.

1. Add one mode flag, exposed as `cua start --voice-only`, that removes
   `start_task`, agent supervision, desktop snapshots, and computer-use tools.
2. Provide a voice-only orchestrator prompt that answers through native tools,
   memory, timers, `browser_data`, and MCP, and clearly refuses unsupported
   desktop actions.
3. Make screen reading and open-app inspection separate opt-in permissions.
4. Produce a smaller `Jarvis Voice.app` artifact without computer-use dependencies.

**Done when.** Voice-only mode runs with microphone permission alone, handles
questions and connected-service actions, and never silently attempts desktop work.

## 9. Phone transport hardening

1. Add optional HTTPS through Tailscale Serve or a documented reverse-proxy setup.
2. Add a simple option to bind only to the selected tailnet interface instead of
   every LAN interface.
3. Review token rotation and device revocation for long-lived installations.

**Done when.** Users can opt into encrypted tailnet transport, restrict gateway
exposure, and revoke a previously paired phone without recreating the installation.

## 10. Advanced browser-data work

1. Replace or augment the basic HTML extractor with a focused readability parser
   for cleaner article Markdown and structured-field extraction.
2. Add bounded parallel retrieval for multi-source research while preserving
   per-page backend, timing, evidence, and failure metadata.
3. Extend Chromium through CDP/Playwright for screenshots, iframe inspection,
   downloads, uploads, dialogs, navigation events, and verified final URL/status.
4. Enforce robots policy consistently across HTTP and Chromium, and strengthen
   redirect/private-network protection for browser-rendered requests.
5. Add an optional authenticated automation profile only as an explicit opt-in,
   with encrypted storage, narrow account scope, revocation, and deletion controls.
   Never copy the user's everyday Chrome profile or ambient credentials.
6. Add evaluation fixtures for readability, parallel retrieval, JavaScript,
   iframes, downloads, authentication boundaries, private-network redirects,
   timeouts, and visual-only pages.

**Done when.** Multi-page research is bounded and produces clean extraction;
Chromium handles complex browser features with verified navigation metadata;
isolated backends enforce one network policy; and authenticated automation is
explicit, scoped, revocable, and separate from the user's normal browser.

## 11. VoiceOS-inspired voice product

Copy the parts of [VoiceOS](https://www.voiceos.com/) that make voice feel like
an OS, without becoming a connector App Store. Keep computer use as the thesis.
Dictation stays a mode, not the headline. Confirm consequential sends, not every
Accessibility click.

### Modes

Most utterances should not start a computer-use job. Split the existing wake,
Fn, and chat paths into explicit modes:

1. **Dictation.** Hold Fn (already implemented) writes into the focused field.
   Upgrade the paste path so speech is cleaned before it lands: strip filler,
   apply self-corrections (“actually I mean tomorrow”), fix grammar and
   punctuation, and adapt tone to the frontmost app (mail vs chat vs code).
2. **Edit.** With a text selection, spoken commands rewrite in place: shorten,
   expand, change tone, fix grammar, translate. This does not require
   `start_task` or screenshots.
3. **Ask / point.** Treat the pointer, focused AX element, and frontmost app as
   implicit context for “this,” “here,” and “that button” without describing the
   window. Reuse `focused_edit_info` and screenshot crops around the cursor.
   Teaching overlays remain section 6; this item is context for questions and
   drafts, not a pointing cursor.
4. **Agent.** Only route to `start_task` when the user wants the machine to act.
   Fast-path MCP, mail/chat drafts, and “reply to this” must not open the slow
   visual computer-use lane.

**Done when.** Hold-Fn dictation produces polished text in Mail and Slack;
selecting a paragraph and saying “make this shorter” rewrites it in place;
“what is this?” answers from cursor/focus context; and “reply to this email”
does not launch `DesktopController`.

### Confirm before send

Per-step GUI confirms and `--auto` already exist. What is missing is a VoiceOS-
style preview for actions that leave the machine.

1. Before sending mail, chat, calendar invites, payments, or other irreversible
   external side effects, show a compact preview (to, body, destination) and
   wait for spoken or click confirmation.
2. Keep `--auto` for on-screen clicks, typing, and local files. Do not treat
   `--auto` as permission to send or pay.
3. Allow a single spoken “send it” / “yes” to approve the preview; barge-in
   cancels.

**Done when.** A request to email or Slack someone always surfaces a preview,
even under `--auto`, and nothing is sent until the user confirms.

### Perceived latency and privacy posture

1. Treat sub-second dictation and mode-switch feedback as product work: overlay
   state, chimes, and not starting the visual agent for writing or Q&A (extends
   section 5 without replacing it).
2. Make observer recording, screenshot memory, and raw audio retention
   obviously opt-in, matching VoiceOS’s “audio is not stored unless you say so”
   default. Learning from accepted skills and editable `memory/` stays on.

**Done when.** Writing and ask-about-this turns feel immediate and never capture
the screen unless computer use or an explicit observe/memory action is running.

Out of scope here: a first-party Gmail/Slack App Store, Windows packaging, and
confirm-on-every-click. Connectors remain MCP plus GUI fallback.
