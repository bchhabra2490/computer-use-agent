---
name: read-memory
description: >-
  Reads and updates stored memories under memory/ (personal facts,
  per-application notes, and screen snapshots). Use before asking the user
  for a known preference, when they say remember / save this, or when they
  say save the screen as memory.
---

# Read and save memories

Memories live in the project `memory/` folder (not the desktop). Use the
`list_memories`, `read_memory`, `save_memory`, and `save_screen_memory` tools —
do not drive Finder or `cat` unless those tools fail.

## Kinds

- **personal** — who the user is: name, location, language, standing
  preferences, people, places, hardware owned. All personal facts live in
  one file: `memory/personal/profile.md` (re-condensed after every write).
- **app** — how to use a specific application: usernames, typical workflows,
  UI quirks, last-used settings. Files: `memory/apps/<app>.md` (e.g. `hn`,
  `chrome`, `drawio`). Live window layout is not stored here.
- **screen** — a desktop snapshot: PNG + LLM description. Files:
  `memory/screens/<slug>.md` and `memory/screens/<slug>.png`.

## When to read

1. Call `list_memories` (kind `all`) if you need the index; the starting
   prompt already includes a catalog.
2. For questions about the user (“what’s my name?”, “where do I live?”),
   `read_memory` with kind `personal` (name `profile` or null — same file).
3. Before using an app that may have stored credentials/preferences
   (Hacker News username, Maps home, default browser), `read_memory` with
   kind `app` and that app’s slug.
4. Prefer memory over `ask_user` when a matching note exists. **Before every
   `ask_user`**, call `read_memory` (at least `personal` / `profile`, plus any
   relevant app note). Do not ask from the catalog preview alone. Ask only if
   memory is missing or contradictory.

## When to save

Call `save_memory` when the user states a durable fact, or after a task
reveals something you will need again:

- “Remember that…”, “save this”, “my HN username is…”
- A preference you had to ask for (OLED is I2C, default volume, etc.)

The runtime also extracts memories automatically after each voice turn and
computer-use run (user request + model replies + tool context). Personal
writes always go to `profile.md` and that file is re-condensed afterward;
app notes condense when they grow. You still save immediately when they say
remember/save this — do not wait for the post-run pass.

Use **append** for new facts; **replace** only when they correct or rewrite
the whole note. For personal use name `profile` (put topics in the text);
for apps use a short slug (`hn`, `gmail`, `github`, `youtube`).

Do **not** store passwords, API keys, OTPs, or payment details unless the
user explicitly asks you to.

## Save the screen

When the user says “save the screen as memory”, “remember this screen”, or
similar, call `save_screen_memory` immediately (optional `name` slug and
`hint`). That tool screenshots the display, describes it with a vision model,
and writes `memory/screens/`. The menu-bar **Add Memory** item runs the same
flow. Do **not** `start_task` or click around just to capture. Later,
`read_memory` kind `screen` (name null for all, or the slug).

## Examples

- HN comments → `read_memory` kind `app`, name `hn` for the username;
  if missing, `ask_user`, then `save_memory`.
- “Play my usual music” → personal profile and/or `app` `youtube`.
- “I’m Bharat in Hyderabad” → `save_memory` kind `personal`, name `profile`.
- “Save the screen as memory” → `save_screen_memory` (hint = their phrase).
