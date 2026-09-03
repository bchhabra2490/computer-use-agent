---
name: open-diagrams-from-folder
description: >-
  Opens PNG diagrams in Preview and editable SVGs in their default editor from a specified folder, brings the windows to the front, and arranges them for on‑screen review. Use when you regularly review or present multiple diagram files stored together.
---

## Steps

1. Confirm the target folder exists and is accessible.
   - In Finder or Terminal, verify the folder path (example): ~/Documents/Computer\ Use\ Agent
   - Terminal check: ls -la "~/Documents/Computer Use Agent"

2. Identify the files to open.
   - Decide the filename patterns to open (example patterns used below): *resnet*.png, *resnet*.svg, *res2net*.png, *se*-resnet*.svg
   - Optional Terminal listing to confirm: find "~/Documents/Computer Use Agent" -maxdepth 1 -type f \( -iname '*resnet*' -o -iname '*res2net*' -o -iname '*se*' \) -print | sort

3. Open PNG files in Preview.
   - Using Terminal (recommended for exact control):
     open -a Preview "~/Documents/Computer Use Agent"/*[Rr]esnet*.png "~/Documents/Computer Use Agent"/*[Rr]es2net*.png 2>/dev/null || true
   - Or in Finder: select the PNG files → Right-click → Open With → Preview.

4. Open SVG files in the default editor.
   - Using Terminal (uses the system default app for .svg):
     open "~/Documents/Computer Use Agent"/*[Rr]esnet*.svg "~/Documents/Computer Use Agent"/*[Rr]es2net*.svg "~/Documents/Computer Use Agent"/*[Ss][Ee]*.svg 2>/dev/null || true
   - If you prefer a specific editor (e.g., Inkscape, Illustrator):
     open -a "App Name" "~/Documents/Computer Use Agent"/filename.svg

5. Bring opened windows to the front and make them visible.
   - Use the Dock or Cmd+Tab to switch to Preview; in Preview choose Window → Bring All to Front if needed.
   - Switch to the SVG editor app (Cmd+Tab) and ensure each SVG file is visible (Window menu may list open documents).
   - If Preview opened images as tabs and you prefer separate windows: in Preview go to View → Thumbnails, then drag a tab out to create a separate window.

6. Arrange windows (optional but useful for review/presentation).
   - Manually drag windows to the desired displays. To tile on a single display, use macOS window controls (green button) or Mission Control.
   - If you want each diagram fullscreen on a particular external monitor, move the window to that monitor and click the green full-screen button.

7. Verify visibility.
   - Confirm each PNG appears in Preview and each SVG is editable in the chosen editor and is on-screen.
   - If any file failed to open, re-check its filename and open it directly via Finder or Terminal: open "path/to/file.png" or open "path/to/file.svg".

## Tips

- If Terminal globbing returns no matches, wrap the exact filename in quotes or use Finder to locate the file.
- To open only files that contain a specific substring (case-insensitive), use mdfind or find with -iname as shown in Step 2.
- If Preview groups images into a single window with tabs and you want separate windows for side-by-side viewing, drag tabs out of the Preview window or open each file individually with: open -a Preview "path/to/file.png".
- If an SVG opens in a viewer rather than an editor, change its default app: select the file in Finder → Get Info → Open with → choose editor → Change All.
- When presenting across multiple displays, move windows to the intended display before entering full-screen to ensure the correct monitor shows the content.
