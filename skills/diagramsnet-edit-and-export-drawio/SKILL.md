---
name: diagramsnet-edit-and-export-drawio
description: >-
  Edits an existing diagrams.net (draw.io) diagram to apply presentation-quality styling (fonts, color-coded nets, annotated components and wiring), saves a new .drawio copy, exports PNG and PDF to a specified folder, and opens the PNG full-screen for final verification. Use when you need to clean up and export wiring or block diagrams for presentation.
---

## Steps

1) Prepare / open the source file
   - In Finder, navigate to the folder containing the source file (example path: /Users/b-eq/Desktop/Pomodoro_Cube).
   - Open the file Pomodoro_Cube_Wiring.drawio with the draw.io (diagrams.net) desktop app or in Chrome (File → Open → Device → select the .drawio file). If the draw.io desktop app is installed, right-click → Open With → draw.io for the more responsive editing experience.

2) Set page size and default text styling for presentation
   - Open Format / Page settings and set a large canvas (landscape) suitable for presentation (example canvas: 2400×1600 px or larger).
   - Select the default text style in the Format panel: set font to a Sans family (e.g., Helvetica/Arial), set font size to 16–20 pt (I recommend 18 pt), and set key labels to bold. Use the style toolbar to update selected text and then use the style panel's "Set as default style" (or copy/paste style) so new shapes use the same typography.

3) Create clear module blocks and enlarge symbols
   - For each component (ESP32 Super Mini C3, SSD1306, MPU6050) use a rounded rectangle with a thick border. Increase the block size so internal pin labels are large and readable at full-screen zoom.
   - Inside each block, list pins line-by-line (left or right) using the chosen font size. Bold the module names and any critical labels.

4) Apply net color conventions (concrete, repeatable steps)
   - Create connector lines for signals and set stroke color and weight per the convention:
     - VCC (3.3V) = red, thick line
     - GND = black/grey, thick line
     - SDA = orange
     - SCL = purple
     - INT = green
     - Other signals = blue
   - Set arrowheads or endpoints consistently and increase stroke width for rails/buses. In the Format panel set Line -> Stroke Color and Line -> Width.

5) Make shared nets visually obvious
   - For SDA and SCL, draw thick parallel wires or a single thick bus shape and label it "I2C bus (shared)". Use orange for SDA and purple for SCL; place a clear label on the bus.
   - For power rails, draw bold red (3.3V) and bold black/grey (GND) rails across the diagram and label "Shared power rails".

6) ESP32 Super Mini C3 block specifics
   - Inside the ESP32 block list: 3.3V, GND, GPIO4 (SDA), GPIO5 (SCL), GPIO10 (INT).
   - Add an annotated sub-list of pins NOT to use: GPIO2, GPIO8, GPIO9 = strapping pins; GPIO12–GPIO17 = flash-related (avoid). Add the text note: "Avoid strapping/flash pins for control signals" near this list.
   - Add a short note near the power pins: "Ensure module has onboard 3.3V regulator; if not, provide 3.3V regulator from 5V supply."

7) SSD1306 OLED block specifics
   - Inside SSD1306 block list: VCC, GND, SDA, SCL, RST (if present). Add a note: "Default I2C address: 0x3C (sometimes 0x3D depending on SA0). Check module solder jumper/SA0 to change to 0x3D."
   - Connect VCC→3.3V (red), GND→GND (black), SDA→I2C bus (orange), SCL→I2C bus (purple).
   - For RST show two wiring options (draw both and label them):
     - Option A: Tie RST to 3.3V through a 10k resistor (label: "RST tied to 3.3V through 10k if no controlled reset needed").
     - Option B: Connect RST to any free non-strapping GPIO (label: "Connect to free GPIO for software reset — avoid strapping pins").

8) MPU6050 block specifics
   - Inside MPU6050 block list: VCC, GND, SDA, SCL, INT, AD0/SDO.
   - Add I2C address note: "Default I2C address: 0x68 (AD0/SDO=0) or 0x69 (AD0/SDO=1). Set AD0 by pulling to GND or VCC; add 10k pull-down/pull-up as required." Place small resistor symbol by AD0 and label 10k.
   - Connect VCC→3.3V, GND→GND, SDA→I2C bus (orange), SCL→I2C bus (purple), INT→GPIO10 (green) and label that connection "MPU6050 INT -> GPIO10 (dedicated)".

9) I2C pull-ups and decoupling
   - Draw and label two pull-up resistors (4.7k recommended) from SDA and SCL to 3.3V with the text: "Add if your breakouts do not include pull-ups." Place them near the bus origin (close to ESP32 pins).
   - Add decoupling capacitors: draw 0.1 uF ceramics close to each module VCC pin and label them "0.1uF ceramic near <module> VCC". Add a bulk 10uF capacitor near the 3.3V regulator labeled "10uF bulk near 3.3V supply." Use capacitor symbols and place callouts visually near the rails.

10) Add visible notes and warnings on the diagram
   - Include always-visible text boxes with these lines:
     - "All signals are 3.3V — do not connect 5V devices directly."
     - "Shared pins: SDA (GPIO4) and SCL (GPIO5) are shared between SSD1306 and MPU6050."
     - "MPU6050 INT -> GPIO10 (dedicated)."
     - "Check and avoid strapping/flash pins for signals that affect boot."
     - "Verify module I2C addresses before powering up."
   - Place these notes in a corner with a subtle background color so they remain readable when presented.

11) Clean up layout and check visual hierarchy
   - Align and distribute modules evenly (Arrange → Align / Distribute). Ensure connectors are orthogonal and do not overlap text. Use thicker lines for rails and bus shapes, and smaller connector arrows for signals.
   - Zoom to full-canvas and visually verify all labels are legible at 100%/Actual Size.

12) Save the new .drawio file to the requested path
   - File → Save As → Device and save as: /Users/b-eq/Desktop/Pomodoro_Cube/Pomodoro_Cube_Wiring_Cleared.drawio
   - Confirm the file exists in Finder after saving.

13) Export PNG and PDF to the requested filenames and folder
   - File → Export as → PNG:
     - Set resolution/width large enough for readability (e.g., 300 DPI or width ≈ 3600 px), check "Crop" or "Crop to content" as needed. Set scale so text remains crisp. Export and save to: /Users/b-eq/Desktop/Pomodoro_Cube/Pomodoro_Cube_Wiring_Cleared.png
   - File → Export as → PDF:
     - Export as vector PDF (if draw.io option available) or high-resolution PDF and save to: /Users/b-eq/Desktop/Pomodoro_Cube/Pomodoro_Cube_Wiring_Cleared.pdf

14) Open the PNG in Preview and present for final verification
   - In Finder double-click Pomodoro_Cube_Wiring_Cleared.png to open with Preview, or open Preview and use File → Open.
   - In Preview: View → Actual Size (Cmd+0) to show 100%/Actual Size. Then enter full-screen (click green window button or press Ctrl+Cmd+F).
   - If any text still looks small, use View → Zoom In (Cmd+= or Cmd+Plus) until everything is readable from normal presentation distance. Avoid resizing that blurs text — prefer increasing export resolution if text becomes pixelated.

15) Final spoken confirmation
   - When satisfied, speak/write exactly: "Cleared diagram created and open; saved to Desktop/Pomodoro_Cube." and include exact file paths in your report:
     - /Users/b-eq/Desktop/Pomodoro_Cube/Pomodoro_Cube_Wiring_Cleared.drawio
     - /Users/b-eq/Desktop/Pomodoro_Cube/Pomodoro_Cube_Wiring_Cleared.png
     - /Users/b-eq/Desktop/Pomodoro_Cube/Pomodoro_Cube_Wiring_Cleared.pdf

## Tips

- If using the web diagrams.net editor in Chrome, use File → Save As → Device to control the destination folder. The desktop draw.io app is simpler for saving directly to device paths.
- Before adding external pull-ups, check if SSD1306 or MPU6050 breakout boards already include pull-ups; duplicate pull-ups can change bus characteristics.
- To ensure crisp text in PNG, export at a higher pixel width (e.g., 3600 px) rather than relying on zooming in Preview.
- For the RST option, show both wiring diagrams visually and mark the chosen option with a bold checkmark if you prefer one.
- Keep the I2C bus origin near the ESP32 pin cluster; place pull-up resistors physically close to the microcontroller side in the diagram to indicate recommended layout.
- If you discover a hardware pin conflict (for example a requested signal uses a strapping or flash-related pin), annotate the diagram with the conflict and the recommended alternative GPIO and include the change in the saved file's change log text box.

Use this skill whenever you need to take an existing draw.io wiring diagram, apply consistent presentation-level styling and safety annotations, save a cleared copy, export presentation-ready PNG/PDF files, and open the PNG for full-screen verification.
