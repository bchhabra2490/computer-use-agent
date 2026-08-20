---
name: network-printer-connect-and-print
description: >-
  Finds an AirPrint/IPP network printer on the LAN from a Mac, adds or selects the printer in System Settings (Printers & Scanners), and prints a specified page or document. Use when you need a repeatable way to connect to a network printer and send a test or user-supplied print job.
---

## Steps

1. Verify whether any printer is already installed and visible to CUPS:
   - Open Terminal and run:
     - lpstat -p -d
     - lpstat -v
   - If you see a device URI containing dnssd:// or ipp:// that matches the printer model, note the printer name shown by lpstat and skip to step 5.

2. Discover the printer on the local network (Bonjour/IPP/AirPrint):
   - In Terminal run:
     - dns-sd -B _ipp._tcp local
     - dns-sd -B _printer._tcp local
   - Or list system-known devices:
     - arp -a
     - lpinfo -v
   - Use your router's device list (web UI) to find the printer IP if dns-sd doesn't show it.

3. Add the printer in System Settings → Printers & Scanners (if it is not already installed):
   - Open System Settings, go to Printers & Scanners.
   - Click the + (Add) button.
   - In the Default/Bonjour list, wait a few seconds for the printer entry (it may appear as "HP DeskJet …" or similar). Select it and click Add.
   - If the printer does not appear in the Bonjour list, add by IP:
     - Choose the IP or IPP entry in the Add dialog (or "IP" tab).
     - Protocol: IPP (or choose AirPrint/HP Jetdirect if available).
     - Address: enter the printer IP (e.g., 192.168.1.45) or hostname.
     - Queue: leave blank or use /ipp/print if required by the printer docs.
     - Give it a Name and Location, confirm the driver shows as "AirPrint" (preferred) or a generic driver, then click Add.

4. Confirm the printer is listed and online:
   - Back in Printers & Scanners confirm the new printer appears and its status is Idle/Ready.
   - In Terminal you can verify with:
     - lpstat -p -d
     - lpinfo -v | grep -i "hp\|deskjet\|ipp\|dnssd"

5. Print the page or document the user provided:
   - Open the document or the web page in the desired app (e.g., Google Chrome, Preview, or Safari).
   - Press Cmd+P to open the Print dialog.
   - In Destination/Printer choose the newly-added HP DeskJet (it may show as "HP_DeskJet_2700_series…" or similar).
   - Confirm Pages/Copies/Orientation as required, then click the blue Print button.

6. Monitor and troubleshoot the print job from Terminal if needed:
   - Check queue and recent jobs:
     - lpstat -W not-completed -o
     - lpstat -W completed -o | tail -n 10
   - To cancel a job:
     - cancel <job-id>  (job-id format shown by lpstat, e.g., HP_DeskJet_2700-66)

## Tips

- Prefer AirPrint (Bonjour/IPP) driver entries — they usually work without vendor driver installs.
- If the printer never appears in Bonjour, ensure the Mac and printer are on the same Wi‑Fi network and that the printer's network has Bonjour enabled (some guest networks block mDNS).
- If connecting by IP, try protocol IPP with path /ipp/print or use the printer's web admin page to confirm the correct printing URI.
- For stubborn cases use the CUPS web interface (http://localhost:631) to add/manage printers and view detailed job logs (you may need to enable CUPS admin access).
- If printing repeatedly from a browser, verify the browser's print preview destination matches the system setting and that any browser print-to-PDF override is turned off.
- Common recovery: open System Settings → Printers & Scanners, right-click (or Control-click) the printer and choose Reset Printer System (this removes all printers) only as a last resort.
