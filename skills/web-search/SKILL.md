---
name: web-search
description: >-
  Searches the web in a browser from the desktop. Use when the user asks to
  look something up, open a site by name, or find information online that is
  not already visible on screen.
---

# Web search

## Steps

1. If no browser is focused, follow the **open-app** skill to launch
   `Google Chrome` (or ask which browser if unclear).
2. Open a new tab with `Cmd+T`.
3. Type the search query or full URL into the omnibox.
4. Press `Enter` and wait for results to load.
5. Screenshot, then click the most relevant result (or navigate the URL bar
   again if you need a specific site).

## Tips

- Prefer a precise query over vague ones; include site names when known
  (e.g. `site:news.ycombinator.com …`).
- If a cookie/consent banner blocks the page, dismiss it before continuing.
- Do not enter passwords or payment details unless the user explicitly asks
  via `ask_user`.
