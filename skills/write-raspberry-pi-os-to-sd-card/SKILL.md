---
name: write-raspberry-pi-os-to-sd-card
description: >-
  Uses the Raspberry Pi Imager on macOS (with a Terminal fallback) to download and write the latest Raspberry Pi OS image to a selected attached SD card, handling admin authentication, verification, and safe ejection. Use when the user needs a reproducible, safe procedure to image an SD card for Raspberry Pi.
---

## Steps

1. Confirm the SD card reader is connected and the SD card is inserted. In Finder, check the sidebar or open Terminal and run `diskutil list` to confirm a removable volume appears (note the disk identifier, e.g. /dev/disk2).

2. Open Raspberry Pi Imager:
   - Press Cmd+Space, type "Raspberry Pi Imager", and press Return. If the app is not installed, open a browser and download it from https://www.raspberrypi.org/software/ then install it and reopen.

3. If you see a crash or "quit unexpectedly" dialog, click the app's "Reopen" button. If the app still misbehaves:
   - Open Activity Monitor (Cmd+Space → "Activity Monitor" → Return), search for "rpi-imager" or "raspberry", select it and click the Stop (×) button → Force Quit. Then relaunch Raspberry Pi Imager.

4. In Raspberry Pi Imager, choose the OS:
   - Click "CHOOSE OS" → select "Raspberry Pi OS (Other)" or the top-level "Raspberry Pi OS (32-bit)" / "Recommended" entry (the UI wording may vary). The imager will download the selected image if it's not cached.

5. Choose the storage device:
   - Click "CHOOSE STORAGE" and carefully select the SD card device that matches the capacity and the device name you noted earlier. Double-check the size and label — selecting the wrong device will overwrite it.

6. Start the write:
   - Click "WRITE". macOS will prompt for administrator access to write to the raw device. Enter your macOS admin password when requested. If prompted to allow the app to access removable volumes, allow it.

7. Let the imager run its write and verify cycle. The imager shows a progress bar and will report when verify completes. Do not eject the card while writing or verifying.

8. When the imager finishes it will normally eject the SD card for you and report success. Confirm the SD card is no longer mounted in Finder or run `diskutil list` again to verify.

9. If the imager fails to write or verify:
   - Reinsert the SD card/reader so it remounts. Try again from step 2.
   - If persistent crashes occur, quit the imager, restart the Mac or reconnect the reader on a different USB port, and retry.

10. Optional: If you prefer a Terminal fallback (advanced users only):
   - Download the Raspberry Pi OS image (.img or .zip) and expand it to get the .img file.
   - In Terminal run `diskutil list` and identify the SD card device node (e.g. /dev/disk2).
   - Unmount the disk: `diskutil unmountDisk /dev/diskN` (replace diskN).
   - Write using the raw device for speed (double-check the device): `sudo dd if=/path/to/raspios.img of=/dev/rdiskN bs=4m conv=sync`  (replace paths and rdiskN). On completion run `sync` and then `diskutil eject /dev/diskN`.
   - WARNING: `dd` will irreversibly overwrite the selected device. Verify the correct /dev/diskN before running and back up any needed data.

## Tips

- Always confirm the device size and label in imager or from `diskutil list` before writing to avoid overwriting the wrong disk.
- If Raspberry Pi Imager repeatedly crashes, reinstall it from the official site and try a different USB card reader or port.
- Use the imager's built-in verify step for a safer, automated check. If using `dd`, prefer `/dev/rdiskN` (raw) for speed and allow `sync` to finish before ejecting.
- If macOS requests permission for removable volumes or needs Full Disk Access for the imager, allow it in System Settings → Privacy & Security when prompted.
- If you need progress while using Terminal and `dd` on macOS, consider installing `pv` via Homebrew and streaming through it, or use `dd` variants that support `status=progress` (availability may vary).
- If the disk shows "Disk Not Ejected Properly" alerts, remove and reinsert the card and confirm it mounts before retrying.

Use this skill whenever you need a reproducible, safe procedure to download and write Raspberry Pi OS to an attached SD card on macOS. Prompt the user for admin password confirmation and for final confirmation of the target device when the disk selection could be ambiguous.
