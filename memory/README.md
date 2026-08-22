# Memories

Durable notes for the voice / computer-use agent.

| Kind | Folder | Examples |
|------|--------|----------|
| Personal | `personal/profile.md` | name, city, people, hardware, standing prefs (one file) |
| Application | `apps/` | HN username, Maps home, app UI quirks |
| Screen | `screens/` | screenshot PNG + LLM description of the display |

Personal facts always share `personal/profile.md` (legacy per-topic personal
files are merged into it). App notes are one topic per file (`hn.md`, …).
Screen memories also store a matching `.png`. The agent reads and writes them
with `read_memory` / `save_memory` / `save_screen_memory` (see skill
`read-memory`). After each run, durable facts from the conversation (repos,
songs, usernames) are extracted automatically; personal writes re-condense
`profile.md`, and app notes condense when they grow. Live per-monitor window
lists are ephemeral (prompt + `.runtime/desktop.txt`), not stored as app notes.
Say “save the screen as memory” to snapshot whatever is visible. Do not put
secrets here unless you mean to.
