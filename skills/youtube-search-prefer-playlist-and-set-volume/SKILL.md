---
name: youtube-search-prefer-playlist-and-set-volume
description: >-
  Searches YouTube for a query, prefers a playlist result (falls back to an official-sounding video), opens the playlist or video, starts playback of the first item, ensures audio is audible by unmuting and setting the YouTube player and macOS system volume to a target level, and handles cookie/region pop-ups and skippable ads. Use when you want reliably to start listening to a searched playlist on a Mac without signing in.
---

## Steps

1. Open Google Chrome (or the user’s default browser if Chrome isn't available) and navigate to https://www.youtube.com.
2. If a cookie-consent / region dialog appears, accept or dismiss it so the page is usable without signing in.
3. Click the YouTube search bar, type the exact query provided, and press Enter.
4. Inspect the results and prefer a playlist result: look for entries labeled “Playlist” or that have the playlist icon/metadata (often the largest left thumbnail or a result with a list-length label). If a playlist is present as the top/first result, click its thumbnail or title. If no clear playlist exists, choose the first official-sounding music video (official channel / VEVO / artist channel).
5. On the playlist page, start playback by clicking the playlist’s main Play icon or by clicking the first item’s thumbnail. If you opened a single video, click Play on the player.
6. If an ad starts, wait for it to finish or click the visible “Skip Ad” button when it appears. Do not sign in to skip ads.
7. Ensure the YouTube player is unmuted: press the video player’s speaker icon or press the keyboard shortcut `m` (toggle mute).
8. Set YouTube player volume to about 50%: drag the player volume slider to the mid position or, if slider control is unreliable, use the browser console to set the HTML5 video element volume (e.g. run in page console: `document.querySelector('video').volume = 0.5`).
9. Set the macOS system output volume to the same target (50%) using a reliable system command: `osascript -e 'set volume output volume 50'`.
10. Verify playback is ongoing by checking that the player shows elapsed time and the video is not paused. Capture the frontmost video title (page title or the element near the player) and copy the video URL to the clipboard or record it for reporting.
11. Return a brief status: the video title (or playlist + item title), confirmation that playback is ongoing, and that volumes were set. Optionally capture a screenshot as verification.

## Tips

- Prefer Chrome for consistency. Use Spotlight (Cmd+Space) → type Chrome → Enter to open it.
- Use keyboard shortcuts: `k` toggles play/pause, `m` toggles mute, and `f` toggles fullscreen; these help verify state without relying on coordinates.
- Playlist results are usually labeled with the word “Playlist” and show a small list/avatar overlay; choose those to play sequential tracks.
- If the player or autoplay blocks, click the tab to ensure it has focus, then press `k` to start playback.
- For reliable system volume setting, use AppleScript (`osascript`); for precise player volume, adjust the HTML5 video volume via the console if UI slider dragging is unreliable.
- Do not sign in. If a sign-in modal blocks the page, dismiss or close it rather than authenticating.
- If multiple playlist-like results appear and the choice matters, pause and ask the user which to prefer.
