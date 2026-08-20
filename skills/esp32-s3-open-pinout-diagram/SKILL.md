---
name: esp32-s3-open-pinout-diagram
description: >-
  Opens a web page containing the ESP32‑S3 (e.g., ESP32S3N16R8) pinout/diagram, reveals the interactive pin map or datasheet section, captures a verification screenshot, and copies the canonical URL. Use when a reproducible fetch of the ESP32‑S3 pin diagram and a saved verification artifact is needed on macOS.
---

## Steps

1. Open Google Chrome (Spotlight: Cmd+Space → type "Chrome" → Enter) and wait for it to become the frontmost app.
2. Focus the address bar (Cmd+L) and search for the variant: type `ESP32-S3 N16R8 pinout` (or `ESP32S3N16R8 pinout datasheet`) and press Enter.
3. From the search results, prefer the official Espressif product page or the datasheet PDF. Click a result named like “ESP32‑S3 | Espressif” or a datasheet link (PDF). If an interactive pinout page appears (e.g., “Explore the pinout”), proceed to step 4.
4. If the page shows an “Explore the pinout” or similar button, click it. If no button is visible, open the page’s top navigation and click “Pinout”, or press Cmd+F and search for the word “pinout”/“pin”/“GPIO” and open the linked section.
5. When the pin diagram is visible and legible on-screen, take a verification screenshot of the Chrome window:
   - Press Cmd+Shift+4, then press Space, then click the Chrome window to save a window screenshot to Desktop.
6. Copy the current tab’s full URL to the clipboard: press Cmd+L then Cmd+C.
7. (Optional) If you prefer the static datasheet PDF, open the datasheet link and save it: Cmd+S → choose Downloads or Desktop → Save.
8. Confirm completion by noting the screenshot filename on the Desktop and that the tab URL is on the clipboard.

## Tips

- If search results list many third‑party pinouts, prefer Espressif’s official pages or the device datasheet PDF for accuracy.
- Variant names sometimes appear without hyphens (ESP32S3N16R8) — try both spellings if the search fails.
- If the interactive pinout uses a canvas and you need a higher‑resolution copy, open the datasheet PDF or use Chrome’s Print → Save as PDF to capture a larger image.
- If the diagram is zoomed out, use the browser zoom control (Cmd+Plus/Cmd+Minus) before taking the screenshot to ensure labels are readable.
- Use the Desktop screenshot file name and the copied URL as verification artifacts for future reference.
