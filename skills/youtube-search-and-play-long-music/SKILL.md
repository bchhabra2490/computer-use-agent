---
name: youtube-search-and-play-long-music
description: >-
  Finds a long (>=30 min) calming music video or playlist on YouTube, starts playback in Chrome, ensures audio is unmuted, and verifies playback is progressing. Use when asked to play long-form relaxing/instrumental music on a Mac.
---

## Steps

1. Open Google Chrome (Spotlight: Cmd+Space, type "Google Chrome", Enter) and bring it to the front.
2. In Chrome, focus the address bar (Cmd+L) and navigate to a YouTube search for the desired query, e.g.:
   - https://www.youtube.com/results?search_query=sitar+music+1+hour
   - or https://www.youtube.com/results?search_query=sitar+instrumental+long
3. Inspect the search results thumbnails and durations shown on each result. Look specifically for videos or playlists with duration >= 30:00 (or playlists whose first item is long).
4. If multiple suitable results appear, prefer the single video or playlist with the highest visible view count. If view counts are not visible on the search page, open the most promising results in new tabs and check view counts on the video pages.
5. Click the chosen video (or the first video in a chosen playlist) to open it.
6. Start playback by clicking the center play button or the bottom-left play control.
7. Ensure YouTube is unmuted: click the speaker icon on the player so it does not show the muted (crossed-out) icon.
8. If you hear nothing, check macOS system volume (top-right menu bar or System Settings > Sound) and raise it as needed.
9. Verify playback is actually progressing: watch the elapsed time in the player for a few seconds and confirm it advances beyond 0:00.
10. If the player is stuck loading or an ad paused playback, either wait for the ad to finish or click play again after the ad; if the page never loads, reload the tab.
11. Report the final state: whether playback is playing or paused, and whether audio is muted or unmuted. Optionally copy the video URL (Cmd+L, Cmd+C) to the clipboard for reference.

## Tips

- Playlists: clicking a playlist may open a playlist page; ensure the first playing item meets the duration/quality requirements.
- Choosing quality: if the video is high view count but contains live streams or low-quality audio, preview a short segment to confirm audio quality.
- Autoplay or region restrictions: if playback is blocked by age/region restrictions or sign-in, notify the user instead of forcing sign-in.
- Stuck spinner: if the page never starts, reload the tab once; if still stuck, try opening the same video in an Incognito tab to rule out extensions.
- Verification: confirm elapsed time increases for 5–10 seconds to ensure real playback (not just a paused-looking animation).
