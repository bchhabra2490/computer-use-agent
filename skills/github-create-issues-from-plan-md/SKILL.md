---
name: github-create-issues-from-plan-md
description: >-
  Converts top-level bullets or top-level headings in a repository's plan.md into GitHub issues on the repository's origin remote, pausing for user confirmation before creating any issues. Use when you keep project plans locally and want reproducible issue creation tied to the repo's origin.
---

## Steps

1. Locate the repository folder on macOS
   - Check common places (~/Desktop, ~/Documents, ~/Downloads, ~/Developer, ~/Projects, ~/code, ~/src, ~/workspace) using Finder or Terminal.
   - Terminal example: find "$HOME" -maxdepth 5 -type d -name '<repo-name>' 2>/dev/null

2. Verify the repo and open plan.md
   - Confirm it's a git working directory: git -C /path/to/repo rev-parse --show-toplevel
   - Print the file: cat /path/to/repo/plan.md
   - If plan.md is not present, stop and ask the user.

3. Extract top-level items
   - Preferred: extract first-level Markdown bullets (lines starting with a single leading '- ' or '* ' at column start) only.
   - If the file has no first-level bullets but uses top-level numbered headings/track headings (e.g., top-level headings or numbered section titles), treat each top-level heading as a proposed issue title instead.
   - Include any nested sub-bullets or paragraph lines that logically belong to that top-level item into the issue body (keep indentation/formatting).
   - Example (bash/python approach): parse lines that match ^-\s+ or ^\*\s+ or top-level heading markers ^#{1}\s+ (or numbered headings) and collect subsequent indented/sub lines.

4. Prepare proposed issues
   - For each extracted top-level item create a proposed issue title: use the full top-level text.
   - If a title exceeds 250 characters, truncate the title to 250 chars and put the full original text into the issue body.
   - Stop and present a progress update to the user listing each extracted item and the proposed issue title/preview. Pause here and require explicit confirmation before creating issues.

5. Determine GitHub remote repository
   - Find repo origin: git -C /path/to/repo remote get-url origin
   - If multiple remotes or ambiguous origin, ask the user to pick which remote to use.
   - Normalize origin to owner/repo slug (supports ssh git@github.com:owner/repo.git and https://github.com/owner/repo.git).

6. Create issues on GitHub (after user confirmation)
   - Recommend using GitHub CLI (gh) or the GitHub REST API with an authenticated token.
   - gh CLI example for each item:
     - export GITHUB_TOKEN=... (or gh auth login)
     - gh issue create --repo owner/repo --title "<title>" --body-file <tmpfile>
   - Ensure no labels or assignees are added.
   - Collect and return the created issue URLs.

7. Final report
   - Return a summary listing created issues with links.
   - If any items were skipped or failed, list errors and next steps.

## Error handling & user prompts

- If plan.md is missing: inform the user and stop.
- If the file contains no first-level bullets: show the top-level headings and ask whether to treat headings as issue titles.
- If there are multiple remotes or unclear origin: prompt the user to choose the remote.
- If the system lacks gh or a valid GitHub token: prompt the user to run `gh auth login` or export GITHUB_TOKEN.
- If a title >250 chars: truncate title to 250 chars and put full text in the body.
- Pause and require explicit user confirmation (showing the proposed titles) before creating any issues.

## Tips

- Use a small Python script to reliably parse Markdown (handle both '- ' bullets and top-level headings) and write each issue body to a temp file for gh to consume.
- Keep exact whitespace/indentation for sub-bullets in the issue body to preserve structure.
- For reproducibility, record which origin URL was used and save the extracted items locally (e.g., /tmp/plan_to_issues.json).
- If automating, run commands under a shell with set -euo pipefail and capture failures; ask the user to inspect before batch-creating when many items exist.

## Example commands (macOS Terminal)

- Find repo: find "$HOME" -maxdepth 5 -type d -name 'agent' 2>/dev/null
- Verify origin: git -C /path/to/repo remote get-url origin
- Show plan: sed -n '1,200p' /path/to/repo/plan.md
- Create issue with gh: gh issue create --repo owner/repo --title "Short title" --body-file /tmp/issue_body.md

Use this skill when you want a reproducible, confirmable conversion of a local plan.md into GitHub issues tied to the repository's origin. The skill will always pause for user confirmation before creating issues.
