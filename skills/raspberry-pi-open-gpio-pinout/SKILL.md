---
name: raspberry-pi-open-gpio-pinout
description: >-
  Opens a high-resolution GPIO pinout diagram for a specified Raspberry Pi model in Google Chrome on macOS, verifies the model text on the page or image, captures a screenshot, and copies the canonical image/page URL. Use when you need a reproducible pinout image and verification artifacts for Raspberry Pi 2/3/4/Zero boards.
---

## Steps

1. Bring Google Chrome to the front (Spotlight: Cmd+Space → type "Chrome" → Return, or click the Dock icon).
2. Open a new tab (Cmd+T).
3. In the address bar (Cmd+L) type a precise query, for example:
   - Raspberry Pi 3 Model B GPIO pinout
   - Raspberry Pi 4 GPIO pinout
   Press Return to run the search.
4. Switch to the Images results (click “Images” or press Tab to focus the Images link then Enter) or scan the top search results for authoritative sources (pinout.xyz, raspberrypi.org, Adafruit, SparkFun).
5. Locate a clear 40‑pin header image labeled for the requested model. Prefer sites in this order: pinout.xyz, raspberrypi.org/documentation, adafruit.com, sparkfun.com. 
6. Open the image at full resolution:
   - Right‑click the thumbnail and choose “Open image in new tab” (or click the image and use the page link to the image file/source page).
   - If a new tab opens as an image file, switch to it (click the tab or use Cmd+Option+Right Arrow until you reach it).
7. Verify the model: on the image/source page press Cmd+F and search for the model text you requested (e.g., "Model B", "Raspberry Pi 3", or "Raspberry Pi 4"). Confirm the page or image caption explicitly references the model.
8. Copy the canonical URL:
   - Focus the address bar (Cmd+L) and copy the full URL (Cmd+C).
   - Paste it to the clipboard or save it to a note for future reference.
9. Capture a verification screenshot:
   - Use macOS screenshot (Cmd+Shift+4, then Space to capture the window) or Cmd+Shift+5 to capture the full tab area. Save the file to Desktop or Downloads with a clear name (e.g., "raspi3-pinout-YYYYMMDD.png").
10. If the image does not explicitly identify the model, repeat the search and open a different result from an authoritative source until a labelled diagram for the requested model is found.

## Tips

- Prefer pinout.xyz when available because it provides canonical, model‑specific pin maps and a stable URL. 
- If multiple variants appear (Pi 2 vs Pi 3 vs Pi 4), check the page date or caption; search within the page for the model string.
- Save both the image file screenshot and the source page URL so you can later confirm provenance.
- If you need to reuse this in automation, target the pinned URLs (pinout.xyz or raspberrypi.org) instead of arbitrary images that may move.
