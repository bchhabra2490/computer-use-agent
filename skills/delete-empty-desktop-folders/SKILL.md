---
name: delete-empty-desktop-folders
description: >-
  Checks a specified set of top-level Desktop folders (e.g. Images, Documents, Code, Archives, Videos, Audio, Apps, Misc, Archive), verifies each is empty (including hidden files), moves empty folders to the system Trash (not permanent delete), and reports which were trashed vs left. Use when you want to remove placeholder/category folders you previously created but must preserve any folder containing files.
---

## Steps

1. Confirm before starting with the user (permission dialogs may appear and should pause the workflow).

2. Switch to the Desktop view so you operate only on top-level Desktop items: open Finder and choose the Desktop folder (Finder → Go → Desktop or click the Desktop in the sidebar).

3. Prepare the folder list to check. Default names to check: `Images`, `Documents`, `Code`, `Archives`, `Videos`, `Audio`, `Apps`, `Misc`, `Archive`. If a different list is needed, substitute it now.

4. For each folder name in the list, perform these checks in order:
   - Confirm the item exists at `~/Desktop/FolderName` and is a directory. If the item is missing or not a folder, record it as MISSING or NOT_A_FOLDER and continue.
   - Verify the folder is truly empty including hidden files: run `ls -A ~/Desktop/FolderName` in Terminal. If the command prints nothing (zero-length output), the folder is empty. If anything is printed, consider the folder NONEMPTY.
     - Alternative (single-command check): `if [ -z "$(ls -A ~/Desktop/FolderName 2>/dev/null)" ]; then echo EMPTY; else echo NONEMPTY; fi`
   - If you prefer a more robust check that treats errors as NONEMPTY: `find ~/Desktop/FolderName -mindepth 1 -print -quit` — if this prints anything, the folder contains files/subfolders.

5. For folders determined EMPTY, move them to the system Trash (do not permanently delete):
   - Recommended safe method (uses Finder so it goes to Trash):
     `osascript -e 'tell application "Finder" to delete (POSIX file "/Users/<shortname>/Desktop/FolderName" as alias)'
` Replace `<shortname>` or dynamically obtain the home path.
   - Alternative: move to the current user Trash folder (`mv ~/Desktop/FolderName ~/.Trash/`) — note this preserves but does not update Finder’s Trash UI in some edge cases.
   - If a permission dialog appears, pause and ask the user for confirmation before continuing.

6. For folders determined NONEMPTY, leave them in place and record their names as "left because not empty".

7. After processing all names, summarize to the user:
   - Which folders were moved to Trash
   - Which folders were left because they contained files
   - Which names were missing or were not folders, if any

8. If requested, open the Trash in Finder for the user to verify moved items (Finder → Go → Go to Folder → `~/.Trash`) or show a screenshot of the Desktop/Trash contents.

## Tips

- Always check hidden files: a folder that appears empty in Finder may contain `.DS_Store`, `.localized`, or other hidden files — treat those as nonempty unless you intentionally want to remove them.
- Use Terminal checks (`ls -A` or `find ... -mindepth 1`) to avoid false emptiness from Finder view filters.
- Prefer using Finder/AppleScript to move items to Trash so the operation is user-reversible via the Trash UI rather than permanently deleting with `rm -rf`.
- Pause and confirm with the user whenever macOS prompts for permission to modify or delete items in case of protected locations or sandbox prompts.
- If automating for different folders, accept a parameterized list of folder names so the skill can be reused for other named groups.
