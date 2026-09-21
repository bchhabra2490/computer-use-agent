---
name: chrome-extract-article-and-compare-to-agent-capabilities
description: >-
  Extract the full article text from a web page open in Google Chrome on macOS, produce a concise summary of the page's claimed capabilities, compare those claims to the stored jarvis-agent capabilities, and save/open a short feature-difference report. Use when you must verify or document what a published product/agent can do vs what the local agent supports.
---

## Steps

1. Bring the target page forward in Google Chrome.
   - If the URL is known, open it with: open 'https://example.com/page'
   - Wait until the page visibly finishes loading (no need to wait for autoplaying media).

2. Try an in-browser copy-first approach (fast, preserves visible text):
   - Click the page content area, press Cmd+A, then Cmd+C to copy the visible article text.
   - In Terminal, run: pbpaste > /tmp/article_clipboard.txt
   - If /tmp/article_clipboard.txt contains the article text (inspect with head -n 80 /tmp/article_clipboard.txt), proceed to step 4.

3. If the in-browser copy missed content or the page is JS-heavy, use an HTTP fetch + cleaning fallback:
   - In Terminal run (Python + requests + bs4):
     python3 - <<'PY'
import requests
from bs4 import BeautifulSoup
u='https://ai.meta.com/muse/'  # replace with target URL if needed
r=requests.get(u, timeout=20, headers={'User-Agent':'Mozilla/5.0'})
html=r.text
soup=BeautifulSoup(html,'html.parser')
for t in soup(['script','style','noscript']): t.decompose()
text='\n'.join(line.strip() for line in soup.get_text('\n').splitlines() if line.strip())
open('/tmp/article_fetch.txt','w',encoding='utf8').write(text)
print('WROTE', len(text), 'chars to /tmp/article_fetch.txt')
PY
   - Inspect the file with: head -n 80 /tmp/article_fetch.txt
   - Use /tmp/article_fetch.txt as the extracted article text.

4. Consolidate extracted text into a single file:
   - If /tmp/article_clipboard.txt exists and looks correct, use it; otherwise use /tmp/article_fetch.txt.
   - Copy the chosen file to the Desktop for easier access: cp /tmp/article_clipboard.txt ~/Desktop/article-extracted.txt

5. Summarize the article's capabilities into concise bullets:
   - Use an LLM or manual reading. Produce a short summary (4–12 bullets) describing the product's claimed capabilities, typical phrasing: "can X", "handles Y", "integrates with Z", "uses a secure browser/VM to…".
   - Save the summary to ~/Desktop/article-summary.txt.

6. Obtain the local agent's implemented capability list:
   - Use the agent memory: call the read_memory tool / skill for kind=app name=jarvis-agent or open the stored agent README.
   - Extract a normalized list of implemented features/capabilities (bulleted), save to ~/Desktop/jarvis-agent-capabilities.txt.

7. Produce a concise feature-difference report:
   - Compare each capability bullet from the article summary to the agent's capability list.
   - For each claimed capability mark: "Implemented", "Partially implemented", or "Not implemented" and add one-line rationale (link to agent memory or explain missing pieces).
   - Save the final report to ~/Desktop/feature-diff-<site-shortname>.txt (e.g., ~/Desktop/feature-diff-muse.txt).

8. Open the original article in Chrome (verify):
   - Ensure a Chrome tab with the article is frontmost. If not, open it: open 'https://ai.meta.com/muse/'
   - Optionally capture a screenshot with the chrome-open-url-and-screenshot skill or take a macOS screenshot for archival.

9. Deliver a short update message summarizing completed artifacts and where they are saved:
   - Example short update: "Done — article opened in Chrome; extracted text saved to ~/Desktop/article-extracted.txt; summary to ~/Desktop/article-summary.txt; feature-diff saved to ~/Desktop/feature-diff-muse.txt."

## Tips

- Prefer the in-browser copy (Cmd+A / Cmd+C -> pbpaste) because it captures the reader-visible text ordering; use the HTTP fetch + BeautifulSoup fallback when content is behind heavy JS or when copy yields navigation markup.
- When comparing features, normalize phrases (e.g., "book appointments", "form-filling", "persistent secure browser/VM", "third-party integrations") so comparison is structured rather than word-for-word.
- Save all intermediate files to ~/Desktop with clear filenames and timestamps when repeating this workflow for multiple pages.
- If the page requires sign-in or dynamically loads private content, note that fetch may not reproduce the signed-in view; prefer an in-browser copy in that case.
- Do not rely on long sleeps; wait for visual load states or for copy/paste confirmation before continuing.
- Keep the report concise: list only capabilities the external product claims and a one-line reason why the local agent lacks each missing capability (e.g., missing persistence sandbox, unavailable integrations, or restricted VM-level actions).
