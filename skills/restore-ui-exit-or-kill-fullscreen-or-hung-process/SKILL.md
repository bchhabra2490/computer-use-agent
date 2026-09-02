---
name: restore-ui-exit-or-kill-fullscreen-or-hung-process
description: >-
  Restores macOS UI interaction when a fullscreen or hung application/process (including terminal sessions like screen/tmux) has captured or blocked the desktop by trying non-destructive exits first, then using Activity Monitor or Terminal commands to quit or kill the offending process.
---

## Steps

1. Try safe keyboard/UI escapes
   - Press Cmd+Option+Esc to open the Force Quit Applications window. If you recognize the offending app, select it and click "Force Quit". This is the least-invasive first step.
   - Press Control+Command+F to toggle fullscreen for the frontmost app (may reveal the UI).
   - Try Cmd+Tab to switch to another app (Finder or Terminal). If you can switch, open Terminal or Activity Monitor to proceed with safer termination.
   - Press F3 (Mission Control) or Control+Up Arrow to show all Spaces and windows; locate and close the stuck fullscreen window if visible.

2. Use the menu bar if it appears
   - Move the pointer to the top of the screen to reveal the menu bar. If visible, choose View → Exit Full Screen (or the app’s equivalent) or use the app menu to Quit.

3. If GUI methods fail, open Activity Monitor (graphical)
   - Press Cmd+Space, type "Activity Monitor", press Enter.
   - In Activity Monitor, sort by CPU or Memory to find a process using lots of resources or the app name you saw.
   - Select the process and click the stop (x) button → choose "Quit" first; if that fails, choose "Force Quit".

4. Use Terminal commands (when you can open Terminal)
   - Open Terminal (Cmd+Space → type "Terminal" → Enter).
   - Inspect recent processes: ps -ax -o pid,ppid,%cpu,%mem,command | head -n 200
   - Narrow by name (replace <pattern> with part of the app/command): ps -ax | grep -i <pattern> | grep -v grep
   - Gracefully ask the process to quit: kill <PID>
   - If it doesn't exit, force it: kill -9 <PID>

5. If the problem is a terminal multiplexed session (screen or tmux)
   - For GNU screen:
     - List sessions: screen -ls
     - If you see the stuck session, either reattach: screen -r <session> or quit it: screen -S <session> -X quit
     - As a last resort, find the screen process PID and kill it (ps -ax | grep SCREEN or pgrep -f SCREEN; kill <PID>)
   - For tmux:
     - List: tmux ls
     - Kill specific: tmux kill-session -t <session>
     - Or kill tmux server: tmux kill-server

6. If a process spawned by a shell is stuck (e.g., a runaway script)
   - Use: ps -ef | grep -i <script-or-command-name>
   - Note the PID and kill as above.

7. If the display server or WindowServer itself is hung (rare)
   - Try logging out if possible (Apple menu → Log Out). If that is impossible, you can reboot:
     - From Terminal: sudo shutdown -r now
     - Reboot is last-resort; warn the user because unsaved work will be lost.

8. After recovery
   - Reopen apps and check for data loss. If a terminal session was important, attempt to reconnect or inspect logs/backups.

## Tips

- Always try non-destructive methods first (Exit Full Screen, Quit) before force-killing processes.
- Ask the user to confirm before killing processes that look like editors, IDEs, or services with unsaved work.
- For remote or critical servers, prefer reattaching a session instead of killing it to preserve state.
- If you need to identify a process by window title, use Activity Monitor’s Inspector (select process → press the (i) button) or use tools like lsof if needed.
- If you must reboot, warn the user about unsaved changes and take screenshots if verification or a record is required.
