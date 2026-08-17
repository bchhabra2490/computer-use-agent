---
name: github-delete-branch-via-ui
description: >-
  Deletes a specified branch from a GitHub repository using Google Chrome on macOS, confirms the deletion, verifies the branch no longer appears, captures a screenshot of the post-deletion branches page, and copies the branches page URL to the clipboard.
---

## Steps

1. Open Google Chrome (Cmd+Space → type "Google Chrome" → Enter).
2. Navigate to the repository branches page: focus the address bar (Cmd+L), paste or type the branches URL (e.g., https://github.com/OWNER/REPO/branches), and press Enter.
3. Wait for the branches page to finish loading. If a spinner hangs, reload (Cmd+R) and wait.
4. If the page is scoped (tabs like "Yours", "Active", "All"), click the appropriate tab (usually "Active" or "All") to ensure the branch list is visible.
5. Click the "Search branches…" input on the branches page, type the exact branch name to find (e.g., feature/mcp-integration), and wait for results.
6. If the branch appears in the list, move to the branch's row and click the delete/trash icon at the far right of that row.
7. In the confirmation dialog that appears, click the confirm button (labelled e.g. "Delete branch" or "Delete").
8. Wait for the page to update/refresh. If the page does not refresh automatically, reload (Cmd+R) and wait.
9. Verify the branch is gone by clearing/focusing the "Search branches…" box and re-searching the branch name; confirm no results are returned.
10. Capture a screenshot of the branches page showing the branch absent (use the system screenshot or the automation’s screenshot action).
11. Copy the branches page URL to the clipboard (Cmd+L → Cmd+C) and confirm the exact URL was copied (optional: paste into a temporary editor to verify).
12. Save or attach the screenshot and report the outcome: whether the branch was deleted, any errors encountered, and the branches page URL.

## Tips

- If you are not signed in to the correct GitHub account, sign in first; the branches page will present sign-in prompts or missing controls.
- If the repository protects the branch (protected branch rules), the delete icon may be absent or disabled; report that the branch cannot be deleted via the web UI and suggest deleting via git (e.g., git push origin --delete <branch>) or removing protection rules first.
- If multiple matching branch rows appear, confirm the exact branch by clicking the branch name and verifying the branch name shown on the branch page before deleting.
- If a confirmation dialog does not appear after clicking the trash icon, check for a browser popup blocker or for an inline confirmation element; look for buttons labeled "Delete branch", "Confirm", or similar.
- When automating, prefer using the visible trash icon at the row's far right (not any inline caret menus) to reduce ambiguity; if the UI layout differs, use the branch row context menu to find the delete action.
- Always take a post-action screenshot and copy the URL to the clipboard so there is verifiable evidence of the deletion or of any error state.

Use this skill when you need to remove a named branch from a GitHub repository via the Chrome browser on macOS and produce verification artifacts (screenshot + branches page URL).
