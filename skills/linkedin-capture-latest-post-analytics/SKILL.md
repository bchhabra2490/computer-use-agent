---
name: linkedin-capture-latest-post-analytics
description: >-
  Opens the user's LinkedIn profile in Chrome, navigates to Activity → Posts, opens the most recent post, opens the post analytics (views/insights), captures impressions/views plus reactions and comments if visible, copies the canonical post URL to the clipboard, and saves screenshots of the post and analytics. Use when you need the latest post metrics and verification artifacts from a logged-in LinkedIn account on macOS.
---

## Steps

1. Open Google Chrome (use Spotlight: Cmd+Space → type "Google Chrome" → Enter). If Chrome is not available, open the system default browser.
2. Navigate to https://www.linkedin.com and ensure the user is signed in with the expected account. If LinkedIn prompts for sign-in or 2FA/OTP, pause and notify the user before proceeding.
3. From the LinkedIn top bar, open the profile: click the "Me" avatar and select "View profile" (or click your profile name/photo). Wait for the profile page to finish loading. If a spinner hangs for >10s, reload the page and wait again.
4. Scroll the profile until you see the Activity section. Click the "See all activity" / "Show all activity" / "Activity" link to open the Activity page.
5. On the Activity page, click the "Posts" tab (or "Posts & activity") to list posts. Wait until the posts list renders and any loading indicators finish.
6. Identify the most recent post (top of the list). Open that post in the canonical post view by clicking the post preview or the "View post" link.
7. Locate and open the post analytics: click the visible "views" / "analytics" / "View analytics" link under the post (or open the three‑dot menu on the post and choose any "View analytics" / "View post insights" option). If the analytics open in a pane/dialog, wait until numbers render; if nothing appears, try the three‑dot menu.
8. Record these values if present and visible in the analytics pane or under the post content:
   - Impressions / views (exact displayed number)
   - Reactions (number of likes/celebrates/insights etc.; sum if LinkedIn shows totals)
   - Comments (number next to the comment icon)
9. Copy the canonical post URL to the clipboard: focus the address bar (Cmd+L) then Cmd+C. If LinkedIn provided a shortened/utm URL, clean it to the canonical permalink (URL path that looks like /posts/<username>_.../...) before copying.
10. Save two screenshots to the Desktop:
    - Desktop/linkedin-latest-post.png: visible post page (showing reactions/comments under content)
    - Desktop/linkedin-latest-post-analytics.png: the analytics pane/dialog showing impressions/views and any demographic/insight numbers
    Use macOS screenshot utilities (screencapture or browser screenshot) and ensure the window is frontmost and unoccluded.
11. Verify the clipboard contains the canonical post URL (paste to a safe place or use pbpaste). If not correct, recopy (Cmd+L → Cmd+C).
12. Return the recorded impressions/views, reactions, comment counts, the canonical URL, and attach the saved screenshots as verification artifacts.

## Tips

- If the Activity section or Posts tab is labelled slightly differently ("All activity", "Posts & activity"), choose the item that lists individual posts.
- If a spinner or partial load persists, reload (Cmd+R) and wait up to ~20s for content to render. Try clicking the post preview if the "View post" toast disappears.
- If the analytics open in a modal overlay that hides the page, move the overlay if necessary to capture both analytics and post context in screenshots, or save separate screenshots as described.
- If analytics are not available for the latest post (LinkedIn sometimes delays insights), note that explicitly and still copy the post URL and take the post screenshot.
- Preserve screenshot filenames exactly as above to make downstream retrieval predictable. Ensure screenshots are saved to the user Desktop and confirm existence before finishing.
- Pause and ask the user if LinkedIn requires re-authentication or a 2FA/OTP step before proceeding.
