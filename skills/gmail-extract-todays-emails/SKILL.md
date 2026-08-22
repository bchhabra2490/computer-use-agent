---
name: gmail-extract-todays-emails
description: >-
  Extracts all Gmail messages received in the last 24 hours (or since midnight), captures a screenshot of the search results, and saves a JSON summary (sender, subject, time, unread, snippet) to ~/Desktop for later review.
---

## Steps

1. Open Google Chrome (Spotlight: Cmd+Space, type "Google Chrome", Enter) and switch to the signed-in Gmail account you want to check (click the avatar top-right if multiple accounts).
2. Go to Gmail: press Cmd+L, type https://mail.google.com and press Enter. Wait for the page to finish loading.
3. Focus Gmail's search box (press / or click it). To show messages from the last 24 hours, type:
   - newer_than:1d
   Or to be explicit for today use your local date: after:YYYY/MM/DD before:YYYY/MM/DD (replace YYYY/MM/DD with today's date and tomorrow's date).
   Press Enter and wait for results to appear.
4. Verify you are viewing the correct mailbox and tab (Inbox / Primary). If results look empty, try toggling the account avatar or widen the query (newer_than:7d) to confirm Gmail loaded correctly.
5. Capture a verification screenshot of the results and save it to the Desktop. From a Terminal run:
   screencapture -x ~/Desktop/Gmail-todays-mails-YYYYMMDD.png
   Replace YYYYMMDD with today’s date (e.g. 20260823).
6. Produce a JSON summary of the messages shown by the search. For each visible message in the search results, collect these fields: sender (display name or email), subject, time (as shown in the list), unread (true/false), and first-line snippet (if visible). Do NOT mark messages as read unless the user asked.
   - If there are many results, scroll the results pane and collect from all loaded rows. Open a message only briefly if needed to get the exact sender/first-line snippet, then close/reply/mark actions must be avoided.
7. Save the array of message objects to a Desktop file named gmail-todays-mails-YYYYMMDD.json. Example JSON file content format:
   [
     {"sender":"LinkedIn","subject":"Example subject","time":"11:23 PM","unread":false,"snippet":"first-line preview"},
     {"sender":"Amazon.in","subject":"We found something you might like","time":"9:11 PM","unread":true,"snippet":"preview text"}
   ]
   You can create the file from Terminal with a heredoc while replacing contents with the parsed entries:
   cat > ~/Desktop/gmail-todays-mails-YYYYMMDD.json <<'EOF'
   [
   <paste JSON array here>
   ]
   EOF
8. Report completion and the saved artifact paths (e.g. ~/Desktop/Gmail-todays-mails-YYYYMMDD.png and ~/Desktop/gmail-todays-mails-YYYYMMDD.json).

## Tips

- Use newer_than:1d for a quick last-24-hours search; use after:YYYY/MM/DD before:YYYY/MM/DD when you need strict calendar-day boundaries.
- If Gmail requires sign-in or 2FA, pause and complete authentication before continuing; do not attempt to bypass 2FA.
- If multiple accounts exist, repeat the search for each account by switching the Gmail account (avatar menu) and saving separate files (append account shortname to filename if needed).
- Avoid actions that change message state: do not archive, delete, mark-as-read, or send replies while extracting data unless explicitly requested.
- If the message list is long, scroll slowly so all rows load before capturing or extracting; you may limit extraction to a reasonable maximum (e.g., 200 messages) to keep JSON manageable.
- When saving filenames, include the date (YYYYMMDD) to avoid overwriting prior runs.
