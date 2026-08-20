---
name: esp32-wroom-open-pinout-diagram
description: >-
  Opens a local ESP32‑WROOM‑32 pinout file if present on the Desktop, or downloads the official Espressif ESP32‑WROOM‑32 datasheet to the Desktop and opens the datasheet to the module pin layout/figure. Use when you need a reliable way to view the ESP32‑WROOM‑32 module pin diagram on macOS.
---

## Steps

1. Check the Desktop for an existing ESP32/WROOM pinout file.
   - Terminal method: open Terminal and run:

     ```bash
     find "$HOME/Desktop" -maxdepth 2 -type f \( -iname '*esp32*' -o -iname '*wroom*' -o -iname '*esp32-wroom*' \) -print
     ```
   - If the command prints a matching file path (for example `~/Desktop/ESP32-WROOM-32_Datasheet.pdf` or `~/Desktop/esp32-wroom-pinout.png`), open it in Preview (PDF/image) or Google Chrome (image):

     ```bash
     open -a Preview "/path/to/the-file"
     # or for an image in Chrome
     open -a "Google Chrome" "/path/to/the-file"
     ```

2. If a local file was opened: bring the viewer to the front and jump to the pin layout.
   - In Preview: press Cmd+F and search for keywords such as `Pin Layout`, `Pinout`, `Pin Definitions`, or `Module` to jump to the figure. Use the arrow keys or the thumbnail sidebar to navigate if needed.
   - In Chrome: open the tab showing the image, click the image to enlarge, and use the zoom controls (Cmd+Plus / Cmd+Minus) or click the green window button to make the window large or fullscreen so the module pin layout is clear.

3. If no suitable Desktop file is found, download the official datasheet to the Desktop and open it in Preview.
   - Download with Terminal (official Espressif PDF):

     ```bash
     curl -L --fail --silent --show-error 'https://www.espressif.com/sites/default/files/documentation/esp32-wroom-32_datasheet_en.pdf' -o "$HOME/Desktop/ESP32-WROOM-32_Datasheet.pdf"
     open -a Preview "$HOME/Desktop/ESP32-WROOM-32_Datasheet.pdf"
     ```

   - After Preview opens, press Cmd+F and search for `Pin Layout`, `Pinout`, `Pin Definitions`, or `module` to jump to the module pin layout figure.

4. (Optional) If you prefer a quick image from the web instead of the PDF:
   - Open Chrome (Cmd+Space → type "Google Chrome" → Enter), search for `ESP32-WROOM-32 pinout` and open a high-resolution image. Click the image to open it in its own tab, then enlarge or fullscreen as above.

5. Verify the module pin layout is visible and readable on the desired display. If you need a local copy for future use, save the image or export the PDF page from Preview (File → Export) into ~/Desktop/Images or another preferred folder.

## Tips

- Use the Terminal `find` command above first — it is fast and reliable for spotting a Desktop file with many common name variants.
- Prefer the official Espressif PDF for canonical pin numbering; images from search results can be convenient quick references but may be derived from different board variants.
- If Preview search doesn’t find the words you tried, open the thumbnail pane (View → Thumbnails) and visually scan pages near likely figure numbers (esp. pages titled "Pin Layout" or "Module Overview").
- If you repeatedly need the same pinout, save a cropped PNG of the pin layout to `~/Desktop/Images/esp32-wroom-pinout.png` for faster access later.
- Avoid relying on any single-case filenames; use the `find` pattern so the skill catches common variants like `esp32-wroom-32_datasheet.pdf`, `ESP32-WROOM-pinout.pdf`, or `esp32_wroom_pinout.png`.
