---
name: cursor-generate-project-from-prompt
description: >-
  Automates creating a local project folder, opening it in Cursor, pasting an exact code-generation prompt into Cursor's chat/editor, saving generated files to disk, running Cursor's formatter/linter, and opening the resulting file for review. Use when you want Cursor to produce and save a project sketch from a precise prompt.
---

## Steps

1. Verify prerequisites
   - Ensure Cursor is installed and can be launched on macOS (Applications or ~/Applications).
   - Ensure you have write permission to the target folder on your Desktop.

2. Create the project folder and placeholder files (Terminal)
   - Open Terminal and run (replace USERNAME if needed):
     mkdir -p ~/Desktop/projects/PROJECT_NAME
     : > ~/Desktop/projects/PROJECT_NAME/PROJECT_NAME.ino
     printf "%s\n" "Placeholder project README." > ~/Desktop/projects/PROJECT_NAME/README.md
   - Confirm files exist:
     ls -l ~/Desktop/projects/PROJECT_NAME

   Notes:
   - Use the actual project folder name in place of PROJECT_NAME.
   - The commands above create the folder (and parent Desktop/projects if missing), create an empty .ino, and write a one-line README.

3. Open the project in Cursor
   - Use Spotlight (Cmd+Space) and type Cursor, press Enter to open Cursor.
   - Or open from Terminal:
     open -a Cursor ~/Desktop/projects/PROJECT_NAME
   - Wait for Cursor to finish indexing the folder and show the project in the sidebar.

4. Paste the exact generation prompt into Cursor's chat/code-gen area
   - In Cursor, select the chat or code generation input area for the project.
   - Paste the full prompt text exactly as provided by the user. (Do NOT paraphrase or have the assistant write the code yourself.)
   - Send the prompt.

5. Wait for Cursor's response and handle clarifying questions
   - If Cursor asks clarifying questions, stop and present those questions to the user for confirmation before continuing.
   - If Cursor generates code, review the response in Cursor's preview/editor pane.

6. Save generated files to the project folder
   - If Cursor outputs a full .ino or multiple files, save them exactly to ~/Desktop/projects/PROJECT_NAME/ with the filenames requested (e.g., Pomodoro_Clock.ino and README.md).
   - Replace the placeholder README.md if the prompt asked Cursor to generate README content.
   - Use Cursor's Save or Export action (or copy/paste into the local file and save from Cursor) so the files are written to disk.
   - Verify with Terminal:
     stat -f '%z %Sm' ~/Desktop/projects/PROJECT_NAME/*

7. Run Cursor's formatter/linter (if available)
   - Open Cursor's command palette (Cmd+Shift+P) and choose 'Format Document' or 'Run Linter' as available.
   - Save the file(s) (Cmd+S) so formatted versions are persisted to disk.

8. Open the generated .ino in Cursor's editor for review
   - In Cursor's file tree, double-click the generated .ino so it is visible in the editor.
   - Confirm the editor is showing the saved file (the file should be the same path under ~/Desktop/projects/PROJECT_NAME).

9. Report back the created file paths to the user
   - Verbally and in chat report the exact full paths created, for example:
     /Users/<me>/Desktop/projects/PROJECT_NAME/PROJECT_NAME.ino
     /Users/<me>/Desktop/projects/PROJECT_NAME/README.md

## Tips

- Use exact filenames and full paths when saving so the files appear on disk where expected.
- If Cursor offers to directly save files to the filesystem, prefer that over copy/pasting to avoid truncation.
- If Cursor asks clarifying questions, present them verbatim to the user — do not assume answers.
- If Cursor cannot run a linter/formatter, save the raw generated file and run an external formatter or a shell command (clang-format for C-like files, or platform-specific tools) before final review.
- If Cursor is not installed as 'Cursor' app, adjust the open -a command to the actual app name or open it via Spotlight.
- When automating many projects, parameterize PROJECT_NAME to avoid collisions.

## Failure modes and recovery

- If saving fails due to permissions, run the mkdir and write commands with sudo or change folder ownership.
- If Cursor times out or crashes, save the prompt text and re-run the generation after restarting Cursor. Keep a copy of Cursor's generated text in a separate temp file before closing.
- If the generated code needs minor edits, prefer editing inside Cursor and re-running Format Document, but avoid altering the original prompt-based content unless requested by the user.

## When to use this skill

- Use when a user requests that Cursor be used to generate code from a precise, user-provided prompt and the generated files must be saved to a specific project folder on the Mac Desktop for later review or upload.
