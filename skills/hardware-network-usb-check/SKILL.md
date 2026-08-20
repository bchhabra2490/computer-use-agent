---
name: hardware-network-usb-check
description: >-
  Performs a quick, repeatable check on macOS for local hardware: scans the LAN ARP table for device MAC prefixes (e.g., Raspberry Pi), tests MQTT broker reachability (and tries the project's MCP helper if available), lists USB/serial devices and Arduino-detected boards, captures a screenshot and saves a short log. Use this when you want a concise sanity check of networked and USB-attached hardware before further steps.
---

## Steps

1. Open a Terminal window (Spotlight: Cmd+Space, type Terminal, Enter).

2. (Optional) Capture the current desktop for record: press Cmd+Shift+3. The screenshot will be saved to the Desktop.

3. Make a timestamped log file on the Desktop so all outputs are saved for later inspection:

   logfile=~/Desktop/hardware-check-$(date +%Y%m%d-%H%M%S).txt

4. Check the local ARP table and append to the log (shows IP ↔ MAC mappings):

   echo "--- arp -a ---" >> "$logfile"; arp -a | tee -a "$logfile"

   - Look for MAC prefixes (first three octets) that indicate Raspberry Pi or other known devices. Common Raspberry Pi OUIs include: b8:27:eb and dc:a6:32 (compare the first three octets of any MAC). If you see an entry like "(192.168.1.69) at b8:27:eb:xx:xx:xx", that indicates a Pi on the LAN.

5. If ARP doesn't show expected devices, rerun ARP after contacting the device or router, or run a host discovery if you have nmap installed (optional):

   nmap -sn 192.168.1.0/24 | tee -a "$logfile"

   (Only run nmap if you have it installed and are permitted to scan the network.)

6. Test MQTT broker reachability (checks TCP connect to default MQTT port 1883):

   echo "--- mqtt port test ---" >> "$logfile"; nc -vz 127.0.0.1 1883 2>&1 | tee -a "$logfile"

   - A successful connect will report succeeded/open. A refusal/time-out indicates the broker is not reachable on localhost:1883.

7. If your project provides an MCP helper (the agent previously called an mcp helper), try the environment-specific call used by your project. Example (adjust to your repo/tooling):

   echo "--- mcp helper (if available) ---" >> "$logfile"
   # Replace the command below with your project's mcp invocation if different
   mcp_call --server hardware --tool list_devices 2>&1 | tee -a "$logfile" || echo "mcp helper failed or not available" | tee -a "$logfile"

   - If this fails with "broker_unreachable" or similar, include that JSON in the log for debugging.

8. List macOS serial/USB device nodes and save to the log (quick check for USB-serial adapters and boards):

   echo "--- /dev serial nodes ---" >> "$logfile"; ls /dev/tty.* /dev/cu.* 2>/dev/null | tee -a "$logfile"

   - Typical names: /dev/tty.usbserial-*, /dev/tty.usbmodem*, /dev/cu.usbserial-*, etc.

9. Run arduino-cli detection (if you use Arduino tooling) and append its output:

   echo "--- arduino-cli board list ---" >> "$logfile"; arduino-cli board list 2>&1 | tee -a "$logfile"

   - If arduino-cli is not installed, the command will fail; note that in the log and skip.

10. (Optional) For a more detailed USB device tree, append system_profiler output:

   echo "--- USB devices (system_profiler) ---" >> "$logfile"; system_profiler SPUSBDataType 2>&1 | tee -a "$logfile"

11. Review the log on the Desktop (open with TextEdit) and note:

   - Any ARP lines showing Raspberry Pi OUIs (b8:27:eb, dc:a6:32, etc.) and their IPs.
   - Whether the MQTT broker port test succeeded or failed.
   - Whether mcp helper returned device JSON or an error like broker_unreachable.
   - Whether arduino-cli found any boards and what port names it reported.

12. Summarize in one line and copy to clipboard if desired (example):

   summary="$(grep -E "b8:27:eb|dc:a6:32|broker_unreachable|arduino-cli|tty\.|cu\." -m 5 "$logfile" | sed -n '1,5p')"
   echo "Hardware check saved to $logfile"; echo "$summary"

## Tips

- Prefer using the log file on the Desktop so you can attach it to bug reports or share with teammates.
- If `nc` is not available use `telnet 127.0.0.1 1883` as a fallback to test port connectivity.
- If you need to identify unknown MAC OUIs beyond the common Raspberry Pi prefixes, paste the MAC into an OUI lookup service (e.g., https://maclookup.app) or use `curl` against an OUI API.
- For ESP/ESP32 boards, use the esp32-probe-and-identify skill (already available) for a deeper serial-probing workflow that runs esptool across candidate ports.
- Avoid repeating long network-wide scans on networks you don't control — prefer targeted checks when possible.

This procedure yields a short, reproducible record of network/USB hardware presence and broker reachability that you can run whenever you need a quick sanity check.
