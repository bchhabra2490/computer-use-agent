---
name: use-easyeda
description: >-
  Opens and drives EasyEDA Pro on the Mac (desktop app, not the website) for
  projects, schematic/PCB chrome, and dialogs. Prefer keyboard shortcuts and
  menus for tool modes and file ops; use mouse/vision mainly for canvas
  geometry. Use when the user asks to work in EasyEDA / JLCEDA Pro.
---

## Principles (CAD / EDA)

1. **Chrome and modes → keyboard / menus.** New project, save, undo/redo, open
   library, place-wire / place-part mode, schematic ↔ PCB, ERC/DRC, zoom-fit,
   find, and dialogs: use Menu Bar items or the app’s documented shortcuts.
   Do **not** hunt toolbar icons by screenshot coordinates.
2. **Canvas geometry → mouse + vision.** Pin attachment, placing a part at a
   location, dragging traces, and “is this net connected?” need clicks and a
   screenshot. Shortcuts only put you in the right *mode*.
3. **Never invent a second eyes pipeline.** Do not `screencapture`, `tesseract`,
   or `cat` PNGs in the terminal. Use the computer tool (and vision) / 
   `read_ui_text` for dialogs.
4. **Prefer `read_ui_text` for dialogs and lists** when Accessibility returns
   labels; fall back to vision if AX is empty (canvas often is).

## Steps — open and new project

1. Open **EasyEDA Pro** from Spotlight (`Cmd+Space` → type EasyEDA → Return)
   or the Dock. Do **not** use the EasyEDA website in a browser.
2. Bring EasyEDA Pro frontmost (`Cmd+Tab` if needed). Confirm the title bar
   shows EasyEDA / JLCEDA Pro.
3. Create a new project via **File → New** (or the app’s New Project shortcut /
   button if the menu path differs). Prefer the menu over clicking a blank
   toolbar glyph.
4. When the name field is focused, type the requested descriptive project
   name. Replace any existing name only if the user asked to rename.
5. Confirm with **Return** / the dialog’s primary button, or **File → Save**
   (`Cmd+S` when that is the app shortcut). Prefer keyboard confirm over
   pixel-clicking Save when focus is already in the dialog.
6. If EasyEDA Pro shows a location, overwrite, or confirmation dialog, use
   Tab/arrows if needed, then confirm the option that completes the save
   **without** altering the schematic.
7. Wait until dialogs close. Verify the new name in the project/document title
   (title bar or AX), or that EasyEDA otherwise shows the save succeeded.

## Steps — schematic / PCB work (when the user asks)

1. Stay in the document the user named; do not start a second project unless asked.
2. Switch tools **by shortcut or menu** (Wire, Place, Move, Rotate, Zoom to fit,
   Undo). If the shortcut is unknown, use the **Menu Bar** / right-click context
   menu — still avoid guessing toolbar pixels.
3. Use library **search by typing the part name** in the library search field
   (keyboard), then place on the canvas with the mouse at the intended location.
4. After a batch of canvas edits, take **one** computer-tool screenshot (or rely
   on the next vision frame) to verify connectivity — do not OCR via shell.
5. Run ERC / design checks from the menu when asked; fix from the issue list
   using keyboard selection where possible.
6. Save with `Cmd+S` / **File → Save** before export or long idle.

## Tips

- Prefer menu labels and shortcuts over fixed coordinates; EasyEDA Pro layouts
  and window sizes vary.
- Do not redraw, move, delete, or modify circuit elements while only saving or
  renaming.
- If an overwrite warning appears unexpectedly, verify destination and filename
  before confirming.
- Preserve the user’s spelling, capitalization, underscores, and filename
  formatting exactly.
- If a shortcut does nothing, fall back to the Menu Bar once — do not spam
  random hotkeys or toolbar clicks.
- Canvas/WebGL often returns little from Accessibility; that is expected — use
  vision for the drawing area only, not for every mode change.
