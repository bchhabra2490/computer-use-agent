---
name: preview-open-and-zoom-image
description: >-
  Opens an image file in macOS Preview (or a .drawio in the draw.io web app), enters fullscreen/presentation mode, sets Actual Size / 100% zoom and, if necessary, increases zoom until the diagram is clearly readable, then announces completion. Use when asked to display a wiring diagram or other image large and readable for review.
---

## Steps

1. Open the image file in Preview:
   - From Terminal: run open -a Preview '/full/path/to/file.png'
   - Or in Finder: double-click the image or right-click → Open With → Preview.
2. Enter fullscreen (presentation) mode in Preview:
   - Press Control + Command + F.
3. Set Actual Size / 100% zoom:
   - Press Command + 0 (⌘0) to set Actual Size.
4. If the text/details are still small, increase magnification until readable:
   - Press Command + Plus (⌘+) repeatedly until details are clear from a normal viewing distance.
5. Announce completion and wait for further instruction:
   - Use the macOS speech command (or speak) to say a short confirmation such as: say 'Diagram is open and zoomed'.

Alternative for draw.io (.drawio) files:
- Open the .drawio file in the draw.io web app (app.diagrams.net) in Chrome.
- Use draw.io's Presentation mode (or Chrome fullscreen - Control + Command + F) and zoom/fit until the diagram text is readable.
- Announce completion as above.

## Tips

- If Preview opens multiple images in one window, use the sidebar to select the correct image before fullscreening.
- If full-screen keyboard shortcut is different (custom shortcuts), use View → Enter Full Screen from Preview's menu.
- Use Command + 0 to return to Actual Size if you changed zoom and need to reset.
- When using speech to confirm, ensure system audio is unmuted so the spoken confirmation is audible.
- For very large images, it may be faster to set Actual Size and then use a trackpad pinch-to-zoom or Command + Plus to reach a comfortable readability level.
