---
name: gmail-flag-today-important-and-screenshot
description: >-
  Scans the primary Gmail inbox in Google Chrome, extracts the latest 10 messages, flags messages received today that match urgency/billing/legal/manager/keyword or starred/important criteria, opens each flagged message briefly, saves per-message screenshots and a one-line reason, and produces a final summary.
---

## Steps

1. Open Gmail in Chrome
   - Open/bring Chrome to front (Spotlight Cmd+Space → type "Google Chrome" → Enter).
   - If a Gmail tab is already open, switch to it. Otherwise go to https://mail.google.com and load the primary account's inbox.
   - If prompted to pick a profile, choose the primary/active account and wait for the page to show the inbox UI.

2. Prepare and refresh the inbox list
   - Ensure the Primary view (or desired inbox label) is selected.
   - Refresh the inbox with Cmd+R so messages are newest-first.
   - Wait briefly for the list to finish loading (watch for the loading spinner to stop).
   - If the currently visible list does not contain 10 rows, scroll slightly until the top 10 rows are fully visible.
   - Take a screenshot of the list view and save it to the Desktop for record (e.g. Desktop/inbox-list-YYYYMMDD.png).

3. Extract the top 10 rows (newest → oldest)
   - For each of the first 10 visible rows read and record these fields:
     - Sender (left-most name/email shown in the row)
     - Subject (center area)
     - Received time (right side; will be a time like "11:06 PM" for messages received today or a date like "Aug 2" for older)
     - Starred (star icon present/filled for that row?)
     - Important marker (the yellow marker/label or 'important' arrow to the left of the sender; present/absent)
   - Save this top-10 table as a short CSV or text summary on the Desktop (Desktop/gmail-top10-YYYYMMDD.csv).

4. Decide which messages are "received today"
   - Treat rows that display a time (e.g., "9:12 AM", "11:06 PM") rather than a date as received today.

5. Identify which of today's messages look important
   - A message qualifies as important if any of these are true:
     - It is starred or marked Important in the row.
     - Subject or the snippet (the single-line preview visible in the row) contains any of these keywords (case-insensitive): urgent, action required, invoice, bill, payment, statement, legal, notice, meeting, invite, calendar, security, password, reset, alert.
     - Sender address/domain or display name clearly looks like billing/finance/legal/support (examples: contains "billing", "invoice", "statement", "payments", "legal", "no-reply@hdfc", "security@github", but this is heuristic).
     - (Optional) If you have a known manager email address list available, treat messages from those addresses as important. If not available, skip this rule.

6. For each message received today that matches the above rules (do not open messages older than today for this step unless they are starred/important and user asked to include older items):
   - Click the row to open the message briefly.
   - Check for attachments: if the message shows an attachments area (paperclip icon or attachments listing), do not open attachments; still capture the message view but note "has attachments" in the reason and do not download.
   - Take a screenshot of the opened message and save it to a dedicated folder on the Desktop named Gmail-Important-YYYYMMDD (e.g. Desktop/Gmail-Important-20260818/01-sender-subject.png). Sanitize filenames (remove slashes, colons, and replace spaces with underscores).
   - Write a one-line reason explaining why it was flagged as important (examples: "starred and marked Important", "subject contains 'invoice'", "from security@github — security advisory"). Save these one-line reasons in a small text file in the same folder (reasons.txt) or append to the CSV from Step 3.
   - Use the left-arrow/back-to-inbox control (or the inbox breadcrumb) to return to the list before processing the next flagged message.

7. Mid-task status updates (visual)
   - Provide brief on-screen visual notifications after major milestones (e.g., "Inbox refreshed", "Top 10 captured", "3 important messages found — capturing screenshots"). Do not use macOS `say`.
   - Example command to show a macOS Notification (optional automation):
     osascript -e 'display notification "3 important messages found" with title "Gmail scan"'

8. Final summary
   - Produce a short summary file on the Desktop (Desktop/gmail-scan-summary-YYYYMMDD.txt) containing:
     - Timestamp of run
     - The top-10 table (sender, subject, received time, starred, important marker)
     - Which messages were flagged as important (indices 1–10), and the one-line reason for each
     - Paths to the screenshots folder and the inbox-list screenshot
   - Optionally display a final notification: osascript -e 'display notification "Gmail scan complete: N important messages" with title "Gmail scan"'

## Tips

- Detecting the "Important" marker: Gmail shows a small yellow marker/triangle/arrow or an 'important' label near the sender in the list row. If uncertain, open the message to see the yellow tagged label near the subject/header area.
- If the inbox shows conversation view and a single row contains multiple senders, prefer the most-recent message header for sender/time.
- For reproducibility, always save screenshots and the summary files to Desktop/Gmail-Important-YYYYMMDD and the top-10 CSV; use ISO date (YYYYMMDD) to avoid collisions.
- Don’t open or download attachments; record and annotate if attachments are present.
- If the inbox requests re-authentication or 2FA, pause to allow the user to complete sign-in and then continue from Step 2.
- If the user wants manager-specific detection, accept a small list of manager email addresses as an input parameter; otherwise rely on the keyword/sender heuristics above.

Known limitations

- This skill uses visible UI cues in Chrome and heuristic keyword/sender matching; it is not a full-content scan of message bodies nor does it consult external Contacts unless provided. Adjust the keyword list or manager-address input for better precision.
