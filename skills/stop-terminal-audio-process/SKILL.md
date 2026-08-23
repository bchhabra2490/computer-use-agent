---
name: stop-terminal-audio-process
description: >-
  Finds and terminates a user process emitting audio (TTS or media) from a terminal or terminal-hosted app on macOS. Use when a terminal or app (e.g., Cursor) is unexpectedly speaking or playing audio and you need to stop it quickly and safely.
---

## Steps

1. Focus Terminal (or open Terminal): use Spotlight (Cmd+Space) → type Terminal → Enter.
2. List likely audio-producing processes with searchable names. Run:

   ps aux | grep -iE "say|afplay|mpv|ffplay|vlc|python|node|cursor|speech|tts" | grep -v grep

   - Note the PID (second column) and the COMMAND column to identify the process owner and invocation.

3. If the list is long, show full command lines for matching PIDs to confirm which one is playing audio:

   for pid in <pid1> <pid2>; do ps -p $pid -o pid,user,%cpu,%mem,etime,command; done

   Replace <pid1> <pid2> with the PIDs you observed.

4. Quick non-destructive test: stop the process without killing to see if audio stops immediately:

   kill -STOP <pid>

   - If audio stops, proceed to either quit the app gracefully or use kill -TERM / kill -9 (below).
   - To resume after a STOP: kill -CONT <pid>

5. If STOP confirmed the offending PID, try to terminate gracefully first:

   kill <pid>

   Wait a few seconds; if the process does not exit, force it:

   kill -9 <pid>

6. If the PID belongs to a named GUI app (e.g., Cursor), prefer quitting the app from the menu or Activity Monitor instead of kill -9:

   - Switch to the app and choose AppName → Quit. If that fails, Activity Monitor → find process → Quit → Force Quit.

7. If you cannot identify a single process, mute system output immediately as a safe fallback: press the Mac mute key or click the volume icon in the menu bar and set volume to 0.

8. After stopping audio, verify normal operation by running a quick check (e.g., play a short harmless system sound or check that the terminal prompt is responsive). If you used kill -9, consider restarting the app you terminated if needed.

## Tips

- Limit kill -9 to user processes you recognize. Do not kill system processes (root-owned or macOS daemons) without knowing their role.
- Common culprits: node/python scripts started inside a terminal, in-app TTS agents, or command-line players (afplay, mpv, ffplay). Searching for those names usually finds the offender.
- If the audio was produced by a terminal-integrated feature (like Cursor running a language-server or TTS subprocess), quit the app rather than repeatedly killing sub-processes; then investigate app settings to disable TTS.
- GUI alternative: open Activity Monitor → search for suspected names (node, python, Cursor, mpv, afplay) → select process → click ✕ → Quit or Force Quit.
- Preserve logs for debugging: before killing, you can capture the process command line and recent output (if available) to a file for later inspection.

Use this skill when a terminal or terminal-hosted app unexpectedly plays speech/audio and you need a concrete, repeatable way to find and stop the responsible process on macOS.
