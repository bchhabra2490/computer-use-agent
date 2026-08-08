---
name: diagramsnet-create-and-export-diagram
description: >-
  Creates a diagram in diagrams.net (app.diagrams.net) on macOS, arranges labeled blocks and connectors, saves the .drawio to Device/Downloads, and exports a PNG to Downloads. Use when asked to make and save a block diagram for reuse or distribution.
---

## Steps

1. Open Chrome (or your preferred browser):
   - Use Spotlight (Cmd+Space) → type "Google Chrome" → Enter.
2. Go to diagrams.net: navigate to https://app.diagrams.net/ and wait for the editor to load.
3. Choose Device (local) storage when prompted so the diagram file can be saved/downloaded to your Mac.
4. Create a new blank diagram and name it exactly: `esp32_power_diagram.drawio`:
   - If a template dialog appears, choose "Blank Diagram" → Create. If asked to name the file, enter the filename.
5. Add five rectangular blocks and arrange them left-to-right:
   - Open the left palette (General shapes) → drag a rectangle onto the canvas.
   - With the rectangle selected, press Cmd+D to duplicate until you have 5 copies.
   - Place them left-to-right with even spacing. Recommended order (left→right):
     - "5V USB Charger"
     - "TP4056 (charger module)" (or custom marking like "+ / − (input)\nVB+ / B−\nOUT+ / OUT−" if you prefer)
     - "Li-ion Battery (protected)"
     - "Boost Converter (to 5V)"
     - "ESP32 (Dev board)"
   - To edit a block label: double-click the shape, type the text, press Enter.
6. Draw straight connectors and label them (use the straight connector tool):
   - Select the connector tool (line / connector) from the top toolbar and choose a straight connector style.
   - Click a connection handle on the source shape, then the target shape to create each connection.
   - After placing each connector, double-click its midline to add the label text.
   - Required connectors and labels (direction is source → target):
     - 5V USB Charger → TP4056 IN+  (label: "5V (IN+)")
     - TP4056 B+ → Battery +      (label: "B+")
     - TP4056 B- → Battery -      (label: "B-")
     - Battery + → Boost VIN+      (label: "VIN+ / Battery +")
     - Battery - → Boost VIN-      (label: "VIN- / Battery -")
     - Boost 5V OUT → ESP32 5V    (label: "5V OUT")
     - Boost GND → ESP32 GND      (label: "GND")
     - Also show TP4056 IN- → Charger GND and TP4056 B- → Battery - (common ground) as connectors and label accordingly.
7. Turn on arrowheads for connectors and make connectors legible:
   - Select all connectors (Shift+click each or drag-select) → open the Style/Format panel → in the Line/Arrows options set an arrowhead at the end (e.g., block or classic) and ensure endFill is on.
   - Set connector stroke width to 2 and choose a dark color for contrast.
8. Set fonts and sizes for legibility:
   - Select all shapes and text elements → set Font to a readable face and size (e.g., 14–18 px) using the Format panel.
9. Add the safety note text box:
   - Drag a text or sticky note shape onto the canvas and paste the safety lines:
     "Use protected cell or TP4056 with protection; set charge current ~0.5C; avoid heavy load while charging."
   - Place the note near the battery/charger area and set its font slightly smaller if needed.
10. Align and tidy the diagram:
    - Use the alignment buttons in the toolbar and the grid/snap (enable grid if needed) for even spacing.
11. Save the diagram file to Device (Downloads) as `esp32_power_diagram.drawio`:
    - File → Save As → Device (or File → Save to Device) → set filename exactly to `esp32_power_diagram.drawio` → Save. The browser will download the file to ~/Downloads.
    - Alternatively, press Cmd+S and follow the Device download dialog if presented.
12. Export a PNG copy named `esp32_power_diagram.png` and save to Downloads:
    - File → Export as → PNG…
    - In the PNG export dialog: set Zoom to 100% (or desired scale), enable options that preserve connectors/arrows (e.g., "Include connection arrows" or "Include a copy of my diagram" if relevant), optionally enable transparent background, then click Export.
    - When the browser Save dialog appears, name the file `esp32_power_diagram.png` and save to ~/Downloads.
13. Verify both files are in your Downloads folder, then report their locations and (if possible) attach them.
    - Files should be at: ~/Downloads/esp32_power_diagram.drawio and ~/Downloads/esp32_power_diagram.png

## Tips

- Duplicate shapes quickly: select a shape → Cmd+D (duplicate) → drag into place.
- Label connectors by double-clicking the connector line; move the label by dragging it.
- If connectors snap to odd points, adjust exit/entry points in the Style panel (exitX/exitY / entryX/entryY) or drag the connector endpoints to new handles on the shapes.
- Use straight connectors from the top toolbar for a clean block diagram.
- If diagrams.net prompts to store files in cloud services, explicitly pick "Device" or "This device" to ensure .drawio downloads to Downloads.
- If export options include a checkbox for "Include connection arrows" or "Edges/Arrows", enable it so the PNG clearly shows arrowheads.
- If you want consistent text size across shapes, set the font and size for one shape, then use the Format painter or select all shapes and apply the font size.
- When running this skill unattended, add short progress updates when any step (loading, saving, exporting) takes longer than a few seconds.

Use this skill whenever you need a repeatable, labeled block-diagram created in diagrams.net and saved/exported locally on macOS.
