---
name: web-search
description: >-
  Searches the web in a browser from the desktop. Use when the user asks to
  look something up, open a site by name, or find information online that is
  not already visible on screen.
---

# Web search

Prefer an MCP search/docs server (`mcp_call`) when one is connected. Only drive
the browser when the user wants a page on screen, or no search MCP is available.

## Steps

1. If an MCP catalog lists a search or fetch tool, call `mcp_call` with the query
   and answer from that result. Do not open Chrome just to scrape Google.
2. If no MCP search tool exists (or the user asked to *open* a site), continue
   with the desktop steps below.
3. If no browser is focused, follow the **open-app** skill to launch
   `Google Chrome` (or ask which browser if unclear).
4. Open a new tab with `Cmd+T`.
5. Type the search query or full URL into the omnibox.
6. Press `Enter` and wait for results to load.
7. Screenshot, then click the most relevant result (or navigate the URL bar
   again if you need a specific site).

## Tips

- Prefer a precise query over vague ones; include site names when known
  (e.g. `site:news.ycombinator.com …`).
- If a cookie/consent banner blocks the page, dismiss it before continuing.
- Do not enter passwords or payment details unless the user explicitly asks
  via `ask_user`.
