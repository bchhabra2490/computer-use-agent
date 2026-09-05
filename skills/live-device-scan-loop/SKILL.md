---
name: live-device-scan-loop
description: >-
  Runs a repeatable live scan on macOS that logs serial ports, arduino-cli board list, and USB device info while taking a screenshot each iteration; saves timestamped logs and screenshots to the Desktop for hardware debugging (useful when holding BOOT/RESET or repeating connect/disconnect cycles).
---

## Steps

1. Prepare the board and Mac
   - Plug the board into the Mac USB port you will exercise. Decide which display should show Terminal for screenshots (move Terminal window to that display).
   - If the test requires the user to hold buttons (BOOT+RESET), be ready to hold them and keep them held for the duration of the run.

2. Open Terminal
   - Open Terminal (Spotlight: Cmd+Space → type Terminal → Enter) or run: open -a Terminal

3. Create a timestamped output folder on the Desktop
   - In Terminal paste and run:
     OUTDIR=~/Desktop/live-device-scan-$(date '+%Y%m%d_%H%M%S')
     mkdir -p "$OUTDIR"
     LOG="$OUTDIR/scan.log"

4. Run the 10-iteration live scan loop (captures logs + screenshots)
   - Copy and paste the following into Terminal and press Enter. This runs 10 iterations, appends human-readable output to a log, and saves a PNG screenshot each iteration in the folder you created.

     for i in $(seq 1 10); do
       printf '\n===== LIVE DEVICE SCAN %s/10 =====\n' "$i" | tee -a "$LOG"
       date '+%Y-%m-%d %H:%M:%S' | tee -a "$LOG"
       echo '-- Serial ports --' | tee -a "$LOG"
       ls -1 /dev/cu.* 2>/dev/null | tee -a "$LOG" || echo 'none' | tee -a "$LOG"
       echo '-- Arduino board scan --' | tee -a "$LOG"
       arduino-cli board list 2>&1 | tee -a "$LOG"
       echo '-- USB devices --' | tee -a "$LOG"
       system_profiler SPUSBDataType 2>/dev/null | grep -E 'Product ID:|Vendor ID:|Manufacturer:|Serial Number:' | head -40 | tee -a "$LOG" || true
       screencapture -x "$OUTDIR/scan-$i.png"
       sleep 2
     done

   - While the loop runs, hold BOOT+RESET (or perform the hardware action) as required. Keep the Terminal window visible on the chosen display so screenshots show the Terminal output.

5. Verify results
   - After the loop ends, list the output folder:
     ls -l "$OUTDIR"
   - Open the log and at least one screenshot to confirm iterations were captured:
     open "$LOG"
     open "$OUTDIR/scan-1.png"

6. (Optional) Archive the results
   - To create a compressed archive for sharing:
     cd ~/Desktop
     tar -czf "$(basename "$OUTDIR").tar.gz" "$(basename "$OUTDIR")"

## Tips

- Ensure arduino-cli is installed and on your PATH (run arduino-cli version). If not installed, install via Homebrew: brew install arduino-cli or follow arduino-cli docs.
- If you prefer full-screen screenshots or a specific region, adjust the screencapture command. -x saves without UI noise; to capture only the Terminal window you can use screencapture -l <windowID> if you first obtain the Terminal window id.
- Adjust the iteration count by replacing `seq 1 10` with `seq 1 N` or use `while true` for indefinite runs (but avoid very long sleeps).
- Keep sleep short (1–3s) so iterations are frequent but still let the OS update device lists. Avoid very long sleeps that block interactive debugging.
- If system_profiler is slow on your machine, reduce how much it prints (the grep | head in the loop already limits output). If you need more USB detail, run system_profiler once outside the loop to collect full output.
- If you prefer per-iteration terminal screenshots without screencapture, you can redirect each loop iteration to a separate text file (e.g., "$OUTDIR/scan-$i.txt") instead of or in addition to the PNGs.

Use this procedure whenever you need a reproducible, timestamped live scan of serial ports, Arduino board detection, and USB device metadata while performing a physical button-hold or repeated connect/disconnect cycle.
