---
name: google-maps-share-directions-to-desktop-chat
description: >-
  Opens Google Maps on macOS, gets driving directions from the current location (or a specified origin) to a named destination, copies the shareable directions link, switches to a desktop chat app (e.g. WhatsApp Desktop), opens a specified conversation, pastes the link into the message box, and sends it. Use when you want to share driving directions from the Mac to a chat conversation.
---

## Steps

1. Open Google Maps with directions preloaded for the destination:
   - Construct a directions URL like `https://www.google.com/maps/dir/?api=1&destination=<DEST>&travelmode=driving` (URL‑encode the destination) and open it in the default browser (e.g. Chrome) or use Spotlight/Chrome to open maps.google.com and enter the destination.
2. Wait until the directions panel (left side) shows route options and step-by-step directions. Verify you can see the route list or the left-hand panel with controls (Share / Copy link / Send directions).
3. Copy a shareable directions link:
   - In the left directions panel click the "Share" or "Copy link" control. If a modal appears, click the modal's "Copy link" button. If a one-click "Copy link" control is visible in the panel, click that.
   - Confirm the link is on the clipboard by pasting into a safe temporary spot (e.g., Notes) or rely on the UI confirmation that the link was copied.
4. Switch to the desktop chat application where you want to send the link (WhatsApp Desktop, Slack, Messages, etc.):
   - Use Cmd+Tab or click the app in the Dock. Bring the chat app to the front.
5. Open or select the intended conversation:
   - If the chat app shows a contact list, click the contact/chat thread you want, or use the app's search field to find the recipient and open the chat.
6. Paste and send the directions link:
   - Click the message input box, press Cmd+V to paste the Maps link, and press Enter (or click Send) to send the message.
7. Verify the recipient sees the link (optional):
   - Look for the sent message in the thread and a clickable preview if the chat app generates one.

## Tips

- If you prefer to specify an origin rather than current location, add `&origin=<ORIGIN>` to the directions URL.
- On slow pages or if the left panel fails to render, try reloading the Maps tab or open Maps in a new browser tab.
- If the chat app is not WhatsApp Desktop, the same steps apply; the only differences are how you select the conversation (search vs. clicking a thread) and how the app sends messages (Enter vs. a Send button).
- If Maps prompts for location permission and you want to use the true current location, allow location access in the browser or supply an explicit origin in the URL.
- When automating, avoid long fixed sleeps; instead confirm UI elements are present (directions panel, share button, chat input) before proceeding.
