---
name: inspect-suspicious-downloaded-installer
description: >-
  Inspects a suspicious command found in shell history that downloaded/ran an installer: identifies the exact history entry and timestamp, fetches HTTP headers and content of the referenced URL into a safe temp file, performs safe static analysis (file, checksums, shell syntax check, grep for persistence/networking keywords), extracts embedded artifacts without executing them, checks common macOS persistence points and running processes/sockets, collects domain reputation info, and prepares a small reproducible report and quarantine bundle.
---

## Steps

1. Find the matching history entry and nearby context (zsh, bash, fish):

   - Search history files for suspect keywords and show context lines:

     ```sh
     grep -n -i -C4 -E 'camera|cameradriver|camupdate|falconxco|driver.falconxco.com|cameradriver.sh|camapp' "$HOME/.zsh_history" "$HOME/.bash_history" "$HOME/.config/fish/fish_history" 2>/dev/null || true
     ```

   - If you get a match in zsh and zsh is using EXTENDED_HISTORY, show a small window around the match to see the timestamp line (starts with ": "):

     ```sh
     idx=$(grep -n -i 'driver.falconxco.com' "$HOME/.zsh_history" | cut -d: -f1 | head -n1)
     [ -n "$idx" ] && sed -n "$((idx-3)),$((idx+3))p" "$HOME/.zsh_history"
     ```

   - If you see a zsh timestamp line like `: 1691234567:0;command`, convert epoch to human:

     ```sh
     epoch=$(sed -n "$((idx-1))p" "$HOME/.zsh_history" | awk -F": " '{print $2}' | cut -d: -f1)
     date -r "$epoch"
     ```

   - Note the exact command string and any URL(s) it used.

2. Capture URL headers and content safely (do NOT execute the downloaded file). Replace $URL with the URL you found.

   ```sh
   URL='https://driver.falconxco.com/downloads/darwin-amd-update.fix'
   TMPBASE="/tmp/installer-review.$$"
   mkdir -p "$TMPBASE"
   curl --fail --location --silent --show-error -D "$TMPBASE/headers.txt" -o "$TMPBASE/installer.bin" -m 20 "$URL" || echo "curl failed or timed out"
   ls -l "$TMPBASE"
   ```

3. Basic static inspection of the downloaded file (no execution):

   ```sh
   file "$TMPBASE/installer.bin"
   wc -c "$TMPBASE/installer.bin"
   shasum -a 256 "$TMPBASE/installer.bin" | tee "$TMPBASE/sha256.txt"
   # If it looks textual (shell script), do a shell syntax check without executing
   head -n 240 "$TMPBASE/installer.bin" | sed -n '1,240p'
   sh -n "$TMPBASE/installer.bin" 2>&1 | tee "$TMPBASE/sh_syntax_check.txt" || true
   ```

4. Search the script (or file) for dangerous or persistence/network keywords (do not run any embedded commands):

   ```sh
   grep -iE 'base64|openssl|chmod|chown|sudo|nohup|&>/dev/null|curl|wget|git clone|python -c|perl -e|ruby -e|mktemp|/var/tmp|/tmp|$TMPDIR|LaunchAgents|launchctl|crontab|/Library/LaunchDaemons|/Library/LaunchAgents|/etc/cron' "$TMPBASE/installer.bin" | sed -n '1,200p'
   ```

   - If the file is binary, use strings/search for the same keywords:

   ```sh
   strings -a "$TMPBASE/installer.bin" | grep -iE 'launchctl|LaunchAgents|crontab|/var/tmp|camapp|falconxco' | head -n 200
   ```

5. Extract embedded base64 blobs or archives safely to separate files (only if you need to inspect them). Never execute the output. Example: if the script contains a base64 blob between markers, extract and decode into the review dir:

   ```sh
   # EDIT the awk markers below to match the script's pattern. Example extracts lines between 'BEGIN_CAM_ZIP' and 'END_CAM_ZIP'.
   awk '/BEGIN_CAM_ZIP/{p=1;next}/END_CAM_ZIP/{p=0}p' "$TMPBASE/installer.bin" > "$TMPBASE/cam.zip.b64"
   [ -s "$TMPBASE/cam.zip.b64" ] && base64 --decode "$TMPBASE/cam.zip.b64" > "$TMPBASE/cam.zip"
   file "$TMPBASE/cam.zip" && unzip -l "$TMPBASE/cam.zip" | head -n 50
   ```

   - For Mach-O binaries found inside, list linked libs (do NOT run):

   ```sh
   for f in "$TMPBASE"/*; do file "$f"; [ -x "$f" ] && otool -L "$f" 2>/dev/null || true; done
   ```

6. Check common locations for installed/running artifacts (do not delete anything yet):

   ```sh
   echo '--- possible artifact files ---'
   ls -la /var/tmp /tmp "$TMPBASE" 2>/dev/null || true
   echo '--- user LaunchAgents ---'
   ls -la "$HOME/Library/LaunchAgents" 2>/dev/null || true
   echo '--- system LaunchAgents/Daemons ---'
   ls -la /Library/LaunchAgents /Library/LaunchDaemons 2>/dev/null || true
   echo '--- crontab (current user) ---'
   crontab -l 2>/dev/null || echo 'no crontab entries'
   ```

7. Find suspicious processes and open network sockets:

   ```sh
   ps auxww | egrep -i 'camapp|camera|cameradriver|camdriver|camupdate|falconxco' || true
   # If you find suspicious PIDs, inspect open sockets for those PIDs:
   for pid in $(ps auxww | egrep -i 'camapp|cameradriver|camupdate|falconxco' | awk '{print $2}'); do
     echo 'PID' $pid
     lsof -nP -a -p "$pid" -i 2>/dev/null || true
   done
   # Show listening TCP ports (requires sudo for full detail):
   sudo lsof -nP -iTCP -sTCP:LISTEN | egrep -i 'cam|camera|falconxco' || true
   ```

8. Check LaunchAgent/launchctl registration for a matching label (use the label you saw e.g. com.camdriver.update):

   ```sh
   LABEL='com.camdriver.update'
   launchctl print "gui/$(id -u)/$LABEL" 2>&1 | head -n 80 || true
   launchctl list | egrep -i 'camdriver|camapp|camupdate' || true
   ```

9. Gather domain and reputation info (local checks):

   ```sh
   domain=$(echo "$URL" | sed -E 's#https?://([^/]+)/.*#\1#')
   echo "domain=$domain" > "$TMPBASE/domain-info.txt"
   whois "$domain" 2>/dev/null | head -n 80 >> "$TMPBASE/domain-info.txt"
   dig +short A "$domain" >> "$TMPBASE/domain-info.txt"
   curl -I --silent --show-error -m 20 "https://$domain/" -o "$TMPBASE/domain-homepage.headers" || true
   ```

   - Also search the domain in a browser or on VirusTotal / Google to see prior reports (manual step): open https://www.virustotal.com and paste the URL or domain, or use your browser to search "falconxco scam".

10. Assemble a short report and save all artifacts to a reproducible folder on the Desktop:

   ```sh
   OUTDIR="$HOME/Desktop/suspicious-installer-$(date +%Y%m%d-%H%M%S)"
   mkdir -p "$OUTDIR"
   cp -a "$TMPBASE"/* "$OUTDIR/"
   echo "Report for $URL" > "$OUTDIR/report.txt"
   echo "Found command in history: $(grep -n -i 'driver.falconxco.com' "$HOME/.zsh_history" 2>/dev/null | head -n1)" >> "$OUTDIR/report.txt"
   shasum -a 256 "$OUTDIR"/* 2>/dev/null >> "$OUTDIR/report.txt"
   echo 'Commands run and notes:' >> "$OUTDIR/report.txt"
   history | tail -n 40 >> "$OUTDIR/report.txt"
   echo "Saved inspection artifacts to: $OUTDIR"
   open -R "$OUTDIR"
   ```

11. Quarantine candidate files (do NOT delete yet; move to a quarantine folder and do not execute):

   ```sh
   Q="$HOME/Desktop/quarantine-suspicious-installer-$(date +%s)"
   mkdir -p "$Q"
   # Example paths to move; edit to match discovered artifacts. Do NOT overwrite unrelated files.
   mv /var/tmp/camapp* "$Q" 2>/dev/null || true
   mv "$TMPBASE"/* "$Q/" 2>/dev/null || true
   ls -la "$Q"
   ```

12. If you confirm active malicious persistence or running processes, stop services carefully and keep copies for forensic review. Prefer to get help from IT/security before deleting system files. Example safe stop (unload a user LaunchAgent label):

   ```sh
   # unload a user LaunchAgent (replace LABEL with actual label). This removes it from the current GUI session only.
   LABEL='com.camdriver.update'
   launchctl bootout "gui/$(id -u)/$LABEL" 2>&1 | tee "$OUTDIR/launchctl-bootout.log" || true
   # kill matching PIDs after recording their state
   ps auxww | egrep -i 'camapp|cameradriver|camupdate' | tee "$OUTDIR/process-list.txt"
   # kill (use only if you accept risk):
   # for pid in $(awk '{print $2}' "$OUTDIR/process-list.txt"); do sudo kill -9 $pid; done
   ```

   - Do not run the commented kill loop unless you understand the impact. Prefer quarantining and consulting security.

13. Final actions and recommendations:

   - If you determine the script was malicious: change any passwords for accounts used after the time of compromise, enable MFA, check for new SSH keys or unknown users, and consider a deeper forensic analysis or OS reinstall if sensitive.
   - Preserve the collected folder ($OUTDIR) and share with your security contact or an analyst rather than deleting it.

## Tips

- Never execute unknown downloaded scripts. Use `sh -n` for shell syntax checking and static inspection tools (file, strings, otool) instead.
- Keep a copy of everything you inspect; moving to a Desktop/Quarantine folder prevents accidental deletion and makes sharing easier.
- Some inspection commands (lsof, launchctl print for other users) may need sudo; use sudo sparingly and document every sudo invocation.
- If you need help interpreting binary artifacts (Mach-O files), save them and consult an analyst who can run them in an isolated VM.
- If you're unsure, stop and escalate to your organization's security team. Quarantine, do not obliterate, until the scope is clear.
