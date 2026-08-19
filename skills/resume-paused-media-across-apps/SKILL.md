---
name: resume-paused-media-across-apps
description: >-
  Resumes paused audio/video by scanning common macOS media apps and browser tabs, resuming the most-recently-active paused source, and falling back to the system play key. Use when a user asks to resume playback from whatever app or tab was last paused.
---

## Steps

1. Preconditions
   - Ensure the automation has Accessibility (UI scripting) permissions for controlling apps and clicking UI elements.
   - Do not change macOS system volume or any in-player volume sliders.

2. Build candidate list and ordering
   - Candidates (in priority order): Spotify, Music (iTunes), VLC, QuickTime Player, Google Chrome, Microsoft Edge, Safari.
   - For determining "most-recently-active" paused source, use the last-focused timestamp for each app/window/tab; prefer the highest timestamp among paused candidates.

3. Check and resume native media apps (use app-specific play commands when available)
   - Spotify
     - If Spotify is running, query playback state and then issue a play command if paused:
       - Check state: osascript -e 'tell application "Spotify" to player state' (returns "playing"/"paused").
       - If paused: osascript -e 'tell application "Spotify" to play'.
       - Verify start by re-checking player state becomes "playing".
     - If AppleScript fails, bring Spotify to front and click its Play button via Accessibility and verify state.

   - Music (iTunes on older macOS)
     - If Music is running, check state: osascript -e 'tell application "Music" to player state'.
     - If paused: osascript -e 'tell application "Music" to play'.
     - Verify player state becomes "playing".

   - VLC
     - If VLC is running, attempt AppleScript: osascript -e 'tell application "VLC" to play'.
     - If AppleScript not responsive, bring VLC forward and use Accessibility to click the Play button in the window.
     - Verify playback by checking the app's UI or media position updates.

   - QuickTime Player
     - If QuickTime Player is running, run: osascript -e 'tell application "QuickTime Player" to play front document'.
     - Verify playback began (player state or UI change).

   - After each app-specific attempt, if play started, stop and report success (see mid-task updates below).

4. Check browser tabs for paused media (Chrome/Edge/Safari)
   - For each browser with open windows/tabs, inspect tabs for media indicators (audio icon, titles containing YouTube/YouTube Music/Spotify Web, or AX roles indicating media controls). Prefer tabs in most-recently-active windows first.
   - When you locate candidate tab(s):
     - Bring that tab to the front.
     - Try a non-invasive UI click on an obvious Play button via Accessibility (AXButton with label "Play", aria-labels, or a visible play glyph). If Accessibility finds a Play button, click it once.
     - If no accessible Play button is found, inject a conservative JavaScript play fallback into the tab (use browser remote debugging or an extension-capable run):
       - JS snippet: (function(){ const el = document.querySelector('video, audio'); if(el && el.paused) { el.play().then(()=>true).catch(()=>false); } else false; })();
     - After clicking or running JS, verify playback by checking the media element's paused property is false or the tab's audio indicator becomes active.
     - If multiple browser tabs show paused media, choose the tab whose window/tab has the most-recently-focused timestamp.

5. Fallback: system media-play key
   - If no individual app or tab responds as paused or playable, send the system play/pause media key once (do not change volume). This may resume whatever media the system last routed to.

6. Verification and reporting (mid-task updates required)
   - As soon as you detect a paused candidate you will attempt to resume, provide a mid-task update: e.g. "Found paused media in <app or browser tab title>".
   - After issuing the play command/click, verify playback started and then report: e.g. "Playback started in <app/tab> — <track title if available>".
   - If no paused media was found and the system play key did not start anything, report: "No paused media found; system play key did not resume playback."

7. Safety, retries and timeouts
   - Only attempt each app/tab once per run, with a short verification window (a few seconds) to detect playback start.
   - Do not change or set any volume values, do not mute/unmute.
   - If AppleScript reports errors or the app is not scriptable, fall back to bringing the app/window forward and using Accessibility to click Play.
   - Capture a screenshot of the resumed player UI for verification if permitted.

## Tips

- Prefer app-specific AppleScript commands first (Spotify, Music, QuickTime) because they are reliable for checking state without noisy UI interactions.
- For browsers, use the most-recently-focused tab heuristic to break ties when multiple paused tabs exist.
- Ensure the automation has necessary Accessibility and browser remote-debugging/automation permissions; otherwise, rely on the system media key as the final fallback.
- Avoid any long waits tied to media duration; only use short verification delays (a few seconds) to confirm playback state change.
