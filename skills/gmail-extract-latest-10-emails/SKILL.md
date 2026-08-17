---
name: gmail-extract-latest-10-emails
description: >-
  Opens Gmail in Google Chrome on macOS, signs in if needed (pauses for 2FA), shows the Primary inbox sorted by newest, captures a screenshot of the inbox, and extracts sender, subject, received time, first-line snippet, and unread status for the latest 10 received messages. Use when a reproducible snapshot and parsed summary of recent emails is required without modifying mail.
---

## Steps

1. Open Google Chrome on the main display (Spotlight: Cmd+Space → type "Google Chrome" → Enter) and bring it to front.
2. Navigate to https://mail.google.com and wait up to 30 seconds for Gmail to finish loading. If a persistent loading spinner appears, allow a short extra wait and then reload once.
3. If the browser shows a Google sign-in page or the account chooser instead of the Inbox:
   - Click the visible "Sign in" or the default account entry. Let Chrome autofill saved credentials and press Enter.
   - If a 2FA / OTP prompt appears, pause and ask the user for the code; do not proceed until the user provides it.
4. When the Inbox loads, ensure the view is the Primary inbox:
   - Click the "Primary" tab in the left/center tab row to bring Primary into view.
   - Visually confirm the list shows email rows (sender, subject, snippet, time) and that the newest messages appear at the top. (Gmail defaults to newest-first; confirm timestamps decrease down the list.)
5. Capture a screenshot of the visible Gmail window (or full Chrome window) and save it to an easy location (for example: ~/Desktop/Gmail-inbox-YYYYMMDD-HHMMSS.png). Keep the screenshot before interacting with messages.
6. Extract the latest 10 received emails (or all visible if fewer than 10):
   - Prefer using Chrome's accessibility tree or run a small snippet in the Chrome Console to collect the fields. Example JavaScript to run in the Console (works with typical Gmail DOM classes; use accessibility fallback if classes differ):

```javascript
(() => {
  const rows = Array.from(document.querySelectorAll('tr.zA')).slice(0, 10);
  const emails = rows.map(r => {
    const unread = r.classList.contains('zE') || r.getAttribute('aria-checked') === 'false';
    const senderEl = r.querySelector('.yW span') || r.querySelector('.zF') || r.querySelector('.yP');
    const sender = senderEl ? senderEl.textContent.trim() : '';
    const subjectEl = r.querySelector('.y6 .bE .bog') || r.querySelector('.y6 span') || r.querySelector('.bog');
    const subject = subjectEl ? subjectEl.textContent.trim() : '';
    const timeEl = r.querySelector('.xW .xY span') || r.querySelector('td.xW span') || r.querySelector('.xW');
    const time = timeEl ? (timeEl.getAttribute('title') || timeEl.textContent.trim()) : '';
    const snippetEl = r.querySelector('.y2') || r.querySelector('.y6 .y2');
    const snippet = snippetEl ? snippetEl.textContent.replace(/^[-–—\s]+/, '').trim().split('\n')[0] : '';
    return { sender, subject, time, snippet, unread };
  });
  console.log(JSON.stringify(emails, null, 2));
  return emails;
})();
```

   - If the page DOM uses different classes, use Chrome's DevTools Elements panel or the macOS accessibility inspector to identify the list-row elements and equivalent child nodes for sender, subject, time, and snippet.
   - Stop at the first visible line of the snippet (truncate at the first newline). Collect at most 10 rows; if fewer exist, return them all.
7. Save the parsed results to a file (example: ~/Desktop/gmail-latest-10.json) and/or copy the JSON to the clipboard. Include which messages are unread by a boolean flag.
8. Return (or report) the path to the screenshot and the extracted list. Do not archive, delete, mark read/unread, move messages, or change Gmail settings at any step.

## Tips

- Pause and explicitly ask the user if any 2FA / OTP / phone prompt appears; do not try to bypass.
- Gmail's DOM can change; if the `tr.zA` selector fails, fall back to selecting visible list rows via the accessibility tree (rows with role="row" inside the message list container).
- Capture and save the screenshot before reading or opening any message to avoid accidentally changing read state.
- If multiple Google profiles are signed in, use the Chrome profile that opens the Inbox by default; if opened into a different Inbox, click the profile avatar (top-right) to switch to the expected account rather than signing out.
- Preserve user privacy: store artifacts locally (Desktop/Downloads) and avoid uploading email content to external services without explicit user consent.
- If timestamps show relative times ("2 hr", "Yesterday"), include the displayed string as-is. If the user requests absolute ISO times, ask before converting.
