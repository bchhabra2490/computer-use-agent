---
name: move-downloads-categories-to-desktop
description: >-
  Moves top-level items from ~/Downloads/Videos and ~/Downloads/Documents into ~/Desktop/Videos and ~/Desktop/Documents respectively, merging contents, preserving file metadata, skipping aliases/shortcuts and hidden files, and renaming conflicts by appending _duplicate/_duplicate_001, etc. Prompts if elevated permissions or locked/in-use files are encountered.
---

## Steps

1. Confirm start and which sources to operate on (~/Downloads/Videos and ~/Downloads/Documents). If the user confirms, proceed; otherwise abort.

2. For each category name in [Videos, Documents]:
   - Let SRC=~/Downloads/<category> and DST=~/Desktop/<category>.
   - If SRC does not exist or is not a directory, record "source missing" for this category and skip to the next category.
   - Ensure DST exists; if missing create it with: mkdir -p "$HOME/Desktop/<category>".

3. Iterate the top-level items in SRC (do not recurse automatically into hidden items at top level — subfolders will be moved as whole items):
   - Skip any item whose name begins with a dot (hidden files/folders).
   - Skip any item that is a symlink (test with [ -L ] or os.path.islink).
   - Skip Finder aliases detected by metadata. One reliable CLI test is: mdls -name kMDItemKind -raw "$path" and treat the item as an alias when the output contains the word "Alias". (On failure/empty output treat conservatively and do not move.)
   - For every non-skipped item, determine a safe destination name:
     - If "$DST/<name>" does not exist, use that name.
     - If it exists, generate a new name by inserting `_duplicate` before the extension (e.g. file.txt -> file_duplicate.txt). If that still exists, append a numeric suffix with zero padding increasing from 001: file_duplicate_001.txt, file_duplicate_002.txt, etc., until an unused name is found.

4. Move the item while preserving metadata (modification and creation timestamps):
   - Use `ditto` to copy metadata-preserving on macOS, then remove the source when copy succeeds. Example:
     - ditto "$SRC/$item" "$DST/$destname"
     - check exit status; if ditto succeeded, remove source safely: rm -rf -- "$SRC/$item" (rm -rf is required for directories; only run after successful copy).
   - If you prefer to rely on a same-filesystem atomic move (faster) you may use `mv` which preserves most metadata on the same volume; but `ditto` is recommended to preserve creation times and resource-fork metadata.

5. If `ditto` or `mv` returns a permission error (EACCES) or resource-busy/EBUSY, pause and report the exact path and error to the user and ask whether to:
   - Retry (after user closes app using the file),
   - Skip the item, or
   - Attempt with elevated privileges (sudo) — in which case explicitly request user permission before escalating.

6. Do not delete any other copies beyond removing the original item in Downloads after the successful copy. Do not remove duplicates that already existed in DST; only avoid overwriting by renaming the incoming item.

7. Keep an in-task report structure and update it as you go per category:
   - source_exists (true/false)
   - moved_count (number of items successfully moved)
   - duplicates_renamed (count)
   - skipped_items (list of names skipped because alias/symlink/hidden)
   - errors (list of {path, error_message})

8. When finished with both categories, present the report summary to the user showing per-category moved counts, duplicates renamed, skipped items, and any errors or items that need user attention.

9. Confirm completion.

## Tips

- Use `mdls -name kMDItemKind -raw <path>` to detect Finder aliases; treat symlinks ([ -L ]) the same as aliases and skip them.
- Prefer `ditto` for copying if you need to preserve creation dates and HFS/metadata: ditto preserves resource forks and extended attributes on macOS.
- Always verify `ditto` exit status before removing the source. Keep a safety-first policy: do not remove source unless copy succeeded.
- For conflict renaming, ensure numeric suffixes are zero-padded (e.g., _001) for predictable ordering.
- If many files are being moved, show periodic progress to the user (e.g., every 50 items) and allow a user cancel.
- When asking to escalate to sudo, show the exact offending path and reason so the user can decide.

## Example shell-safe snippet (reference implementation)

A compact Bash-like pseudocode reference (run only after user confirmation):

- For each category in Videos Documents:
  - SRC="$HOME/Downloads/$category"; DST="$HOME/Desktop/$category";
  - [ -d "$SRC" ] || record "source missing" and continue;
  - mkdir -p -- "$DST";
  - for item in "$SRC"/*; do
      - name=$(basename -- "$item");
      - [ "${name#*.}" != "$name" ] || true  # normal name check; skip names starting with '.'
      - if [[ "$name" == .* ]]; then record skipped and continue; fi
      - if [ -L "$item" ]; then record skipped and continue; fi
      - kind=$(mdls -name kMDItemKind -raw -- "$item" 2>/dev/null || true)
      - if [[ "$kind" == *Alias* ]]; then record skipped and continue; fi
      - dest="$DST/$name"
      - if [ -e "$dest" ]; then generate dest with _duplicate / _duplicate_001 etc. and increment duplicates_renamed; fi
      - ditto -- "$item" "$dest"  || { record error and if error suggests permission or busy, pause and ask user; continue; }
      - rm -rf -- "$item"  # only after successful ditto
      - increment moved_count
    - done

Return the per-category JSON-like report to the user when complete.

(Implementers can translate the above to a Python script using pathlib + subprocess(mdls) + subprocess.run(['ditto', src, dst]) following the same safety checks.)
