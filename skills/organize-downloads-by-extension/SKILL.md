---
name: organize-downloads-by-extension
description: >-
  Automates inspecting and organizing the user's Downloads folder into category subfolders (Images, Documents, Code, Archives, Videos, Audio, Apps, Misc, Archive). Produces an inventory, issues mid-task updates (counts and top-largest items), safely moves files by extension while preserving modification dates and contents, relocates duplicates to Downloads/Archive with _duplicate suffixes, leaves aliases/hidden files untouched, and pauses for risky items or permission dialogs. Use when you want to declutter Downloads without deleting anything.
---

## Steps

1. Confirm and begin
   - Announce that you will start and ask the user to confirm (note you will not delete anything). If the user confirms, continue.

2. Inventory the Downloads root
   - List every top-level item in ~/Downloads and record: name, type (file/folder/alias/hidden), size, and last-modified date.
   - Use Finder or Terminal; recommended terminal command: `ls -la ~/Downloads` plus a script to gather sizes and mtimes for each entry. For folder sizes use `du -sk "~/Downloads/FolderName"` or sum files in the folder.
   - Save this inventory to a timestamped manifest (e.g. `~/Downloads/downloads-inventory-YYYYMMDD-HHMM.json`).

3. Mid-task update (after inventory)
   - Send user the number of top-level items and the top 10 largest items (name, type, size, modified date).
   - If any large or suspicious items appear (e.g. very large folders, installers in use), pause and ask whether to move or leave them.

4. Prepare category folders
   - Ensure these folders exist inside ~/Downloads: Images, Documents, Code, Archives, Videos, Audio, Apps, Misc, Archive.
   - If a required category name already exists as a file (not a folder), pause and ask the user for permission to move that file to Misc so the category folder can be created.

5. Extension-to-category mapping (use these rules)
   - Images: .png .jpg .jpeg .gif .heic .webp
   - Documents: .pdf .doc .docx .xls .xlsx .ppt .pptx .txt .md .rtf
   - Code: .py .js .java .c .cpp .rb .go .sh .ts
   - Archives: .zip .rar .7z .tar .gz .tgz .bz2
   - Videos: .mp4 .mov .avi .mkv .webm
   - Audio: .mp3 .wav .m4a .flac .aac
   - Apps: .dmg .exe .msi .apk
   - Files with no extension or ambiguous types → Misc
   - Top-level folders in ~/Downloads → move the entire folder into Misc unless the folder name or contents clearly match one of the categories (e.g. a folder called "Images" or containing mostly .png/.jpg)

6. Duplicate detection and handling
   - Detect duplicates by either identical content checksum (e.g. `shasum -a 256`) or same name+size when checksums are expensive.
   - Do NOT delete duplicates. Move the duplicate(s) into ~/Downloads/Archive and append `_duplicate` to the filename. If that name already exists, append numeric suffixes (`_duplicate`, `_duplicate (2)`, ...).
   - Record duplicates in the manifest with source and new destination.

7. Move items safely and preserve metadata
   - Prefer moving on the same filesystem with `mv` (preserves modification times). If you must copy then delete, use `rsync -a` or `ditto` to preserve modification dates and metadata, then remove the original only after verifying the copy succeeded.
   - For each move, update the manifest with original path, destination, and modified time.
   - Leave aliases (symlinks) and hidden files (names starting with `.`) in place.

8. Handle conflicts and risky items
   - If a permission dialog appears or moving would affect an app that appears to be in use (e.g., an installer currently mounted or a running .dmg application), stop and ask the user before proceeding.
   - If a name conflict would overwrite an existing file, pause and ask whether to rename (append suffix), skip, or place in Archive.

9. Post-move update
   - After moving, send an update listing which category folders were created and counts of items moved into each (including duplicates moved to Archive).
   - Verify that modification dates of moved items match the inventory; report any mismatches.

10. Final summary and manifest
   - Produce a final summary of all actions (items moved, folders created, duplicates archived, files left in place) and attach or save the manifest JSON in ~/Downloads (e.g. `downloads-organize-manifest-YYYYMMDD-HHMM.json`).
   - Ask the user whether they want further changes (e.g., change categorization rules, move Softwares-type folders, remove leftover installers, or permanently delete Archive contents).

## Tips

- Use a small Python script or shell script to implement the inventory, checksum, and move logic; save a manifest so every action is auditable.
- For checksums: use `shasum -a 256 "file"` for robust duplicate detection. For large numbers of files, use name+size first, then checksum only for candidates.
- To compute folder sizes quickly: `du -sh ~/Downloads/*` (human readable) or `du -sk` for KB values.
- Preserve mtimes: `mv` preserves timestamps; if copying use `rsync -a --progress src dest` or `ditto src dest` and then verify before removing the original.
- If the user asks to exclude a particular folder (e.g. `Softwares`), record that exception in the manifest and skip it.
- When moving large files or folders, warn the user and optionally show estimated time/size so they can confirm before you proceed.
- Keep the script idempotent: if run again it should detect already-organized items and skip or report them rather than duplicating work.

Use this skill when you need a repeatable, safe process to declutter the Downloads folder on macOS without deleting user data.
