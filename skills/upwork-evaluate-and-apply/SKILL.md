---
name: upwork-evaluate-and-apply
description: >-
  Evaluates an Upwork job posting against the user's stored profile and, if the match is good, completes the Upwork application flow on macOS: set hourly rate within the client's budget, paste a concise personalized cover note, attach the user's resume file, verify the application email, submit the application, and capture verification screenshots. Use when you routinely apply to Upwork job posts and want a reproducible, careful apply flow that includes an explicit suitability check.
---

## Steps

1. Bring Google Chrome to the front and open the Upwork job tab or the job URL.
   - Shortcut: click the Chrome window or use Spotlight (Cmd+Space) → type "Chrome" → Enter.

2. Ensure the job page is fully loaded. If you see a spinner or incomplete rendering, hard-refresh the tab (Shift+Cmd+R). If that fails, copy the URL (Cmd+L, Cmd+C), open a new tab (Cmd+T), paste (Cmd+V) and press Enter.

3. Scroll to the top of the job page (use the trackpad or press Home/scroll) and read the full job description, responsibilities, and required skills sections. Expand any collapsed sections.

4. Compare the job's required skills and responsibilities with the stored profile/resume:
   - Open the user's stored profile/memory or resume (read from known path e.g. ~/Downloads/Resume.pdf or the agent's stored profile via read_memory) and verify core matches (e.g., JavaScript, Node.js, React, AWS, PostgreSQL, Redis).
   - If >=70% of the key required skills match the user profile and responsibilities are within the user's experience, proceed. Otherwise stop and report unsuited.

5. Confirm the client's budget or hourly-range on the right-side/job header. Choose an hourly rate inside the posted range and that aligns with the user's preference (recommend setting to the upper-mid of the client's range to increase competitiveness if acceptable). Example keyboard entry: click the rate input, Cmd+A, type the numeric hourly rate (e.g., "25").

6. Compose a short personalized cover note (3–5 lines) that highlights the match:
   - Use a template: "Hi — I’m <Name>, a Full‑Stack engineer with ~<years> years building <stack>. I have direct experience with <key required tech> and can start immediately. I propose $<rate>/hr and am available for a quick call to discuss next steps." 
   - Replace placeholders with values from the stored profile (name, years, key tech). Click the cover letter field and paste the tailored text.

7. Attach the resume file:
   - Click the resume/attachment button.
   - In the file picker, press Cmd+Shift+G, paste the full path to the resume (for example: /Users/b-eq/Downloads/Resume.pdf), press Enter, select the file and confirm (double-click or click Open).
   - Wait for the UI to show the file is attached (filename or thumbnail).

8. Verify the application email/contact is correct:
   - Open the application-email selector (if available) and ensure it matches the user's intended application email (from memory/profile). If it's wrong, change it to the correct one.

9. Check for additional client questions or required answers; fill them with brief, honest answers derived from the resume/profile. If any question requires new information you don't have or looks ambiguous, stop and report for manual review.

10. Capture a pre-submit screenshot of the filled application (use the system screenshot shortcut: Cmd+Shift+4 then Space to capture the focused window, or let the agent capture via its screenshot action). Save or keep the screenshot for verification.

11. Submit the application:
   - Click the Apply/Submit button.
   - If Upwork prompts for confirmation, review and confirm.
   - If 2FA, CAPTCHA, or a wallet/payment confirmation appears, pause and report to the user for manual completion.

12. After submission, capture a post-submit screenshot of the confirmation page or application list showing the applied job. Copy the canonical job URL to the clipboard (Cmd+L, Cmd+C) and record the application status.

13. Report back a short summary: whether the job matched the profile, the hourly rate set, the cover note used, the resume attached (path), and the post-submit confirmation screenshot and URL. If you stopped for any ambiguous prompt (2FA/CAPTCHA/questions), state why and wait for user action.

## Tips

- Keep the cover note tailored but concise — clients skim these.
- Prefer an hourly rate inside but near the upper half of the client's range if the user's profile strongly matches.
- If the job requires a fixed-price proposal with a delivery timeline, adapt steps to set the proposed budget and add a short timeline sentence in the note.
- Stop and ask the user if: required skills diverge from the profile, custom questions need factual answers not in memory, or Upwork requires payment/identity steps.
- Use Cmd+Shift+G to quickly navigate file pickers to a known resume path to avoid browsing through Finder folders.
- Save screenshots (pre- and post-submit) to the Desktop or the agent's usual artifacts folder for auditability.
