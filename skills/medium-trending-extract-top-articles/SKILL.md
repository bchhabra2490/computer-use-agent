---
name: medium-trending-extract-top-articles
description: >-
  Extracts the top articles from Medium's Trending page in Google Chrome on macOS: opens the Trending page, ensures the top article cards are visible, opens each top card in new tabs, and for each article copies the title, author, clapped count or reading time (if visible), a one-line summary/snippet, and the article URL.
---

## Steps

1. Activate Google Chrome and open the Trending page.
   - Bring Chrome forward (Cmd+Tab) then focus the address bar (Cmd+L).
   - Type or paste `https://medium.com/trending` and press Enter.
   - If the page shows a 404 but the recommendation/article cards are visible, continue — the cards shown on the page are the target.

2. Reveal the top article cards.
   - Scroll up to the top of the page (Page Up or two‑finger swipe up or Cmd+Up) so the first row of trending/recommended article cards is fully visible.

3. Open each top card in its own tab.
   - For each article card in the first visible row (the top-most cards on the page) open the link in a new tab by Cmd+clicking the headline or image. If a card does not open in a new tab by Cmd+click, right-click the headline and choose "Open Link in New Tab."
   - Limit to the cards visible without additional scrolling (the first row). If you need a different number, decide the count before proceeding.

4. Visit each newly opened tab and extract fields.
   - Newly opened tabs appear to the right of the current tab. Switch to the first of those new tabs by clicking its tab in the Chrome tab bar.
   - For each article tab, gather this information in order:
     - Title: copy the large article headline (H1). If unsure, use the page title (Cmd+L then Cmd+C to copy the URL, and look at page content) or check the `og:title` meta (view page source or inspect element) as a fallback.
     - Author: copy the byline shown under/near the title (author name and link). If not visible, look for a meta `author` tag or the author link near the top of the article.
     - Claps or reading time: prefer the clap count if a clap/like control shows a numeric value. If clap count is not displayed, record the reading time (e.g., “6 min read”) if visible near the title/byline. If neither is visible, set this field to null or “not shown.”
     - One-line summary/snippet: copy the first paragraph under the title as a one-line summary. If the article is paywalled or the first paragraph is long, instead use the preview/excerpt shown on the Trending card (return to the Trending tab if needed and copy the excerpt text for that card).
     - URL: focus the address bar (Cmd+L) and copy the full URL (Cmd+C).
   - Record these five items (title, author, claps-or-reading-time, one-line snippet, URL) for the article.
   - Close the article tab when done (Cmd+W) to return to the Trending page or move to the next new tab.

5. Repeat step 4 for each top card opened in step 3 until all top-row articles are processed.

6. Produce the final list.
   - Present a simple list of top articles with the five fields for each article in the order they appeared on the Trending page.
   - If any field was unavailable, note it as “not shown” or null.

## Tips

- If Medium prompts for sign-in or paywall, prefer extracting the snippet from the Trending card (the preview text) rather than signing in.
- For accuracy, prefer DOM text (headline H1, byline element, elements that explicitly show clap count or read time). When in doubt, capture the first paragraph and the address bar URL as authoritative sources.
- If the Trending route returns a 404 but recommendations/cards are visible (some Medium routes do this), proceed using the visible cards on the page; they are normally the correct top items.
- If you need a reproducible sample size, add a step to accept a parameter like `count` (e.g., top 5). This skill defaults to the first-row visible cards.
- Optionally capture a screenshot of each opened article (for verification) before closing its tab.

Use this skill when you need a repeatable, desktop-automatable procedure to gather title, author, claps/reading-time, a one-line snippet, and URL for Medium's top/trending articles in Chrome on macOS.
