---
name: chrome-copy-current-tab-url
description: >-
  Copies the full URL of the frontmost Google Chrome tab to the clipboard and reports the exact URL back to the user. Use when a precise current-tab URL is needed without navigating away or closing the tab.
---

## Steps

1. Ensure Google Chrome is the frontmost application. If not, activate it (Spotlight Cmd+Space then type "Chrome" and Enter, or click the Chrome window).
2. Focus the address bar and reveal the full URL: press Cmd+L.
3. Copy the full URL to the clipboard: press Cmd+C.
4. (Optional verification) Read the clipboard to confirm the exact URL (e.g., run `pbpaste` in Terminal or use an equivalent clipboard-read action).
5. Do not navigate away, reload, or close the tab. Report the exact URL text copied to the user.

## Tips

- Cmd+L reliably selects the omnibox and reveals the full URL (including protocol) in most Chrome versions. If that fails, click the address bar with the mouse and then Cmd+C.
- To programmatically verify the clipboard on macOS, use `pbpaste` and confirm the output matches the copied text before reporting.
- If multiple Chrome windows or profiles are open, confirm you are working in the intended frontmost window before copying.
- Avoid actions that navigate the page (e.g., pressing Enter) — only select and copy the address bar content.
- If the URL is extremely long, ensure the entire string is selected before copying (Cmd+L then Cmd+C covers this).
