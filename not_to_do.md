# Not to do

Always-on policy for the computer-use agent and orchestrator. This is not a skill to load — follow it on every task.

- Do not use `run_terminal` `sleep` (or `sleep && say …`) to wait out a song, video, or timer. Starting playback is the task; then `mark_done`. For a countdown or reminder, call `set_timer` (do not click Clock.app).
- Do not use macOS `say` for updates the user should hear. Spoken updates are `mark_done`, `ask_user`, or orchestrator `give_response_to_user`.
- Do not keep the computer-use loop occupied watching a player until a track ends unless they asked you to click something at a specific timestamp.
- Do not treat evaluator coaching as a command to invent Terminal announcement scripts.
- Do not restart a task that already succeeded.
- Orchestrator `start_task` is a goal, not a UI screenplay (no Chrome / new tab / Spotlight / keypress recipes in the task string).
- Save every user-facing file the agent creates, downloads, exports, or generates under `~/Documents/Computer Use Agent/` unless the user explicitly specifies another destination in the current request. This includes SVG, PNG, PDF, CSV, JSON, text, reports, exports, and generated media. Create the folder if needed. This default overrides example Desktop/Downloads paths in skills. Internal logs, runtime files, caches, recipes, and `memory/screens` remain in their project-managed locations.
