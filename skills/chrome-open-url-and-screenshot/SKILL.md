---
name: chrome-open-url-and-screenshot
description: >-
  Opens a specified URL in Google Chrome on macOS, brings the Chrome window/tab to the front, waits for the page to finish loading (handles stuck spinners by reloading), captures a screenshot of the page, and reports completion. Use when asked to open a known web page and verify/record that it loaded.
---

## Steps

1. Bring Google Chrome to the front using Spotlight: press Cmd+Space, type "Google Chrome", press Enter. If Chrome is already running, use Cmd+Tab or click its window to focus it. If the requested URL is already open in a tab, use that tab — do not Cmd+T a new tab or retype the URL.
2. Focus the address bar with Cmd+L.
3. Paste or type the exact URL and press Enter.
4. Wait for the page to load: watch for the page title to update and the central/loading spinner to disappear. Allow an initial wait of 5–10 seconds; if dynamic content (video/live) is expected, allow an additional 5–15 seconds.
5. If the page appears stuck (spinner persists after ~10–15s), press Cmd+R to reload and wait again. If Chrome is not focused, click anywhere in the Chrome window or press Cmd+Tab first.
6. Once the page is visibly loaded (content, player or main content is rendered and spinner is gone), take a screenshot of the Chrome window.
7. Report that the URL is open and finished loading and provide the screenshot.

## Tips

- If a sign-in/permission modal blocks the page, note it and pause to ask the user before proceeding.
- For YouTube live/video pages, a brief spinner is normal; wait until video player controls, title, and chat (if present) are visible.
- Use Cmd+L then paste (Cmd+V) to avoid typos when entering long URLs.
- If network errors appear (offline / DNS / 5xx), capture a screenshot showing the error and report the failure instead of repeating reloads indefinitely.
- To ensure the Chrome tab is frontmost in multi-window setups, click the desired tab or press Option+Cmd+Right/Left to navigate tabs before taking the screenshot.
