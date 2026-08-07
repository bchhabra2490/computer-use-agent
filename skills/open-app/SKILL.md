---
name: open-app
description: >-
  Opens macOS applications reliably via Spotlight (Cmd+Space). Use when the
  user asks to launch an app (Chrome, Notes, Terminal, Slack, etc.) or when you
  need to switch into a specific application before continuing.
---

# Open an app (macOS)

## Steps

1. Press `Cmd+Space` to open Spotlight.
2. Wait briefly for the Spotlight field to appear.
3. Type the exact app name (e.g. `Google Chrome`, `Notes`, `Terminal`).
4. Press `Enter` to launch.
5. Wait for the app window to appear, then take a screenshot to confirm focus
   before interacting with it.

## Tips

- Prefer Spotlight over Dock clicks — Dock icons move and are easy to miss.
- If the wrong app is highlighted in Spotlight results, type more of the name
  or use arrow keys before pressing Enter.
- If Spotlight does not open, try `Cmd+Space` once more, then `ask_user` if it
  still fails (permissions / keyboard shortcut conflicts).
