---
name: create-bom-and-drawio-diagram
description: >-
  Creates a project-local Bill of Materials (Markdown and CSV) and an editable diagrams.net (.drawio) wiring/pinout diagram saved into a specified project folder on macOS. Use when you have a hardware project directory and want both a written BOM plus a reusable visual wiring diagram stored alongside source files.
---

## Steps

1. Identify the target project folder
   - In Finder or Terminal, locate the project folder (example: ~/Desktop/projects/Pomodoro_Clock). Note the full path.

2. Create initial BOM files in the project folder
   - Open Terminal and change to the project folder:
     cd "~/Desktop/projects/Pomodoro_Clock"
   - Create a starter Markdown BOM that the user can refine. Example command (overwrites if present):
     cat > BOM.md <<'EOF'
     # Pomodoro Clock — Bill of Materials (BOM)

     ## Required parts

     | Ref. | Qty. | Item / specification | Purpose | Connection / notes |
     |---|---:|---|---|---|
     | U1 | 1 | ESP32-C3 Super Mini development board | Main controller / USB power | I2C (SDA,SCL), 3.3V, GND, buzzer pin |
     | U2 | 1 | MPU6050 (3.3V) | Orientation sensor | I2C 0x68 — SDA, SCL; VCC=3.3V, GND |
     | U3 | 1 | 128x64 OLED (I2C, 3.3V) | Display | I2C — SDA, SCL; VCC=3.3V, GND |
     | BZ1 | 1 | Passive buzzer (or piezo) | Sound notifications | GPIO -> series resistor -> buzzer or driver |
     | J1 | 1 | USB-C (or micro-USB) cable / power source | Power and programming | USB 5V -> regulator/board USB input |

     ## Optional parts

     | Ref. | Qty. | Item |
     |---|---:|---|
     | D1 | 1 | NPN transistor or MOSFET (buzzer driver) |
     | R1 | 1 | 100–220 ohm resistor (buzzer current limit) |

     EOF

   - Create a CSV copy for tooling/parts import:
     cat > BOM.csv <<'EOF'
     Ref,Qty,Item,Purpose,Connections/Notes
     U1,1,ESP32-C3 Super Mini development board,Controller,I2C SDA/SCL;3.3V;GND;buzzer GPIO
     U2,1,MPU6050 3.3V,Orientation sensor,I2C address 0x68;VCC 3.3V;GND
     U3,1,128x64 OLED I2C,Display,I2C SDA/SCL;VCC 3.3V;GND
     BZ1,1,Passive buzzer,Sound output,GPIO via resistor or driver
     J1,1,USB cable/adapter,Power/Programming,USB power to board
     EOF

3. Populate or refine BOM from source files
   - If the project already contains README.md or source files (e.g., .ino) with parts listed, open them in an editor to copy exact part numbers/footprints into BOM.md and BOM.csv.
   - Example: open README.md or Pomodoro_Clock.ino in your editor (VS Code, TextEdit) and update BOM entries to match exact modules (e.g., board part numbers, display module SKU, MPU module breakout SKU).

4. Create the diagrams.net (.drawio) wiring/pinout diagram and save into the project folder
   - Open Google Chrome (or your preferred browser).
   - Go to https://app.diagrams.net/ .
   - When prompted for storage location, choose "Device" so you can save directly into the project folder. If the app asks for permissions, allow it to save files.
   - Use the file picker to navigate to the project folder (~/Desktop/projects/Pomodoro_Clock) and create a new diagram named Pomodoro_Clock.drawio.

5. Build the diagram content (recommended, step-by-step)
   - Add one labeled rectangle/icon per component: ESP32-C3, MPU6050, OLED, Buzzer, USB Power / connector. Use the left shapes palette (rectangles, device icons) to place elements.
   - For each component, add a small text box listing pins used (example for ESP32-C3):
     - 3V3 (VCC)
     - GND
     - SDA (I2C)
     - SCL (I2C)
     - GPIO_BZ (buzzer output)
   - For MPU6050: show pins VCC=3.3V, GND, SDA, SCL, AD0 if used.
   - For OLED: show VCC=3.3V, GND, SDA, SCL.
   - Draw color-coded connector lines for power (red for 3.3V), ground (black), and I2C (green/blue for SDA/SCL). Use connector arrows or simple lines and label them (SDA, SCL, 3.3V, GND, BZ_PIN).
   - Add pin numbers/labels on the ESP32-C3 box that match the physical dev board pin names used by the firmware (e.g., if code uses GPIO7 as SDA, label that mapping: SDA -> GPIO7). Pull the exact pin mappings from your source code before labeling.
   - Group each component's shape + pin-list text into a single grouped object for easier movement.
   - Add a small note or table on the diagram listing I2C address (e.g., MPU6050 0x68) and any jumpers/AD0 settings.

6. Save and export
   - Save the diagram: File → Save (this writes Pomodoro_Clock.drawio into the project folder)
   - Export a PNG for documentation: File → Export as → PNG (check "Include a copy of the .drawio XML" if desired) and save the PNG into the same project folder as Pomodoro_Clock.png.
   - Optionally export PDF: File → Export as → PDF → save to project folder.

7. Verify files in the project folder
   - In Terminal:
     ls -l "~/Desktop/projects/Pomodoro_Clock" | egrep "BOM|Pomodoro_Clock.*(drawio|png|pdf|csv)" || true
   - Open BOM.md and the exported PNG to visually verify contents.

## Tips

- Use exact pin names from your source code: before labeling pins in the diagram, open Pomodoro_Clock.ino and find the pin definitions so the diagram matches firmware.
- Save frequently in diagrams.net; keep the .drawio source in the project folder so the diagram is editable later.
- If diagrams.net can't directly save to the project folder due to browser sandboxing, save to Downloads first and then move the .drawio/.png into the project folder with mv.
- Keep the BOM CSV simple (Ref,Qty,Item,Notes) so it can be imported into spreadsheets or ordering systems.
- If the project uses alternate power rails (5V vs 3.3V) or a regulator, show the regulator block and label input/output voltages.
- For more PCB-like pinouts, consider using the diagramsnet-create-pcb-pinout-from-image skill as a follow-up to convert a photo or screenshot into a pinout diagram.

Use this skill whenever you want a repeatable, project-local BOM plus an editable diagrams.net wiring/pinout diagram saved with your project files.
