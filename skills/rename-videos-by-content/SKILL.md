---
name: rename-videos-by-content
description: >-
  Renames visible top-level videos in ~/Downloads/Videos by extracting representative frames, classifying the primary content label, normalizing that label, and applying sequential <label>_NNN.<ext> filenames while preserving timestamps and writing a mapping CSV. Use when you want content-based video filenames without moving or deleting files.
---

## Steps

1. Preconditions
   - Ensure ffmpeg and ffprobe are installed (brew install ffmpeg) and a vision classifier is available (local model or API).  Install SetFile (part of Apple Xcode Command Line Tools) if you need to preserve creation/birth timestamps exactly.

2. Inventory visible top-level videos
   - Target folder: `~/Downloads/Videos` (expand ~). Consider alternative `~/Downloads/Videos` if symlinked.
   - Allowed video extensions (case-insensitive): .mp4 .mov .mkv .avi .webm .flv .mpeg .mpg
   - Exclude: folders, aliases/symlinks, hidden files (names beginning with `.`).
   - Produce a list with file name, full path, size (bytes), mtime, ctime/birthtime.
   - Send a mid-task update (or write to console/log) with the number of videos found and the top 5 largest files by size.
   - If any file is unusually large (suggested threshold: >1 GB) or currently in use (detected with `lsof`), pause and ask for confirmation before proceeding with that file.

3. For each video (iterate in a predictable order, e.g., alphabetical)
   a. Safety checks
      - If file size > large threshold or `lsof` shows it is in use, pause and request user approval to continue.
      - If file is symlink or hidden, skip and record as skipped with reason.

   b. Extract a representative frame
      - Get duration in seconds with ffprobe:
        ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "~/Downloads/Videos/<file>"
      - Compute a midpoint timestamp: mid = max(1.0, duration/2).
      - Try to extract a single frame at mid (downscale to save memory):
        ffmpeg -y -ss <mid> -i "infile" -frames:v 1 -q:v 2 -vf "scale='min(800,iw)':'-2'" "out.png"
      - If the extracted frame is nearly black (low mean brightness), attempt 3 more extractions at mid+2s, mid+4s, mid+6s and choose first non-black frame. Implementation note: analyze pixel mean with Python Pillow (convert to grayscale and compute average).
      - Keep extracted frames in a temporary work folder (e.g., /tmp/video-labels-XXXX) and record the chosen frame path in the mapping log.

   c. Downscale/normalize frame for classifier
      - Resize to a reasonable max dimension (800 px longest side) and save as PNG/JPEG for classifier input.

   d. Run vision classifier on the representative frame
      - Use your chosen vision model/API to obtain 1) the single-primary content label (text) and 2) a confidence score.
      - If the classifier returns multiple candidates, pick the highest-confidence one.
      - If confidence is below a low-confidence threshold (e.g., <0.4) or the frame contains UI/text (detected via OCR or high proportion of high-contrast rectangular UI elements), set label to one of: `screen_recording`, `screenshot`, or `text` as appropriate.
      - If classification fails or no meaningful label emerges, mark as `undetected` and skip renaming (record in log).

   e. Normalize label
      - Lowercase
      - Replace any sequence of non-alphanumeric characters with a single underscore
      - Trim leading/trailing underscores
      - Truncate to 40 characters
      - If label is empty after normalization, set `undetected` and skip renaming.

   f. Determine target filename with per-label sequence
      - Maintain an in-memory counter per normalized label starting at 1.
      - Construct candidate filename: `<label>_NNN<ext>` where NNN is zero-padded 3 digits (001, 002...).
      - If a file with that name already exists in the target folder, increment NNN until you find an unused name. This avoids any overwrite.

   g. Rename while preserving timestamps and content
      - Atomically rename: use filesystem rename (os.rename) to change the filename within the same directory.
      - Preserve mtime and atime using os.utime(new_path, (atime, mtime)) with the original values captured before rename.
      - Preserve creation/birthtime if possible:
         - If `SetFile` is available: SetFile -d "<mm/dd/yyyy hh:mm:ss>" "new_path" (dates must be in local format acceptable to SetFile).
         - If SetFile is not available, document that creation time (birthtime) may not be changeable without developer tools; still preserve mtime/atime.
      - Verify file size and a quick checksum (e.g., md5 or sha256) pre- and post-rename to confirm contents unchanged.

   h. Record mapping row
      - For each processed file, append a CSV row with these columns:
        original_path,original_name,new_name,label,confidence,frame_path,status,reason,size_bytes,mtime_iso,ctime_iso,sha256
      - status: renamed | skipped | undetected | in_use | permission_denied
      - reason: free text if skipped or failed (e.g., "file in use", "undetected by classifier").

4. Post-processing and final report
   - Save the mapping CSV to the Videos folder with a timestamped filename, e.g. `video-rename-mapping-20260814-153215.csv`.
   - Produce a final summary: count renamed, count skipped (with reasons), location of mapping CSV, any permission dialogs encountered.
   - If any rename operations were paused due to permission dialogs, large-file confirmation, or in-use files, report which ones and await user action or retry.

5. Safety rules (must follow)
   - Do not move or delete files—only rename within the same directory.
   - If any file appears to be open/in use, ask before modifying.
   - If a file is extremely large and the user did not approve, skip it and record in the log.
   - Always avoid overwriting existing files by incrementing sequence numbers.

## Tips

- Batch / performance:
  - Extract a single downscaled frame per video (fast) instead of processing entire video. For very short videos (<5s) use a frame at 0.5s.
  - Keep temporary work directory under /tmp and clean it up after successful completion.

- Classifier guidance:
  - Provide a small labeled taxonomy (lecture, meeting, family, dog, cat, screen_recording, gameplay, presentation, lecture_slide, concert, city, beach, bathroom, undetected) to the classifier or map free-text labels into that taxonomy.
  - Use OCR to detect dominant large text/UI; if OCR text covers >30% of frame or classifier returns low confidence with many short English tokens, prefer `screen_recording` or `text`.

- Timestamp preservation on macOS:
  - os.utime will preserve atime/mtime.
  - Creation/birthtime requires SetFile (part of Apple Developer Tools) or a specialized tool. If preserving creation time is required, check for SetFile and use it; otherwise clearly document that creation time may change.

- Logging and reproducibility:
  - Write detailed logs (stdout and CSV) so the operation is auditable and reversible (mapping allows renaming back manually if needed).
  - Include sha256 checksums in the CSV so the user can be confident contents were unchanged.

- Permission handling:
  - If macOS shows a permission dialog (Full Disk Access/Downloads access), stop and instruct the user to grant permission in System Settings → Privacy & Security → Files and Folders or Full Disk Access, then resume.

- Edge cases:
  - If classifier returns a multi-word label, the normalizer will convert spaces & punctuation to underscores.
  - If many files map to the same label, numeric suffixes will increment to avoid collisions.

## Example command snippets (for implementers)

- ffprobe duration:
  ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "infile"

- ffmpeg single frame (midpoint)
  ffmpeg -y -ss 123.45 -i "infile.mov" -frames:v 1 -q:v 2 -vf "scale='min(800,iw)':'-2'" "/tmp/frame.png"

- check if file is open
  lsof -- ~/Downloads/Videos/yourfile.mov

- preserve atime/mtime in Python
  os.utime(new_path, (original_atime, original_mtime))

- SetFile creation date (if available)
  SetFile -d "08/14/2026 15:32:15" "~/Downloads/Videos/renamed.mov"

## When to use this skill
- Use when you regularly want content-based, human-readable filenames for multiple videos sitting in ~/Downloads/Videos and you want the process to be repeatable, non-destructive, auditable, and safe on macOS.

If you want, I can also provide a ready-to-run Python script that implements these steps (requires ffmpeg and a classifier API or local model).
