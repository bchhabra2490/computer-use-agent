---
name: git-merge-branch-into-main-with-backup
description: >-
  Performs a safe merge of a named remote/local feature branch into main on macOS: ensures repo presence (cloning if needed), fetches remotes, creates a timestamped safety branch, merges (no-ff or squash), detects conflicts and stops for manual resolution, pushes main, and reports the merge commit SHA.
---

## Steps
Note: Use MCP if possible, otherwise

1. Open Terminal.

2. Define or confirm the repository path. Default used by this skill:

   repo="$HOME/code/computer-use-agent"

   If the repo is in a different location, ask the user and set `repo` accordingly.

3. Ensure the repo exists locally; if not, clone the canonical origin and cd into it:

   cd "$HOME" || exit 1
   if [ ! -d "$repo/.git" ]; then
     git clone https://github.com/bchhabra2490/computer-use-agent.git "$repo"
   fi
   cd "$repo"

4. Fetch all remotes and prune deleted refs:

   git fetch --all --prune

5. Update main to the latest remote tip (work on a clean working tree):

   git checkout main
   git pull origin main

   If `git checkout main` fails because the branch name differs, inspect branches with:
   git branch -a

6. Create a timestamped safety branch from the current main (do not modify main directly):

   backup="main-backup-merge-$(date +%Y%m%d-%H%M)"
   git checkout -b "$backup"

   Note the exact backup branch name for potential rollback.

7. Return to main and prepare to merge:

   git checkout main

8. Determine the correct feature branch to merge.
   - If a local branch exists named `phone-gateway`, merge that.
   - If not, find candidate remote branches (examples):

     git branch -r --list '*phone*'

   - Common remote form: `origin/feature/phone-gateway`. Confirm with the user before merging if the local/remote name differs.

9. Perform the merge. Prefer a non-fast-forward merge to preserve history:

   # Non-FF merge from a local branch
   git merge --no-ff phone-gateway

   # Or, if merging directly from the remote-tracking branch
   git merge --no-ff origin/feature/phone-gateway

   If you prefer a single squashed commit instead of preserving intermediate commits:

   git merge --squash origin/feature/phone-gateway
   git commit -m "Squash-merge feature/phone-gateway into main"

10. If conflicts occur, stop and notify the user immediately. To detect conflicts and list conflicting files:

   # detect merge exit code and conflicting files
   if [ $? -ne 0 ]; then
     echo "MERGE_CONFLICT"
     git diff --name-only --diff-filter=U
     # Do NOT attempt to resolve automatically. Wait for user instructions.
     exit 1
   fi

   Alternatively, after a merge attempt you can run:
   git status --porcelain
   git diff --name-only --diff-filter=U

11. If the merge completed cleanly, record the merge commit SHA and subject, then push main to origin:

   MERGE_SHA=$(git rev-parse HEAD)
   MERGE_SUBJECT=$(git log -1 --format=%s)
   echo "MERGE_SHA=$MERGE_SHA"
   echo "MERGE_SUBJECT=$MERGE_SUBJECT"

   git push origin main

12. Report back to the user with:
   - Whether the merge succeeded or had conflicts
   - The merge commit SHA (when successful)
   - The backup branch name (e.g. main-backup-merge-YYYYMMDD-HHMM)

## Tips

- If the script cannot find the expected branch name, ask the user which remote/local branch they intended to merge; do not guess and do not merge any similarly-named branch without confirmation.

- If a conflict occurs, do NOT auto-resolve. Provide the list of conflicted files (git diff --name-only --diff-filter=U) and wait for user instruction. To abort a problematic merge you can run: `git merge --abort`.

- To restore the pre-merge main state from the backup branch locally:
  git checkout main
  git reset --hard "refs/heads/$backup"
  (or force-push the backup if you need to restore origin: `git push --force origin "$backup":main` — require explicit user confirmation before forcing origin.)

- Prefer merging the remote-tracking branch (origin/feature/...) when a local tracking branch is not present; this avoids accidental merges of local work-in-progress branches.

- Always show and record `git rev-parse HEAD` after a successful merge so you can report the exact commit SHA.

- If the repo path differs from the default, prompt the user and repeat the same steps after cd into the chosen path.

This skill intentionally stops and prompts on any conflicts or ambiguous branch-name situations so the user can decide how to proceed.
