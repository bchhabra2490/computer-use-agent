---
name: detect-usb-serial-bridges
description: >-
  Detects attached USB-to-serial bridge chips (CH340/CH341/CH910x, CP210x, FTDI, CDC devices) on a macOS laptop by inspecting the USB device tree, system_profiler output, serial device nodes, and loaded drivers. Use when you need a reproducible way to confirm whether a CH340/CP2102/CH9102-style adapter is present and to capture VID:PID and driver hints.
---

## Steps

1. Open Terminal (Spotlight: Cmd+Space → type Terminal → Enter).

2. Save a snapshot of the USB device tree and system USB report so you have files to inspect and attach if needed:

   - system_profiler SPUSBDataType > ~/Desktop/system_profiler_usb.txt
   - ioreg -p IOUSB -l > ~/Desktop/usb_ioreg.txt
   - ioreg -c IOSerialBSDClient -r -l > ~/Desktop/ioserial_clients.txt
   - ls -l /dev/cu.* /dev/tty.* 2>/dev/null > ~/Desktop/serial_nodes.txt
   - kextstat 2>/dev/null | egrep -i 'wch|ch34|silabs|cp210|ftdi|usbserial|usb-serial|ch91|ch910' > ~/Desktop/kext_hints.txt

   These commands create five files on the Desktop you can review or send for debugging.

3. Search the saved USB/ioreg output for known vendor strings and bridge keywords (common vendors: WCH 0x1A86, Silicon Labs 0x10C4, FTDI 0x0403):

   - grep -Ei 'CH340|CH341|CH910|CH9102|CP210|Silicon|Silabs|WCH|FTDI|USB Serial|usbmodem|CDC-ACM|Vendor ID|Product ID|idVendor|idProduct' ~/Desktop/usb_ioreg.txt || true
   - grep -Ei 'Vendor ID|Product ID|USB Product Name|USB Serial Number' ~/Desktop/system_profiler_usb.txt || true

   When present, system_profiler and ioreg will show lines with vendor/product IDs, e.g. "idVendor" = 0x1a86 and "idProduct" = 0x7523, or System Profiler lines like "Vendor ID: 0x1A86 (WCH)" and "Product ID: 0x7523".

4. Map serial device nodes onto the USB tree:

   - Open the ioserial_clients.txt produced above and look for properties named IOCalloutDevice or IOTTYDevice. These lines show the /dev/cu.* or /dev/tty.* node and are often nested under a USB device entry in ioreg output. Example grep:
     - grep -E 'IOCalloutDevice|IOTTYDevice|IORegistryEntryName' ~/Desktop/ioserial_clients.txt -n || true

   - If you see a serial node (e.g. /dev/cu.wchusbserialXXXX or /dev/cu.usbserial-XXXX), note nearby parent device properties (Vendor ID/Product ID) printed earlier in the same ioserial_clients.txt file.

5. List current serial nodes and their symlinks/owners to spot driver-provided names:

   - ls -l /dev/cu.* /dev/tty.* | egrep -i 'usb|wch|silab|cp210|ftdi|serial' || ls -l /dev/cu.* /dev/tty.* | sed -n '1,200p'

   Typical node names:
   - WCH/CH340 often shows cu.wchusbserial or cu.wchusbserialXXXX
   - Silicon Labs CP210x may show cu.SLAB_USBtoUART or cu.usbserial-*
   - FTDI chips often show cu.usbserial- or cu.usbserial-FTDI
   - Native CDC/ACM devices may appear as cu.usbmodem* or tty.usbmodem*

6. Inspect loaded kernel modules / driver hints:

   - kextstat | egrep -i 'wch|ch34|silabs|cp210|ftdi|usbserial|ch91|ch910' || true

   Note: modern macOS versions and Apple Silicon may use user-space drivers or DriverKit rather than kexts; absence of a kext does not prove absence of a device.

7. If you find a candidate, extract the VID:PID and a short report:

   - From system_profiler or ioreg, record Vendor ID (hex) and Product ID (hex) and any product/vendor strings. Example text to capture:
     - <Device Name> — Vendor ID: 0x1A86 (WCH) — Product ID: 0x7523 — Serial: <serial if present> — Node(s): /dev/cu.wchusbserialXXXX

   - Save a one-line summary to the Desktop:
     - echo '<one-line summary>' > ~/Desktop/usb-serial-summary.txt

8. If nothing matching CH340/CP210/CH910 appears:

   - Re-check physical connections: use a different cable and connect directly to the Mac (avoid unpowered hubs). Some cheap cables are power-only.
   - Open System Information GUI (Apple menu → About This Mac → System Report → USB) and see whether the device appears in the USB device tree.
   - Try a different OS or device (phone/computer) to verify the adapter works elsewhere.

## Tips

- Known vendor IDs that are useful to search for:
  - WCH (CH340/CH910 family): 0x1A86
  - Silicon Labs (CP210x): 0x10C4
  - FTDI: 0x0403

- Search keywords: CH340, CH341, CH910, CP210, CP2102, Silabs, Silicon Labs, WCH, FTDI, usbserial, usbmodem, CDC-ACM, SLAB.

- If you need a portable one-liner to show likely USB serial matches quickly:

  ioreg -p IOUSB -l 2>/dev/null | grep -Ei -B4 -A8 'CH340|CH341|CH910|CP210|Silab|WCH|FTDI|usbserial|usbmodem|Vendor ID|Product ID' || true

- If the adapter has no USB-level presence (no VID:PID shown in system reports), it may be a power-only cable or the adapter is faulty.

- For troubleshooting driver issues: check the vendor website (Silicon Labs, WCH) for macOS drivers or updated DriverKit packages; note that many modern macOS versions don't require third-party kernel extensions for common bridges.

- Keep the Desktop log files (system_profiler_usb.txt, usb_ioreg.txt, ioserial_clients.txt, serial_nodes.txt, kext_hints.txt) when asking for help — they contain the exact strings experts need to diagnose missing VID:PID or naming issues.
