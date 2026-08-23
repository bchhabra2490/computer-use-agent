---
name: remove-third-party-keypress-sound
description: >-
  Locates and removes leftover third‑party agents/launchers, audio plugins, or login items that play a sound on each keyboard press (useful after uninstalling apps like Kivi). Use when typing produces per‑key sounds and the originating app was removed but the sound persists.
---

## Steps

1. Reproduce and observe
   - Keep Terminal frontmost and reproduce the keypress sound once so any helper that logs to stdout/stderr or the system will have a recent timestamp.

2. List suspicious processes
   - In Terminal, run:
     ps aux | egrep -i "kivi|servam|key(click|press|board)|keysound|beep|afplay|coreaudiod|keyboard" || true
   - Paste any matching lines (process name, PID, user). If you see a process, note its path (look at the COMMAND column) before killing.

3. Check loaded LaunchAgents and LaunchDaemons
   - Run:
     echo '---USER AGENTS---'; launchctl list | egrep -i "kivi|servam|key|sound|beep|keysound" || true
     echo '---SYSTEM AGENTS/DAEMONS---'; sudo launchctl print system | egrep -i "kivi|servam|key|sound|beep|keysound" || true
   - If you find a matching service label, note the label and the plist path (next steps show how to find plists).

4. Look for leftover LaunchAgent/Daemon plist files (don’t delete yet)
   - List likely locations and filter names:
     ls ~/Library/LaunchAgents /Library/LaunchAgents /Library/LaunchDaemons /Library/PrivilegedHelperTools 2>/dev/null | egrep -i "kivi|servam|key|sound|beep|keysound" || true
   - Search more widely for matching filenames:
     find ~/Library /Library -maxdepth 4 \( -iname '*kivi*' -o -iname '*servam*' -o -iname '*keysound*' -o -iname '*keyclick*' -o -iname '*keysound*' \) 2>/dev/null | sed -n '1,200p'
   - Also try Spotlight index (fast):
     mdfind "kivi"; mdfind "servam" || true

5. Inspect login items and startup items in System Settings (GUI)
   - Open System Settings → General → Login Items. Look for any unknown vendor (Kivi, Servam, anything referencing key/click/sound) and remove it by selecting and clicking the minus (–) or Remove.
   - Also open System Settings → Privacy & Security → Accessibility/Input Monitoring to see if any removed app still has permissions; remove them if present.

6. Check audio plugin/device drivers
   - Some key‑click installers add HAL audio plugins. Check these folders for unfamiliar items:
     /Library/Audio/Plug-Ins/HAL
     /Library/Audio/Plug-Ins
     ~/Library/Audio/Plug-Ins
   - Look for names referencing the vendor and note the files.

7. Inspect application folders
   - Check /Applications and ~/Applications for leftover helpers (Kivi, Servam, KeySound, etc.) and note their full paths.

8. Safely unload and move suspicious plists/helpers (backup first)
   - For each plist you found, unload it first, then move it to a safe backup folder on the Desktop instead of deleting. Example (replace <plist> with full path):
     # for a per-user LaunchAgent
     launchctl bootout gui/$(id -u) "<plist>" || launchctl unload "<plist>" || true
     mkdir -p ~/Desktop/removed-keypress-sound-backups
     mv "<plist>" ~/Desktop/removed-keypress-sound-backups/

     # for a system LaunchDaemon (requires sudo)
     sudo launchctl bootout system "<plist>" || sudo launchctl unload "<plist>" || true
     sudo mkdir -p /Users/$(whoami)/Desktop/removed-keypress-sound-backups
     sudo mv "<plist>" /Users/$(whoami)/Desktop/removed-keypress-sound-backups/

   - For helper binaries / plugins, move them similarly to the backup folder (use sudo where needed):
     sudo mv "/Library/.../suspect-binary" ~/Desktop/removed-keypress-sound-backups/

   - Do not rm files immediately; keep backups so you can restore if something breaks.

9. Log out / restart relevant services
   - After unloading and moving files, log out and log back in, or reboot the Mac to ensure agents are not reloaded.

10. If the sound persists, check Terminal/iTerm beep and shell settings
   - Terminal: Terminal → Settings → Profiles → Advanced → Sound (turn off audible bell or visual bell).
   - iTerm2: Preferences → Profiles → Terminal → Silence bell or set to visual bell.
   - Shell/prompt: check PS1/prompt hooks and PROMPT_COMMAND for commands that might call afplay or play a sound. Example quick check:
     grep -iE "afplay|play|osascript|say|paplay|aplay" ~/.bashrc ~/.bash_profile ~/.zshrc ~/.zprofile ~/.profile || true

11. Final verification
   - Reproduce typing. If sound is gone, you removed the offending agent.
   - If you need to restore something, move the backup files back to their original locations and reboot.

## Tips

- Always back up (move to a Desktop backup folder) instead of permanently deleting until you confirm the change is safe.
- If you see a LaunchAgent/Daemon label but can’t find a plist path, use `launchctl print <label>` to show its details and path.
- If a process keeps restarting after you bootout/unload and you can’t find the source, check Login Items again, and check third‑party updater utilities (Sparkle, etc.).
- If you’re unsure about a file you found, paste its exact path or the plist contents into a support thread or to an expert before removing.
- If the culprit is a kernel extension or low‑level audio driver (rare), removal may require a vendor uninstaller or Safe Mode troubleshooting.

Use this sequence any time typing produces per‑key or repeated sounds after an app uninstall; the sequence focuses on finding and safely disabling leftover agents, login items, and audio helpers.
