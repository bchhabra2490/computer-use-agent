---
name: esp32-probe-and-identify
description: >-
  Probes a macOS machine for an attached ESP32-family board: gathers USB device info, lists serial devices, installs/verifies esptool, runs esptool chip_id across candidate ports, and records results. Use when you need a repeatable check to detect and identify an ESP32 (or find why it is not responding).
---

## Steps

1. Open Terminal and confirm Python 3 is available:
   - python3 --version

2. Collect USB device information (captures USB-serial adapter and vendor strings):
   - system_profiler SPUSBDataType 2>/dev/null | sed -n '1,240p' > ~/Desktop/esp-usb-info.txt
   - grep -i -E 'esp|cp210|ch340|wch|ftdi|usb serial|silicon' ~/Desktop/esp-usb-info.txt || true

3. List macOS serial device nodes and save listing:
   - ls -l /dev/cu.* /dev/tty.* 2>/dev/null | sed -n '1,200p' > ~/Desktop/esp-serial-list.txt

4. Install or ensure esptool is available (pip install is safe on macOS):
   - python3 -m pip install --user esptool
   - command -v esptool || command -v esptool.py || python3 -m esptool version 2>/dev/null || true

5. Probe candidate serial ports with esptool's chip_id command. Run this loop (it skips non-existent names):
   - for p in /dev/cu.usbserial* /dev/cu.SLAB_USBtoUART* /dev/cu.wchusbserial* /dev/cu.usbmodem* /dev/cu.*; do
       [ -e "$p" ] || continue
       echo "===== $p ====="
       python3 -m esptool --port "$p" --timeout 3 chip_id 2>&1 | sed -n '1,40p'
     done 2>&1 | tee ~/Desktop/esp-probe-output.txt

   Notes: the glob list covers common adapter names; the command writes a combined probe log to ~/Desktop/esp-probe-output.txt for review.

6. If no ESP responds, try entering the ESP bootloader (many boards require GPIO0/BOOT held low during reset):
   - Power-cycle or press RESET while holding the BOOT (sometimes labelled IO0) button, then immediately re-run the probe loop above.
   - Some devboards require a short press sequence (hold BOOT, press RESET, release RESET, then release BOOT).

7. If still no response, try these troubleshooting steps and re-run the probe loop each time:
   - Use a different USB cable (confirm it is a data-capable cable, not power-only).
   - Try a different Mac USB port or a powered USB hub.
   - Confirm the board has power LEDs and that the USB-serial chip (CP210x/CH340/FTDI) appears in the system_profiler output from step 2.
   - If the board has removable headers or soldered pins, ensure the USB connector is seated correctly.

8. When a board responds, note the chip_id output and save additional esptool info:
   - python3 -m esptool --port /dev/cu.xxx chip_id  (replace with the responding device node)
   - python3 -m esptool --port /dev/cu.xxx flash_id
   - Save those outputs to ~/Desktop/esp-identified-<device>.txt

9. Collect artifacts for later analysis or bug reports (all files on Desktop):
   - ~/Desktop/esp-usb-info.txt
   - ~/Desktop/esp-serial-list.txt
   - ~/Desktop/esp-probe-output.txt
   - any esp-identified-*.txt files

## Tips

- Many ESP32 boards will only reply to esptool when in the chip's serial bootloader; putting the board into the correct boot mode is a common requirement.
- If macOS denies access to a USB adapter or the adapter driver is missing, look for vendor drivers (CP210x, CH340) and prefer drivers provided by the vendor or use built-in serial drivers when possible.
- Avoid using GUI tools or system sleeps; focus on capturing command output to Desktop files so results are reproducible and shareable.
- If you need to probe many machines, wrap the probe loop into a short shell script that timestamps logs: e.g. LOG=~/Desktop/esp-probe-$(date -u +%Y%m%dT%H%M%SZ).txt
- Do not rely on cloud/hardware brokers; this skill is for direct local USB/serial probing on macOS.
