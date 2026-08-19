---
name: read-diagram-on-display-and-report-pins
description: >-
  Reads a hardware pinout or schematic diagram that is already fullscreen on a specified attached display, captures or views the display image, zooms for legibility, identifies the requested pin numbers/labels and returns one-line name+function descriptions. Use when a diagram is visible on one monitor and the user asks for concise pin identification without opening other apps.
---

## Steps

1. Confirm which physical display is showing the fullscreen diagram (note the display name or its position in the macOS Displays layout).
2. Capture just that display: press Cmd+Shift+5, choose "Capture Selected Portion" (or drag a selection that exactly covers the diagram on the target display) and click Capture; save the screenshot to the Desktop/Downloads.
3. Open the saved screenshot in Preview (double-click or right-click → Open With → Preview).
4. In Preview, enter fullscreen and set View → Actual Size (or press Cmd+0) and then use the zoom controls until all text/labels in the diagram are clearly readable.
5. Locate the diagram’s pin numbering or labeling. If the diagram uses alternate labels instead of numeric pins, use those diagram labels.
6. For each requested pin (e.g., pin 1 and pin 2), read the label and nearby annotation, then write one short sentence per pin describing: “Pin X — NAME: brief function.” Keep each description to a single concise sentence.
7. Save or discard the screenshot per user preference and report the two one-line pin descriptions.

## Tips

- If the diagram spans multiple displays, make sure you capture only the display with the intended diagram.
- If text is very small, zoom further in Preview or use the macOS built-in zoom accessibility (Option‑Cmd‑8 toggles zoom if enabled) rather than changing the file or opening other apps.
- If the diagram uses non-standard labels, repeat the exact labels in your one-line answers (e.g., “BAT+, BATT” etc.).
- Do not open unrelated apps or navigate away from the captured image; the workflow focuses on reading the existing fullscreen diagram and reporting pin functions.
