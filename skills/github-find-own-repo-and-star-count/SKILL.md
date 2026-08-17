---
name: github-find-own-repo-and-star-count
description: >-
  Finds a repository in the user's GitHub account matching specified keywords (or lists the 5 most-recently-updated repos if none match) and returns the repository full name (owner/repo) and the exact star count. Use when you need to verify or report the star count of a repo you own from a Mac desktop.
---

## Steps

1. Open the web browser on macOS:
   - Press Cmd+Space, type "Google Chrome" (or "Safari" if you primarily use Safari), and press Enter to open it.
2. Go to GitHub:
   - Press Cmd+L, type `https://github.com`, and press Enter. Wait for the page to finish loading.
3. Confirm you are signed in:
   - Look at the top-right of the page for your avatar/profile picture. Do NOT sign out or change account settings.
4. Open your repositories list:
   - Click the avatar and choose "Your repositories" from the dropdown, or open `https://github.com/your-username?tab=repositories` (replace `your-username` if you prefer).
5. Search the repositories page for keywords:
   - Press Cmd+F and search each keyword one at a time: `computer`, `use`, `usage`, `agent`, `computer-use-agent`.
   - For any search hits that look like candidates, open that repository in a new tab by Cmd+clicking the repo name (or right-click → Open in New Tab).
6. If multiple candidate repos were opened, inspect each candidate tab:
   - For each candidate, open the tab and load the repository's main page.
7. For the repo that is the computer-use agent you own (or for each candidate if requested):
   - Copy the repository full name: press Cmd+L to focus the address bar, copy the path portion of the URL (the `owner/repo` segment after `https://github.com/`). Example: from `https://github.com/owner/repo` copy `owner/repo`.
   - Find the exact star count: look for the `Star` button near the top-right of the repository page; the exact star count appears adjacent to it. Select that number and copy it exactly as shown (do not round or abbreviate).
8. If no repositories match those keywords:
   - On the Repositories page, identify the top 5 repositories ordered by most recent update (the page shows update times). Copy the names of those top 5 for user confirmation.
9. Return to this chat and paste the repository full name and the exact star count (or the top-5 repo names if none matched). Append the word `done` on its own line after the pasted result.

## Tips

- Opening candidate repos in new tabs (Cmd+click) keeps the Repositories list in place so you can continue searching.
- To avoid mistakes extracting `owner/repo`, use the URL bar (Cmd+L) and copy only the path after `github.com/`.
- The star count may be formatted with commas (e.g., `1,234`) or abbreviated on some GitHub UI variants; copy exactly as displayed on the repo page.
- Do not change account settings, star/unstar repositories, or sign out while performing this workflow.
- If you are not signed in (no avatar visible), stop and report the sign-in state rather than attempting to sign in.
