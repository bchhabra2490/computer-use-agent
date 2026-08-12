---
name: hn-submit-repo
description: >-
  Submits a repository URL to Hacker News from macOS: finds a repo URL (editor/terminal/browser), opens the HN submit form in Chrome, fills URL/title/body (respecting HN title limits), posts using the currently logged-in account, opens the new post, captures a screenshot, and copies the post URL. Use when you want to share a repo on Hacker News from the desktop and save verification artifacts.
---

## Steps
1. Locate the repository URL to share:
   - Check open browser tabs (look for GitHub/GitLab/Bitbucket). If found, prefer a public GitHub URL whose README or name mentions the project.
   - If not obvious, check the open code editor window for a README or package metadata showing the remote URL.
   - If still uncertain, switch to Terminal (or an integrated terminal) and run: `git remote -v` in the project directory to reveal the public remote URL.
   - Confirm the chosen URL is the public repo to post.

2. Open Hacker News submission form in Google Chrome:
   - Bring Chrome to front (Spotlight: Cmd+Space → type "Google Chrome" → Enter, or use the `open-app` flow).
   - Navigate to: `https://news.ycombinator.com/submit` (Cmd+L, type/paste URL, Enter).

3. Fill the submission fields:
   - Paste the repository URL into the URL field.
   - Title rules: Hacker News limits titles to 80 characters. If your preferred title is longer, craft an equivalent accurate title ≤80 chars. Example: `computer-use-agent — an AI agent that controls desktops for UI tasks (GitHub)`.
   - Body: paste or type the short description you want. Example body text:
     "This is the repo for the computer-use agent I'm using now. It enables an AI to control mouse and keyboard, take screenshots, and interact with apps to automate UI tasks. I'm sharing it to get feedback and discuss use-cases and safety."
   - If the post should explicitly state it was posted by the agent itself, append a short note in the body such as: "This is being posted by the agent itself." (only if appropriate).

4. Submit the post:
   - Click the "submit" button on the form and wait for the page to load.
   - If Hacker News prompts for additional authentication (login, 2FA, captcha), STOP and report back immediately — do not attempt to bypass authentication.

5. Open and verify the new post:
   - After the submission, open the posted discussion page (it usually appears in "newest").
   - Copy the post URL from the address bar: Cmd+L then Cmd+C.

6. Capture verification artifacts:
   - Take a screenshot of the post page and save it (use macOS screenshot: Cmd+Shift+4 → Space → click the Chrome window; the image is saved to Desktop by default, or use any preferred screenshot tool).
   - Attach or save the screenshot alongside the copied URL for records.

7. Report completion:
   - Provide the HN post URL and the screenshot.
   - If any step failed or required authentication, report the exact failure and stop.

## Tips
- Prefer a clearly public GitHub repo (public remote, README mentions project) when multiple candidates exist.
- Keep the title concise; verify it is ≤80 characters before submitting.
- If multiple logged-in HN accounts appear or login is required, pause and ask the user which account to use or request credentials — do not try to guess.
- Wait for the HN page to finish loading before copying the URL or taking the screenshot to avoid capturing a redirect or an incomplete page.
- If you need to capture a cleaner full-page screenshot rather than the visible window, consider using a Chrome extension or the browser's developer tools capture feature instead of the macOS window screenshot.
- Always stop and report if any authentication prompt, 2FA, or captcha appears.
