---
name: contain-remove-terminal-dropper
description: >-
  Contains and removes a malicious dropper installed via a terminal command (curl/wget|sh -c) on macOS: inspects shell history and temporary downloads, identifies the dropper binary/bundle and persistence (LaunchAgents/Daemons, cron, login items), unloads and disables persistence, terminates processes, creates a quarantine bundle with checksums and metadata, safely removes artifacts, and verifies no active processes or network connections remain. Use when a user discovers a suspicious terminal command that downloaded and executed a payload and wants a reproducible containment+removal procedure.
---

## Steps

1. Prepare an evidence/quarantine folder (do not delete anything yet):
   - mkdir -p "$HOME/Desktop/malware-quarantine-$(date +%Y%m%d-%H%M%S)"
   - cd "$HOME/Desktop" and note the full path for later.

2. Find the suspicious command and related artifacts in shell history:
   - Inspect shells: tail -n 200 ~/.zsh_history ~/.bash_history 2>/dev/null | egrep -i 'curl|wget|sh -c|bash -c|chmod +x' || true
   - Copy the exact command text and note the remote URL(s) and target filenames/paths.

3. Identify downloaded files, extracted bundles, and common temp locations:
   - Check obvious temp and download locations (do not execute files):
     - ls -la /var/tmp /tmp "$HOME/Downloads" "$HOME/.cache" "$TMPDIR" 2>/dev/null
     - find /var/tmp "$HOME/Downloads" "$TMPDIR" -maxdepth 2 -type f -iname '*driver*' -o -iname '*cam*' -o -iname '*update*' -mmin -1440 2>/dev/null | head -200
   - Note files matching the URL-filename or suspicious names (e.g., camapp, cameradriver.sh).

4. Inspect possible persistence points (do not remove yet):
   - User LaunchAgents: ls -l "$HOME/Library/LaunchAgents" | egrep -i 'cam|driver|update|falcon|camapp' || true
   - System LaunchAgents/Daemons (may need sudo): ls -l /Library/LaunchAgents /Library/LaunchDaemons 2>/dev/null | egrep -i 'cam|driver|update|falcon|camapp' || true
   - crontab: crontab -l 2>/dev/null || true
   - login items and ~/Library/Application Support for unexpected bundles.
   - Grep launch agents for indicators: grep -RIlE 'camapp|cameradriver|camdriver|falconxco|<suspicious-domain>' "$HOME/Library/LaunchAgents" /Library/LaunchAgents /Library/LaunchDaemons 2>/dev/null || true

5. Collect metadata and create checksums before touching files:
   - For each suspect file path, run: sha256sum /path/to/file 2>/dev/null || shasum -a 256 /path/to/file
   - Save file listings and checksums to the quarantine folder: 
     - ls -l /path/to/suspect > "$QUARANTINE/paths.txt" and append shasums to "$QUARANTINE/checksums.txt".
   - Copy suspicious files (do not run them) into the quarantine folder using cp --preserve=timestamps or ditto on macOS:
     - cp -p /var/tmp/cameradriver.sh "$QUARANTINE/" || ditto /var/tmp/cameradriver.sh "$QUARANTINE/"
   - Save the exact shell history excerpt and the original suspicious command into "$QUARANTINE/command.txt".

6. Contain persistence (unload/disable) — user-level first (no reboot):
   - For a user LaunchAgent plist (example name com.camdriver.update.plist):
     - launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.camdriver.update.plist" 2>/dev/null || launchctl remove com.camdriver.update 2>/dev/null || true
     - mv "$HOME/Library/LaunchAgents/com.camdriver.update.plist" "$QUARANTINE/" 2>/dev/null || true
   - For system-level plists (requires sudo):
     - sudo launchctl bootout system /Library/LaunchDaemons/com.example.plist 2>/dev/null || true
     - If present, move the files to quarantine with sudo mv and preserve a copy: sudo mv /Library/LaunchDaemons/com.example.plist "$QUARANTINE/"
   - Remove or comment out any matching crontab entries (edit with crontab -e) only after copying the crontab to "$QUARANTINE/crontab.bak".

7. Terminate running payload processes safely:
   - List related processes: pgrep -laf 'camapp|cameradriver|camupdate|falconxco|darwin-amd-update' || ps auxww | egrep -i 'camapp|cameradriver|camupdate'
   - Attempt graceful termination: pkill -TERM -f '/var/tmp/camapp|/var/tmp/cameradriver.sh' || true
   - After a short wait, force kill if still present: pkill -KILL -f '/var/tmp/camapp|/var/tmp/cameradriver.sh' || true
   - For identified PIDs, capture lsof -p <pid> and redirect output into "$QUARANTINE/process-<pid>-lsof.txt" before killing.

8. Disable network and verify no active connections from the payload remain:
   - Check listening/established sockets: lsof -i -nP | egrep 'ESTABLISHED|LISTEN' | egrep -i 'camapp|cameradriver|5\.183\.78\.2|<suspicious-domain>' || true
   - Use netstat or ss equivalent: netstat -anv | egrep '5\.183\.78\.2|<suspicious-ip>' || true
   - If the payload has active remote connections, consider temporarily disabling network (Wi‑Fi off) to assist containment if appropriate and coordinated with the user.

9. Quarantine and remove artifacts (after metadata saved):
   - Move all confirmed suspect files/bundles to the quarantine folder rather than immediate rm -rf where possible:
     - mv /var/tmp/cameradriver.sh "$QUARANTINE/" || cp -p /var/tmp/cameradriver.sh "$QUARANTINE/" && rm -f /var/tmp/cameradriver.sh
     - For app bundles: mv "$TMPDIR/CamDriverUpdate.app" "$QUARANTINE/" || cp -R "$TMPDIR/CamDriverUpdate.app" "$QUARANTINE/" && rm -rf "$TMPDIR/CamDriverUpdate.app"
   - For system-owned artifacts use sudo and record actions: sudo mv /Library/... "$QUARANTINE/" || sudo cp -R /Library/... "$QUARANTINE/" && sudo rm -rf /Library/...
   - Do not execute or open any quarantined files. Store the quarantine folder offline or on an isolated storage if possible.

10. Clean up LaunchAgents/Daemons and remove references:
    - Ensure the plist file is removed from LaunchAgents/Daemons directories once copied to quarantine.
    - Run: launchctl print-disabled gui/$(id -u) | egrep 'com.camdriver|com.cam' || true
    - Grep for leftover references: grep -RIlE 'camapp|cameradriver|camdriver|falconxco|<suspicious-domain>' "$HOME" /Library 2>/dev/null | tee "$QUARANTINE/post-clean-greplist.txt"

11. Verification and logging:
    - Verify no matching processes: pgrep -alf 'cameradriver|camapp|camupdate|falconxco' || echo 'none'
    - Verify no matching files at common locations: for p in /var/tmp/cameradriver.sh "$HOME/Library/LaunchAgents/com.camdriver.update.plist" "$TMPDIR/CamDriverUpdate.app"; do [ -e "$p" ] && echo "PRESENT $p" || echo "absent $p"; done
    - Save a summary.txt in the quarantine folder with actions taken, timestamps, checksums, and any network IPs/domains observed.

12. Next steps and reporting:
    - If the machine is corporate-managed, notify IT/security immediately and hand over the quarantine bundle and logs.
    - Consider uploading the quarantined files (hashes first) to a malware-scanning service (VirusTotal) from a secure machine; do not submit from the infected host without isolating network.
    - If unsure about system integrity, plan for an offline forensic analysis or OS reinstall after preserving important data.

## Tips

- Always collect evidence and checksums before deleting; move to a quarantine folder rather than immediate deletion when possible.
- Use sudo only when required for system-level files and record sudo actions in the quarantine summary.
- Avoid executing any suspicious binary. Do not open app bundles or scripts in a way that runs them.
- If the payload contacts remote hosts, consider isolating the Mac from the network to prevent data exfiltration while containing.
- When in doubt, preserve artifacts and escalate to an incident response team or professional for deeper forensic analysis and recovery.
- This skill assumes user consent and that the operator will confirm the exact files/paths to remove; when automation is used, always prompt for explicit confirmation before destructive steps.
