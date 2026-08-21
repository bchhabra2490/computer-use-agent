---
name: diagramsnet-create-pcb-pinout-from-image
description: >-
  Creates a PCB-style pinout diagram in diagrams.net from a photo or screenshot of hardware: places component outlines, adds and labels pin shapes on component edges, draws color-coded connector lines (nets), groups components, and saves/export the diagram as a .drawio (XML) and PNG. Use when you have an image of a board or breadboard and need a reproducible pinout diagram for documentation or export to draw.io.
---

## Steps

1. Prepare the source image
   - Place the photo/screenshot you will trace into an easy-to-find folder (Desktop or Downloads). Note the filename.

2. Open diagrams.net (draw.io)
   - Launch Google Chrome (or the diagrams.net app) and open https://app.diagrams.net/.
   - Create a new blank diagram (File → New → Blank Diagram) if prompted.

3. Import the photo into the canvas and lock it as a background
   - Use File → Import From → Device (or Arrange → Insert → Image) and select your source image.
   - Position and scale the image to a comfortable working size.
   - Right-click the image and choose Arrange → Lock (or right-click → Lock) so it cannot be moved while tracing.

4. Enable electronics/connector shape libraries
   - Click **+ More Shapes** (bottom of the left shapes panel).
   - Enable the Electrical / Electronics / Connectors (or Circuit) libraries and click **Apply**.

5. Add component outlines (one per visible component)
   - From the left panel, drag a rectangle (or component symbol) over each physical component in the photo.
   - Reduce fill opacity or set a transparent fill so the photo underneath remains visible (Format → Style → Fill opacity).
   - Size and align each rectangle to match the component shape and orientation.

6. Add pin shapes on component edges
   - From the electrical/connector library pick a small terminal/circle/pin symbol (or use a small circle shape) and drag it onto the edge of the component rectangle for each pin.
   - Place one pin shape per real pin, aligned on the same edge as appropriate.
   - To speed placement: position the first pin, select it, then press Cmd+D to duplicate and move duplicates as needed.

7. Label each pin
   - Double-click each pin shape (or its adjacent text) and enter the pin name (e.g., VCC, GND, SCL, SDA, TX, RX, VIN).
   - Use the Format panel to set a small readable font size and consistent alignment.

8. Draw connector lines (nets) between pins
   - Select the Connector tool (arrow/line icon) from the toolbar or press the Line tool and draw orthogonal connectors between pin shapes.
   - Use orthogonal connectors (right-angle/orthogonalEdgeStyle) so wires look PCB-style.
   - After drawing, select an edge and use the Format panel to set stroke color and width—use consistent colors to represent nets (e.g., red for VCC, black/grey for GND, green for SDA/SCL).

9. Annotate nets and groups
   - Add short net labels near groups of wires using the text tool (press T or double-click the canvas).
   - Group each component’s rectangle, pins, and labels: select them and choose Arrange → Group (or Cmd+G) to keep them together while moving.

10. Make a clean diagram layer (optional)
   - If you want a schematic-only view, copy the grouped components and their connectors to a new layer and hide the photo layer (View → Layers). This keeps the photo as reference and produces a clean export.

11. Save and export the diagram (XML/.drawio and PNG)
   - Save the editable XML (.drawio) to your device: File → Save As → Device and name it e.g., over_and_out.drawio (the .drawio file is XML).
   - Export a static image for sharing: File → Export as → PNG (choose transparent background off if you want the photo visible or PNG of the traced diagram if you hid the photo layer). Save to Downloads or Desktop.

12. Import the .drawio/.xml into another diagrams.net session
   - In the receiving session, use File → Import From → Device and choose the previously saved over_and_out.drawio/.xml.
   - When prompted that the current diagram will be replaced, either Cancel and Save the current diagram first, or choose Discard Changes to overwrite.

## Tips

- Work with two layers: keep the photo locked on a bottom layer and draw pins/lines on the top layer so you can hide the photo for a clean export.
- Use consistent pin symbol size and font for readability; set and reuse a style via the Format panel.
- Duplicate (Cmd+D) is faster than repeatedly dragging shapes from the palette.
- For orthogonal routed connectors, select the connector and in Format → Style choose an orthogonal connector style and set a jetty/rounding if desired.
- If many pins must be added programmatically, you can prepare a simple XML/.drawio template (component rectangles + numbered pin shapes) and then import and edit labels—this speeds repeated conversions.
- When importing into a session that already has unsaved work, save/export the current diagram first to avoid losing changes.

Use this procedure whenever you need a repeatable, presentation-quality pinout diagram generated from a photograph or screenshot and exported as diagrams.net XML (.drawio) and PNG.
