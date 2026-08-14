---
name: organize-desktop-by-extension
description: >-
  Automates a safe Desktop reorganization on macOS: inventories top-level Desktop items, creates category folders, moves files into folders by extension, moves ambiguous folders to Misc, relocates duplicates into Desktop/Archive with _duplicate suffixes, preserves modification dates, and pauses for risky items or permission dialogs. Use when a user asks to declutter the Desktop without deleting anything.
---

## Steps

1. Confirm intent and constraints with the user.
   - Confirm: do not delete files, leave aliases/hidden/system files in place, preserve modification timestamps, and pause for any risky items (very large folders, apps, system-like items) or permission dialogs.

2. Inventory the Desktop (mid-task update #1).
   - On macOS Finder: open ~/Desktop and show View→as List with Size and Date Modified columns.
   - Or run this Terminal command to produce a machine-readable inventory:
     - python3 - <<'PY'\nfrom pathlib import Path\nimport os,datetime,json\nD=Path.home()/"Desktop"\nitems=[]\nfor e in sorted(D.iterdir(), key=lambda x: x.name.lower()):\n    if e.name.startswith('.'):\n        items.append({'name':e.name,'type':'hidden','size':None,'modified':datetime.datetime.fromtimestamp(e.lstat().st_mtime).astimezone().isoformat()})\n        continue\n    st=e.lstat()\n    typ='alias' if e.is_symlink() else ('folder' if e.is_dir() else 'file')\n    size=st.st_size if typ!='folder' else sum((f.lstat().st_size for f in e.rglob('*') if f.is_file()),0)\n    items.append({'name':e.name,'type':typ,'size_bytes':size,'modified':datetime.datetime.fromtimestamp(st.st_mtime).astimezone().isoformat()})\nprint(json.dumps(items,indent=2))\nPY
   - Report: total number of top-level items, number visible vs hidden, and the top 10 largest items (folders' sizes are content-inclusive). Send this inventory as the first mid-task update.

3. Identify risky items before moving anything.
   - Treat as risky and pause to confirm with the user before touching:
     - Top-level items > 10 GB (or user-defined threshold).
     - Any item ending in `.app` or folders that contain a `Contents` folder (possible apps).
     - Items with names like `Library`, `System`, or other OS-like names.
   - If permission dialogs are expected (moving items owned by another user), notify the user and wait for approval.

4. Create category folders on the Desktop if they don't exist.
   - Required folder names (create exactly these names at Desktop top level):
     - Images, Documents, Code, Archives, Videos, Audio, Apps, Misc, Archive
   - Create via Finder or Terminal: mkdir -p ~/Desktop/{Images,Documents,Code,Archives,Videos,Audio,Apps,Misc,Archive}

5. Decide mapping from extension to category (apply to top-level files only).
   - Suggested mapping (case-insensitive):
     - Images: .png, .jpg, .jpeg, .gif, .heic, .bmp, .tiff
     - Documents: .pdf, .doc, .docx, .xls, .xlsx, .pptx, .txt, .md, .rtf
     - Code: .py, .js, .java, .c, .cpp, .h, .rb, .go, .sh, .ts
     - Archives: .zip, .rar, .7z, .tar, .gz, .tgz
     - Videos: .mp4, .mov, .avi, .mkv, .webm
     - Audio: .mp3, .wav, .m4a, .flac
     - Apps: .dmg, .app, .pkg, .exe, .msi, .apk
     - Anything with no extension or ambiguous extension: move to Misc
     - Top-level folders: move entire folder to Misc unless the folder name or contents clearly match a category (e.g., folder named "Projects" containing .py/.js files → Code). If large or risky, ask first.

6. Detect duplicates (do not delete; move to Archive instead).
   - Duplicate criteria:
     - Exact content match (recommended): compute a SHA256 (or MD5) checksum of files and treat identical checksums as duplicates.
     - Fallback: identical filename and identical file size.
   - For each duplicate beyond the first copy:
     - Move it to ~/Desktop/Archive
     - Rename by appending `_duplicate`. If that name already exists in Archive, append `_duplicate_2`, `_duplicate_3`, etc.
   - Example command to compute a checksum and move duplicate (scripted approach preferred for reliability).

7. Move files (and folders) using a method that preserves modification dates and metadata.
   - If moving within the same filesystem (typical for a single-user Desktop), mv preserves timestamps. If uncertain or crossing volumes, use rsync to preserve metadata, then remove the original:
     - rsync -a --remove-source-files "source" "destination/"
   - Alternatively, use a Python script that moves and then sets atime/mtime with os.utime(source, (atime, mtime)).
   - Leave aliases (symlinks) and hidden files untouched.
   - For each moved item, record: source name, destination folder, original size, original modification time.

8. Provide the second mid-task update after moving files.
   - Report which category folders were created.
   - For each category folder, report the number of items moved into it (count of top-level items moved).
   - List items moved to Desktop/Archive (duplicates) with original names and new names.

9. Final verification and summary.
   - Re-run the inventory (like step 2) and produce a final summary of actions taken:
     - Number of items moved per folder, items moved to Archive and their new names, folders left untouched, and any items skipped due to risk or permissions.
   - Ask the user if they want additional changes (e.g., move large 'projects' folder into Code, recursively organize subfolders, or revert any moves).

10. If the user requests a revert for specific moved items, move them back and restore timestamps (record original locations during the run to support this).

## Tips

- Always pause and ask the user when a top-level item is large (default threshold 10 GB) or appears to be an app bundle (.app) or system-like folder. Moving those without confirmation can break apps or workflows.
- Prefer scripting the operation (Python or a small shell script) to ensure consistent duplicate detection (checksums), robust renaming of duplicates, and guaranteed preservation of modification timestamps via os.utime or rsync -a.
- To compute checksums quickly on macOS: shasum -a 256 "filename". For many files, script the checksums and compare.
- When renaming duplicates, keep the extension: e.g., `photo.jpg` → `photo_duplicate.jpg` or `photo_duplicate_2.jpg`.
- Use Finder to visually inspect results if the user prefers a GUI; the script approach is useful for reproducibility and producing logs to show the user.
- Log every action to a timestamped file on the Desktop (e.g., `Desktop/desktop-organize-log-YYYYMMDD-HHMMSS.txt`) so the user can review what changed and revert if needed.

## When to run this skill

- Use when a user asks to declutter or organize their macOS Desktop by file type while ensuring no files are deleted and metadata is preserved. Do not use for one-off trivial actions (single-file moves) or when the user only wants a visual Finder sort; this skill is intended for repeatable desktop-wide reorganizations.
