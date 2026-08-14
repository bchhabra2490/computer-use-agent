---
name: rename-images-by-content
description: >-
  Renames visible top-level image files in ~/Downloads/Images to concise content-derived labels with per-label numeric sequences, preserving timestamps and producing a mapping log. Use when you want image filenames to reflect primary image content for easier browsing/searching.
---

## Steps

1. Confirm start
   - Ask the user to confirm before making any on-disk changes. Offer a dry-run first.

2. Locate and list inputs (mid-task update)
   - Target folder: `~/Downloads/Images` (expand to the user's home path).
   - List only visible top-level files with these extensions (case-insensitive): `.jpg .jpeg .png .gif .heic .webp .tif .tiff .bmp`.
   - Exclude: directories, Finder aliases, symlinks, and hidden files (names beginning with `.`).
   - Produce and report the count and list of files found (this is the mid-task update).

3. For each file: detect primary content label
   - Run a vision classifier on the image. The classifier must return a single best label and a confidence score (0.0–1.0).
   - Label selection rules:
     - If classifier confidence is reasonably high (e.g., ≥0.6), take the returned label as the primary label.
     - If confidence is low (<0.6) but image contains mostly text (use OCR or a text-area heuristic), label as `text`, `document`, or `screenshot` according to appearance:
       - OCR large text block + document-like layout → `document`.
       - UI-like capture (menus, windows, status bars) → `screenshot`.
       - Mostly small lines of printed text / receipts → `receipt` or `invoice` where appropriate.
     - If detection cannot determine a useful label, do NOT rename the file; record it as `undetected` and skip.

4. Normalize the label
   - Lowercase.
   - Replace any character that is not alphanumeric with an underscore `_`.
   - Collapse multiple underscores to a single underscore and trim leading/trailing underscores.
   - Truncate the normalized label to at most 40 characters.

5. Produce the new filename and avoid collisions
   - Filename format: `<label>_NNN<original extension>` where `NNN` is a three-digit sequence per label starting at `001` (e.g., `cat_001.jpg`).
   - Maintain a per-label counter. If a target filename already exists in the folder, increment the counter until a free filename is found (do not overwrite).

6. Rename in place and preserve metadata
   - Perform an atomic rename/move within the same directory (e.g., Python's `os.rename()`), which normally preserves creation metadata on the same filesystem.
   - Capture original atime and mtime before renaming and restore them after rename with `os.utime()` to ensure modification/access timestamps are preserved.
   - Note: macOS birth/creation time is usually preserved by an in-place rename. If it is not preserved in a particular environment, document that restoring creation date may require developer tools (e.g., `SetFile -d`) and treat that as a special-case operation (pause and ask user if necessary).

7. Logging and reporting
   - Maintain a mapping log (CSV or JSON) in the same folder named like `rename_map_YYYYMMDD_HHMMSS.csv` containing columns: original_name, new_name, label, confidence, status (renamed/skipped/undetected), and any notes (e.g., alias, permission required).
   - Record any skipped files (aliases, hidden, undetected) and any permission dialogs encountered.

8. Safety and user interaction
   - Do not delete or move files out of the directory.
   - If any file operation triggers a permission dialog or OS error (lack of folder access), pause and ask the user before continuing.
   - Provide a dry-run mode that produces the mapping CSV without renaming so the user can review.

9. Final report
   - After processing, report counts: total images scanned, renamed, skipped, undetected.
   - Provide the full mapping log file location and optionally copy it to Desktop.

## Implementation sketch (macOS-friendly)

- Listing files (bash example):
  find "$HOME/Downloads/Images" -maxdepth 1 -type f ! -name '.*' \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.gif' -o -iname '*.heic' -o -iname '*.webp' -o -iname '*.tif' -o -iname '*.tiff' -o -iname '*.bmp' \) -print0

- Python pseudocode outline:
  - Enumerate files from the above list.
  - For each file:
    - call detect_label(path) → (label_str, confidence)
    - apply label normalization function
    - if skipped/undetected: append to log and continue
    - compute next available `<label>_NNN.ext` by checking existence
    - record original times: stat.st_atime, stat.st_mtime
    - rename via os.rename(src, dst)
    - restore times via os.utime(dst, (atime, mtime))
    - append mapping to CSV/JSON log

- Dry run: perform all steps but do not call os.rename; instead write planned mapping to the log and show counts.

## Tips

- Test on a small subset first and run the dry-run to verify label choices and sequencing before committing to renames.
- OCR can be performed with Tesseract (via pytesseract) to decide `document`/`screenshot`/`receipt` labels.
- If you rely on a cloud vision API, ensure you handle rate limits, upload consent, and privacy considerations; ask the user before sending images off-device.
- If preserving macOS creation (birth) time is critical, document that restoring it may require `SetFile` (part of Apple Developer Tools) and handle that as a user-confirmed extra step.
- Keep the mapping CSV in the same directory and also copy to Desktop for easy access; do not overwrite any existing mapping files—add a timestamp to the filename.
- Provide an easy undo path by preserving the mapping and offering a small script that reverses the renames using the mapping CSV.

This skill is intended to be used whenever a user wants to convert a flat folder of visible image files into concise, content-labeled filenames while preserving timestamps and avoiding destructive operations.
