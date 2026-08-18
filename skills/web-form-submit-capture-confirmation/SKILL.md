---
name: web-form-submit-capture-confirmation
description: >-
  Brings a specific web form tab forward on macOS, detects whether the form is already submitted, saves a pre-submit screenshot if needed, submits the form, detects interactive blocks (CAPTCHA/login/file-size), captures the post-submit confirmation screenshot, and provides short audible updates. Use when a repeatable end-to-end web-form submission + verification is required.
---

## Steps

1. Identify the target tab or URL to act on (parameterize as <url> or a tab title). Bring Google Chrome to the front and switch to the tab with the target URL. If the tab is not open, open the URL in a new Chrome tab.

2. Check the page for submission-confirmation markers (case-insensitive): words/phrases like "thank you", "submission received", "thanks for", "we received your", "your submission", a reference/confirmation number, or a clear success/thank-you page layout. Also check for an explicit confirmation element (e.g., a centered message or a visible success card).

3. If a confirmation is already visible:
   - Capture a screenshot of the Chrome window showing the confirmation (use macOS screenshot of the frontmost Chrome window: Cmd+Shift+4, then Space, then click the Chrome window) or the automated screenshot tool available in your assistant environment.
   - Save the image to the assistant memory/screens store with the exact name provided by the caller (example parameter: <confirmation-name>, e.g. "parsewave-submission-confirmation").
   - Announce audibly: "Confirmation screenshot saved."
   - End the task.

4. If the form is still filled but not submitted:
   - Take a pre-submit screenshot and save it to memory/screens under the provided pre-submit name (example: <pre-submit-name>, e.g. "parsewave-filled-form").
   - Locate the visible submit button (look for buttons or inputs with text like "Submit", "Send", "Apply", "Finish"). If multiple candidates exist, prefer the visible primary button near the bottom of the form.
   - Before clicking, ensure no interactive block is present (see step 6). If safe, click the submit button and immediately speak the audible update: "Upload and submit confirmed."

5. After clicking submit, wait for navigation or the confirmation content to load. Use a short timeout (for example, 30 seconds) and check for the confirmation markers described in step 2. When confirmation appears:
   - Capture a screenshot of the confirmation and save it to memory/screens using the provided confirmation screenshot name (example: "parsewave-submission-confirmation").
   - Announce audibly: "Confirmation screenshot saved."
   - End the task.

6. If an interactive block prevents submission at any point (examples: CAPTCHA or reCAPTCHA iframe visible, a login/sign-in prompt, explicit file-size / upload error message, or other modal requiring user interaction):
   - Do not attempt to bypass it.
   - Speak aloud exactly: "I still can’t submit — there’s an interactive block. Would you like help resolving it?"
   - Stop and wait for the user's instructions.

7. Safety / typing note: never press and hold the 'D' key while typing (do not use long key-holds that could trigger unwanted repeated input).

8. When saving screenshots to memory/screens, use exact names provided by the caller and include a small metadata note if possible (URL acted on, timestamp).

## Tips

- Detection hints: confirmation pages often change the page title to include "thank you" or "confirmation"; check document.title as a secondary signal.
- Use keyboard shortcuts to bring Chrome frontmost: Cmd+Tab, then cycle to the correct Chrome window/tab. Use Cmd+L to focus the address bar and paste the URL if switching to a tab by URL is easier.
- For reliable screenshots of just the page content, prefer capturing the Chrome window (Cmd+Shift+4 → Space → click window) rather than a dragged area.
- If the submit action triggers a file upload step or progress indicator, wait until the spinner or progress completes before checking for confirmation.
- Parameterize the skill with: <url or tab-title>, <pre-submit-name>, <confirmation-name>, and an optional timeout value.

Use this skill when you need a repeatable, safe flow to finish and verify a browser-based form submission on macOS and capture evidence of both pre-submit and post-submit states.
