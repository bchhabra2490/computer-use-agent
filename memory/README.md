# Memories

Durable notes for the voice / computer-use agent.

| Kind | Folder | Examples |
|------|--------|----------|
| Personal | `personal/` | name, city, language, standing preferences |
| Application | `apps/` | HN username, Maps home, app UI quirks |
| Screen | `screens/` | screenshot PNG + LLM description of the display |

Files are markdown, one topic per file (`profile.md`, `hn.md`, …). Screen
memories also store a matching `.png`. The agent reads and writes them with
`read_memory` / `save_memory` / `save_screen_memory` (see skill `read-memory`).
After each run, durable facts from the conversation (repos, songs, usernames)
are extracted into these files automatically, then a background pass condenses
duplicates. With multiple monitors, `apps/displays.md` is overwritten with the
live window layout (not condensed). Say “save the screen as memory” to snapshot
whatever is visible. Do not put secrets here unless you mean to.
