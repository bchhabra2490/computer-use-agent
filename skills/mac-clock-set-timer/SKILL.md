---
name: mac-clock-set-timer
description: >-
  Sets a timer in the macOS Clock app (or via Spotlight), selects the 'When Timer Ends' alert sound, adjusts system volume, starts the timer, and optionally watches for and verifies completion. Use only when the user explicitly wants the Clock app UI. For a spoken "set a timer" or "remind me in N minutes", the orchestrator/agent must call set_timer instead of this skill.
---

## Steps

1. Open the Clock app (or press Cmd+Space and type "Clock" then Enter).
2. In Clock, switch to the Timers tab (top: World Clock / Alarms / Stopwatch / Timers).
3. Click the hours/minutes/seconds digits and enter the desired duration in HH:MM:SS format (e.g., 00:01:00 for one minute). Ensure fields read exactly the intended duration.
4. Click the "When Timer Ends" dropdown/selector below the digits and choose a clear, loud alert sound (example choices: Radar, Bell, or other short, high-volume tones).
5. Set the system output volume to about 70%:
   - GUI method: Open Control Center (menu bar top-right) or click the volume icon and drag the slider to ~70%.
   - Terminal method: run `osascript -e 'set volume output volume 70'` if you prefer a reproducible command.
6. Verify the Clock window still shows the chosen alert and the correct remaining time.
7. Click Start (or press Enter if the Start button is focused) to begin the timer.
8. (Optional) To verify completion, keep the Clock window visible and watch the countdown until it reaches 00:00. Confirm a visible notification appears and the selected alert sound plays.

## Tips

- If Clock isn't available on older macOS versions or is hidden, use Spotlight (Cmd+Space) to search for "Timer" or use third-party timer apps with similar steps.
- Avoid automations that hard-sleep for the entire timer duration; instead poll the Clock UI or monitor for the notification/sound so the workflow can detect completion without long, uninterruptible sleeps.
- Do not use the macOS `say` command for audible notifications in automated instructions (use the Clock alert sound or system notification instead).
- Use the `osascript` volume command shown above when you need a reproducible volume level from scripts or automation steps.
- If you need the assistant to report when the timer ends, prefer `set_timer` with speak=true (native reminder) rather than watching Clock.app. Use this skill only when they asked to set the Clock app itself.
