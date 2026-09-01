---
name: open-and-read-latest-morning-report
description: >-
  Finds the newest morning-report/briefing file on the Mac (Desktop and ~/memory), opens it in the appropriate app, and extracts/reads the top summary, Gmail highlights, market snapshot/market-data, and other section headlines for quick review.
---

## Steps

1. Use morning-report MCP to fetch latest report.
   - Example: use the project's briefing API or MCP if your environment exposes one; fetch the latest delivered briefing and write it to a temp file:
     ```sh
     # If a local briefing service is available, replace with the project-specific fetch command
     mcp_call --server morning-report-local list_briefings
     mcp_call --server morning-report-local get_briefing --date YYYY-MM-DD > /tmp/latest-morning-report.md
     ```
   - If you do that, treat /tmp/latest-morning-report.md as the file to open in step 2.

2. Open the chosen file with the default or suitable editor/viewer.
   - Quick preview: select the file in Finder and press Space to Quick Look.
   - From Terminal, open with the default app:
     ```sh
     open "/full/path/to/file"
     ```
   - To open in a text editor (TextEdit) for plain text/markdown:
     ```sh
     open -a TextEdit "/full/path/to/file"
     ```
   - If the file is a PDF, Preview will open by default via `open`.

3. Identify the report structure and extract the requested sections.
   - List headings (works for Markdown and many plain-text reports):
     ```sh
     grep -nE '^#{1,3} |^[A-Z][A-Za-z ]{4,}$' "/full/path/to/file" | sed -n '1,200p'
     ```
     - This shows lines that look like Markdown headings (#, ##) and plain uppercase-ish section titles.
   - To extract the top summary (the first paragraph immediately under the report title or first heading):
     ```sh
     awk 'NR==1{h=$0} /^(#|##|[A-Z].*\S$)/ && p{exit} {if(!hseen && NF){print; hseen=1} if(hseen) {print}}' "/full/path/to/file" | sed -n '1,20p'
     ```
     - If the file is Markdown, look for the first non-empty paragraph after the top-level heading instead.
   - To pull Gmail highlights, market snapshot/market-data, and other headline lines by name, use named-pattern extraction:
     ```sh
     grep -nE -i 'gmail|gmail highlights|market snapshot|market data|market-data|market snapshot|hacker news|reddit|readings|summary|lead' "/full/path/to/file" || true
     ```
   - For Markdown-style sections (## Market Data, ## Gmail), extract the section contents (first N lines):
     ```sh
     # Example: print the first 20 lines under the '## Market Data' heading
     awk '/^##[ ]*Market Data/{p=1;next}/^##[ ]/{p=0} p{print}' "/full/path/to/file" | sed -n '1,20p'
     ```

4. Read back aloud or summarize the findings (human or TTS as your workflow requires).
   - Summarize the found fields succinctly:
     - Top summary / lead: one-sentence paraphrase.
     - Gmail highlights: list 2–4 bullets of named items.
     - Market snapshot/Market Data: list the top tickers/prices mentioned.
     - Other section headlines: list section names (Hacker News, Reddit, Readings, etc.).
     - DO not skip any points.

## Tips

- Prefer Quick Look for a rapid visual check; use a text editor if you need to copy exact lines.
- If reports are generated in HTML or other formats, open them in Chrome and use the browser's Find (Cmd+F) for section headings.
- If the report is produced by a service (MCP/local API), prefer fetching via that service to ensure you get the canonical delivered version rather than a stale file copy.
- If grep/awk commands above seem noisy for your specific report format, adjust the heading patterns to match the actual file (e.g., '## Market Data' vs 'Market Data:').
- When automating, avoid playing audio or using long waits; extract text programmatically and present a short summary instead.
