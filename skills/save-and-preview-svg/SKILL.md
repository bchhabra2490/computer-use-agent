---
name: save-and-preview-svg
description: >-
  Writes provided SVG source to a file in a chosen folder, renders a PNG (using rsvg-convert or fallbacks), opens the rendered image in Preview for quick visual verification, and leaves the editable SVG in place for further edits. Use when you programmatically generate or receive SVG markup and need a reproducible preview workflow on macOS.
---

## Steps

1. Prepare inputs: an SVG text blob, a target folder (e.g. "$HOME/Documents/Computer Use Agent"), a base filename (e.g. `diagram`), and desired output pixel dimensions (optional).
2. Ensure the folder exists and is writable:
   - mkdir -p "$TARGET_DIR"
3. Save the SVG text to disk exactly as given (example uses a heredoc):
   - cat > "$TARGET_DIR/$BASE.svg" <<'SVG_EOF'
     ...paste exact SVG source here...
     SVG_EOF
   This preserves exact content and permissions.
4. Detect and choose a renderer (prefer rsvg-convert, then ImageMagick `convert`, then macOS Quick Look `qlmanage`):
   - command -v rsvg-convert || command -v convert || command -v qlmanage
5. Render to PNG using the best available tool:
   - If rsvg-convert is available:
     rsvg-convert -w <width> -h <height> "$TARGET_DIR/$BASE.svg" -o "$TARGET_DIR/$BASE.png"
     (omit -w/-h to keep intrinsic SVG size; supply integers for width/height if you want a specific pixel size)
   - Else if ImageMagick `convert` is available:
     convert "$TARGET_DIR/$BASE.svg" "$TARGET_DIR/$BASE.png"
   - Else fall back to Quick Look (creates a PNG in the specified output directory):
     qlmanage -t -s <size> -o "$TARGET_DIR" "$TARGET_DIR/$BASE.svg"
     (this writes something like `$TARGET_DIR/$BASE.png` or `$TARGET_DIR/$BASE.png.png`; check the output file)
6. Verify the rendered file exists and open it in Preview:
   - open -a Preview "$TARGET_DIR/$BASE.png"
7. Keep the SVG file for further editing; optionally also open it in an editor (open -a TextEdit "$TARGET_DIR/$BASE.svg") or keep the SVG in the Documents folder for versioning.

## Tips

- Prefer installing librsvg (provides rsvg-convert) via Homebrew: `brew install librsvg` — it gives consistent SVG rendering and a straightforward CLI.
- ImageMagick `convert` can render many SVGs but requires an ImageMagick/inkscape/ghostscript toolchain for some complex SVG features.
- Quick Look (`qlmanage`) is a convenient fallback but may produce different rasterization results and can add an extra filename suffix; check the actual output filename after running it.
- If the SVG references external fonts or CSS, rendering on your machine may differ from a browser; embed fonts or test in a browser first if fidelity matters.
- To preview without creating a PNG, you can also open the SVG directly in Preview (`open -a Preview file.svg`), but some SVG features or css-based text may not render identically compared to rsvg/convert or a browser.
- If creating many previews, script the detection+render steps and include timestamped filenames to avoid accidental overwrites.
