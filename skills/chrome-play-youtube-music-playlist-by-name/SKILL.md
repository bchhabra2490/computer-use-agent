---
name: chrome-play-youtube-music-playlist-by-name
description: >-
  Finds an existing YouTube Music tab in Google Chrome (preferring a named playlist), avoids opening tabs whose preview would change a specified display, and starts playback; if no suitable tab exists, opens music.youtube.com, searches for the playlist, and starts it. Use when you want a specific playlist resumed or started without disturbing other windows or displays.
---

## Steps

1. Prepare: identify the playlist name to find (e.g., "Bollywood Party") and, if needed, the display/window you must not change (e.g., a diagram shown on "L27i-40").

2. Open Chrome Tab Search:
   - In Google Chrome, press Cmd+Shift+A to open Tab Search.

3. Filter results by playlist name:
   - Type the playlist name (e.g., "Bollywood") into the Tab Search field to narrow matching tabs.

4. Inspect previews (do NOT click tabs that would change a protected display):
   - Hover each matching Tab Search result to show its preview.
   - If a preview shows the protected content (for example the TP4056 diagram on L27i-40), skip that result and do NOT open it.
   - Choose the result whose preview clearly shows YouTube Music or the playlist/player UI.

5. Open the chosen tab and start playback:
   - Click the chosen Tab Search result to activate that tab in Chrome.
   - In the YouTube Music page, click the big playlist Play triangle (usually near the top of the playlist) or click the play button in the bottom player/control bar.
   - Confirm playback started by checking that the play icon changed to a pause icon and/or the progress timer is advancing (or that the player shows a running progress bar).

6. If no suitable existing tab is found:
   - Open a new tab (Cmd+T), focus the address bar (Cmd+L), and go to https://music.youtube.com.
   - Use the site search field to search the playlist name (type it and press Enter).
   - From the search results, open the desired playlist and click the playlist Play button or the bottom-player Play.
   - Confirm playback started as in step 5.

7. Finish without switching or altering other apps/displays:
   - Close Tab Search (Esc) if still open and leave other windows and protected displays untouched.
   - Stop after confirming audio/playback has started.

## Tips

- Keyboard shortcuts: Cmd+Shift+A = Chrome Tab Search, Cmd+T = new tab, Cmd+L = focus URL bar, Esc = close Tab Search.
- Hovering tab results shows a small preview; use that to avoid opening tabs that would change content on a particular display.
- The YouTube Music player has two common play triggers: a large playlist-level play button near the playlist header and a play/pause control in the bottom player bar. Try the playlist-level play first.
- If playback appears to toggle but no audio is heard, verify the YouTube player shows progress and that system volume and tab audio are unmuted.
- Avoid using automated waits for media: rely on the player's visual state (play/pause icon and progress) to confirm playback.
