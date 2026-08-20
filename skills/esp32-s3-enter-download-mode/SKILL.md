---
name: esp32-s3-enter-download-mode
description: >-
  Provides a repeatable, safe procedure for putting an ESP32‑S3 development board into the serial bootloader (download) mode on a macOS desktop: identify pins, use a BOOT/GPIO0-to-GND jumper and RESET/EN toggle, and verify the board appears as a USB serial device and responds to esptool.
---

## Steps

1. Prepare the Mac terminal and tools
   - Open Terminal.app.
   - Run a quick port inventory (to see the new port appear after connecting the board):
     - ls -1 /dev/cu.* 2>/dev/null || true
     - python3 -m serial.tools.list_ports -v 2>&1 || true
   - If you will verify bootloader with esptool and it is not installed, install it:
     - pip3 install --user esptool
     - (If pip3 is not available, install Python via Homebrew or the official installer.)

2. Identify the correct pins on the carrier/dev board (do this with the board UNPOWERED)
   - Locate BOOT (often labeled BOOT or GPIO0), GND (ground), and RESET or EN on the carrier/DevKit silkscreen.
   - If pin labels are not clear, consult the board's silkscreen/photo or the board's schematic/quickstart page. Do not assume chip pinout locations—use the carrier board labels.

3. Power‑off and prepare a jumper
   - Unplug the USB cable or otherwise ensure the board is not powered before moving or adding a jumper.
   - Place a jumper or short a wire between BOOT (GPIO0) and GND so GPIO0 is held low when the board is powered/reset.

4. Apply power and toggle RESET/EN to enter bootloader
   - With BOOT tied to GND, connect the USB cable to power the board (or apply the board's recommended VBUS/5V input). Wait a second.
   - Press and release RESET (sometimes labeled EN) once while BOOT remains grounded. (Alternative: press RESET, release while BOOT still low.)
   - After the RESET cycle, you may remove the BOOT-to-GND jumper (some boards require leaving it for the entire connection; if unsure, leave it until verification succeeds then remove).

5. Verify the board appears as a USB serial device on macOS
   - Re-run the port inventory and look for a newly appeared port (example: /dev/cu.SLAB_USBtoUART or /dev/cu.usbserial-XXXX):
     - ls -1 /dev/cu.* 2>/dev/null || true
     - python3 -m serial.tools.list_ports -v 2>&1 || true
   - If no new port appears, try unplugging and re-plugging the USB data cable once and repeat the listing. If still not visible, check cables or USB drivers for the USB‑to‑UART chip on your board (CP210x, CH340, FTDI, etc.).

6. Confirm bootloader responsiveness with esptool
   - Identify the new device name (replace <port> below with the actual /dev/cu.* path you found).
   - Try to query the chip id using esptool:
     - esptool.py --port <port> chip_id
     - If esptool.py is not on PATH, try: python3 -m esptool --port <port> chip_id
   - A successful bootloader response will report an ESP32‑S3 chip/chip id and indicate communication over the serial/USB port.

7. If verification fails
   - Reconfirm you held BOOT/GPIO0 low during the reset. Repeat steps 3–6.
   - Try a different USB cable or USB port (prefer a full‑speed USB data cable, not a power‑only cable).
   - Check for any required vendor drivers (CP210x/CH340) for older macOS versions.

## Tips

- Safety: always power off or unplug before moving jumpers. Never short VCC to GND. Use the board's labeled power pin (5V/VBUS or 3V3) only as specified by the carrier board documentation.
- Board variations: exact silkscreen names and pin locations vary by carrier board. This procedure describes the generic manual BOOT/GPIO0→GND + RESET/EN toggle method used by ESP32 dev boards, but pin locations are board dependent.
- Auto‑enter bootloader: many modern ESP32 DevKits use the USB‑to‑UART chip to toggle DTR/RTS automatically; manual jumper/reset is the universal fallback when auto‑boot fails.
- Use the existing esp32-probe-and-identify skill after the board is detected to run a standard identification sweep and save results.
- If the chip still isn't detected at all (no USB vendor/product in ioreg/system_profiler), inspect the board power circuit and data lines, and try a different host USB port/hub.
