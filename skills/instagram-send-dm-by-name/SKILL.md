---
name: instagram-send-dm-by-name
description: >-
  Sends a Direct Message on Instagram from Chrome on macOS by searching a recipient name; pauses to ask the user when multiple matches or no matches appear, and handles sign-in/2FA when needed.
---

## Steps

1. Open Google Chrome
   - Press Cmd+Space, type "Google Chrome", press Enter.

2. Go to Instagram
   - Press Cmd+L, type `https://www.instagram.com`, press Enter.

3. Ensure you are signed in
   - If Instagram shows a login page, sign in with the current macOS user’s account.
   - If 2FA/OTP is required, pause and ask the user for the code; enter it to complete sign-in.

4. Open Direct Messages (DMs)
   - Click the paper-plane icon (Direct) in the top-right or navigate to `https://www.instagram.com/direct/inbox/`.

5. Start a new message
   - Click the New Message / pencil-compose icon (usually near the top-left of the inbox).

6. Search for the recipient by name
   - In the recipient search field, type the target display name (e.g., `Bhaskar`).
   - Wait for the suggestion list to populate.

7. Branching behavior
   - If multiple matching accounts appear: pause and ask the user which account to choose (show handles/usernames from the list). Do not proceed until the user selects one.
   - If no results appear: pause and ask the user for the recipient’s exact Instagram username; then enter that username in the search field.

8. Select the correct recipient
   - Click the chosen username in the suggestion list to add them to the new message.
   - Click "Next" or the equivalent button to open the message thread.

9. Compose and send the message
   - Type the exact message text provided by the user (do not alter punctuation/capitalization). Example: `Bhaskar, please stop watching reels.`
   - Press Enter (or click Send) to send the message.

10. Confirm delivery and report back
   - Verify a sent message bubble with the exact text appears in the thread and/or the inbox preview shows the recent message (e.g., "You: <message> · 1m").
   - If everything was sent successfully, report confirmation and the recipient’s handle. If there were errors (sign-in failed, 2FA failed, recipient not found), report the specific error and any paused prompts you presented to the user.

## Tips

- If the user’s Chrome is already signed into a different Instagram account, confirm with the user before sending.
- For reliability use the DM inbox URL (`/direct/inbox/`) if the icon is not visible.
- Pause and request explicit user input whenever the correct recipient isn’t unambiguous or when authentication/2FA is required.
- If Instagram rate-limits or blocks messaging, capture the error text and report it to the user.
- Keep the message text exactly as provided; do not paraphrase.

(This skill assumes interaction in Google Chrome on macOS and that the user will supply choices or 2FA codes when prompted.)
