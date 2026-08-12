---
name: hn-edit-submission
description: >-
  Edits an existing Hacker News submission (title and post/comment) in Google Chrome on macOS: opens the submission or finds the user's post, opens the edit form (or the user's post-comment edit for link posts), replaces title and/or body exactly as provided, saves changes, verifies the saved page, captures a screenshot, and copies the canonical post URL to the clipboard. Use when you need to update a previously submitted HN post.
---

## Steps

1. Preconditions:
   - Use Google Chrome on macOS and be signed into the correct HN account. If not signed in or an auth/2FA prompt appears, stop and report.

2. Locate the submission:
   - If the user supplied a post URL, focus the address bar (Cmd+L), paste (Cmd+V) and open it (Enter).
   - If no URL, open the user’s HN profile or the post list and find the intended submission.

3. Open the edit form:
   - On the post line (the title line showing e.g. "1 comment | edit"), click the small “edit” link to open the edit form.
   - If the edit link is not on the list view, open the post page (click title) and look for an “edit” link there.
   - If you cannot find any edit link, stop and report (edits may be disallowed or you may be using a different account).

4. Determine fields available:
   - If the edit form shows a Title and Text/Body field, proceed to replace both as instructed.
   - If the edit form shows only Title (this is usual for link posts), the original submission body is instead a separate comment. In that case:
     a. Open the post page and find the user’s original comment (usually the first comment by the submitter).
     b. Click the comment’s “edit” link to open the comment edit form, and replace the comment text exactly as instructed.

5. Respect HN title limits:
   - Hacker News enforces an 80-character title limit. Before replacing the title, verify the provided title length.
   - If the requested title exceeds 80 characters, do NOT save a truncated title without asking the user. Pause and report the exact character overage and offer a suggested shortened title.

6. Replace text exactly:
   - Click into the title field, select all (Cmd+A) and paste/type the exact requested title.
   - Click into the Text/Body (or comment) field, select all (Cmd+A) and paste/type the exact requested body text.

7. Save changes:
   - Click the “update” button (or the comment’s update/save control). Wait for the page to reload or confirm the changes.

8. Verify and capture artifacts:
   - Reload the post page (Cmd+R) and confirm the title and body/comment show exactly as requested.
   - Capture a screenshot of the updated post page (use Cmd+Shift+3 for a full-screen macOS screenshot or a browser/extension screenshot).
   - Copy the post URL to the clipboard (Cmd+L, Cmd+C) and record it for return to the user.

9. Report back:
   - If any authentication or permission errors occur (login required, 2FA, edit disabled), stop and report immediately with the prompt details.
   - Provide a short mid-task update when encountering user-visible blockers (e.g., title-length rejection) and a final confirmation including the URL and screenshot path or confirmation that a screenshot was captured.

## Tips

- Always verify you’re editing while signed into the correct HN account; editing isn’t allowed when unauthenticated.
- Don’t auto-truncate titles: inform the user and offer a shorter approved alternative if the 80-char limit is exceeded.
- Link posts often require editing the submitter’s first comment rather than the submission form—check the post page when the edit form lacks a body field.
- Use Cmd+L then Cmd+C to reliably copy the canonical Hacker News item URL from the address bar.
- Use macOS screenshot shortcuts (Cmd+Shift+3 or Cmd+Shift+4) and then locate the most recent screenshot on Desktop/Downloads to attach or provide to the user.
- If you need to automate repeated edits, batch the edits by collecting titles/bodies first and confirm with the user before saving any changes.

When to use this skill: when you need to update an existing Hacker News post (title or body/comment) on macOS. When not to use: trivial single-click tasks, posting a new submission (use hn-submit-repo), or one-off local checks that don't require saving edits on HN.
