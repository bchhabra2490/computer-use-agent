---
name: check-printer-job-status
description: >-
  Checks the status and page progress of a print job for a specified printer on macOS, using Terminal (lpstat/lpq) and the system Print Queue or CUPS web interface when needed. Use when you need a reproducible way to determine whether a job is queued, printing, completed, or failed and how many pages have printed.
---

## Steps

1. Open Terminal
   - Press Command+Space, type Terminal, press Return.

2. List all active and queued jobs
   - Run:
     lpstat -W all -o
   - This prints one line per job. Each line starts with the printer name and includes job id and user. If many jobs appear, narrow to your printer:
     lpstat -W all -o <printer_name>
   - If no lines appear, try checking recently completed jobs:
     lpstat -W completed -o

3. Identify the job of interest
   - Note the full job identifier or the printer-specific job token shown in the lpstat output (it will look like <printer>_<something> or a numeric job id). Also note any displayed job title (document name) and owner.

4. Get detailed status for that job
   - Run a long listing for the job (replace <job> with the exact job token from step 3):
     lpstat -l -W all -o "<job>"
   - Read the output fields. Useful fields to check:
     - "job-printer-state-message" or "printer-state-message" — human-readable printer messages (paper out, paused, printing page X, etc.)
     - "job-originating-user-name" — who submitted it
     - timestamps — when the job started/queued

5. Check the printer queue progress view
   - Run lpq for a quick progress view:
     lpq -P "<printer_name>"
   - lpq may show the active job and sometimes page progress or which page is currently being processed. If a job is actively printing, lpq often marks it as 'active' or shows the job's rank and size.

6. (GUI alternative) Open the Print Queue
   - Open System Settings → Printers & Scanners.
   - Select the target printer and click "Open Print Queue…" (or right-click the printer and choose Open Print Queue).
   - In the queue window, read the job row for status (Queued, Printing, Completed, Failed) and any page/progress indicator shown.

7. (CUPS web UI fallback) If Terminal/Settings don’t show enough detail, open the CUPS web interface in a browser:
   - Open http://localhost:631/jobs and locate the job by printer or owner. The CUPS UI often shows per-job status messages and page counts.

8. Interpret and report
   - If lpstat / lpq / Print Queue show the job as active/processing or include a message like "page N of M" or "started page N", report "printing" and compute pages printed as N-1 printed fully and page N in progress.
   - If the job appears in the queue but not active, report "queued".
   - If it appears under completed (lpstat -W completed -o) or the Print Queue shows "Completed", report "completed" and the total pages (if available).
   - If messages show errors (paused, canceled, error, filter failed), report "failed" with the printer-state-message text.

## Tips

- Exact printer name is case-sensitive for lpstat/lpq; copy it from lpstat -p or lpstat -W all -o output.
- To list available printers and default printer: lpstat -p -d
- If you need a numeric job id only, lpstat -o output often contains a numeric id that can be used in commands.
- No elevated privileges are normally required to view your own jobs. If a job was sent by another user or by the system, you may need admin rights to see details.
- For scripted checks, parse lpstat -W all -o and lpstat -l -W all -o <job> programmatically; prefer the long lpstat output or the CUPS jobs page for reliable human-readable messages.
- Avoid relying on lpstat output formats that vary across macOS/CUPS versions; when in doubt, confirm with the Print Queue GUI or CUPS web UI.
