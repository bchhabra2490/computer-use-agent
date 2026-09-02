---
name: rotate-and-clear-browser-sessions
description: >-
  Clears cookies, site data, and session storage and creates a fresh browser profile to rotate sessions on macOS. Use when the user needs to remove all logged-in sessions and start a new browsing session or profile.
---

## Steps

Note: These steps cover the three common macOS browsers (Google Chrome, Safari, Mozilla Firefox). Perform them for each browser you use. Back up any passwords or site data you need before proceeding.

A. General preparation

1. Save any work in browser tabs (copy important URLs or use a bookmarking method).
2. Close unneeded tabs so you can confirm sign-outs after clearing data.

B. Google Chrome (clear all site data and create a new profile)

1. Bring Google Chrome to the front (click its Dock icon or use Spotlight: Cmd+Space, type "Chrome", Enter).
2. Verify which profile is active by clicking the profile avatar in the top-right of the Chrome window.
3. To clear all cookies/site data for the active profile:
   - In the address bar, go to chrome://settings/clearBrowserData and press Enter.
   - In the dialog that appears, switch to the "Advanced" tab.
   - Set the time range to "All time."
   - Check at minimum: "Cookies and other site data" and "Cached images and files." Optionally check "Site settings" and "Hosted app data."
   - Click "Clear data."
4. To remove any remaining site-specific storage (localStorage / IndexedDB) across sites:
   - Open chrome://settings/siteData and press Enter.
   - Click "Remove all" (Confirm the prompt) to delete all site data for the profile.
5. Create a new, clean Chrome profile to rotate sessions (so you have an isolated, logged-out session):
   - Click the profile avatar in the top-right and choose "Add."
   - Choose "Continue without an account" (or "Browse as a guest" for a temporary session) to avoid signing in. Give a name and avatar. Click "Done."
   - A new Chrome window opens for that profile. Use that window as the rotated/clean session.
6. (Optional) Remove the old profile if you no longer need it:
   - Click the profile avatar → Manage people (or the gear icon next to Profiles) → click the three-dot menu on the old profile → Remove this person. Confirm. Note: removing a profile permanently deletes that profile's local data.
7. Restart Chrome (Cmd+Q then reopen) and spot-check by visiting a site where you expect to be logged out.

C. Safari (clear cookies, website data, and rotate by using a fresh Safari profile equivalent)

1. Bring Safari to the front.
2. Open Safari → Settings (Cmd+,) → Privacy tab.
3. Click "Manage Website Data…" and then click "Remove All." Confirm to delete cookies and website data.
4. To clear caches (if the Develop menu is available):
   - If Develop is not enabled: Safari → Settings → Advanced → check "Show Develop menu in menu bar."
   - From the menu bar choose Develop → Empty Caches.
5. Safari does not support multiple persistent UI profiles like Chrome. To get a fresh session, either create a new macOS user account or use a private window: File → New Private Window (Shift+Cmd+N). Private windows start without site cookies.
6. Quit Safari and reopen. Verify by visiting a site to confirm you're signed out.

D. Mozilla Firefox (clear cookies and site data; create new profile)

1. Bring Firefox to the front.
2. Open the menu (three horizontal lines) → Settings → Privacy & Security.
3. Under "Cookies and Site Data," click "Clear Data…" Select "Cookies and Site Data" and optionally "Cached Web Content," then click "Clear."
4. To remove stored site-specific data (localStorage/IndexedDB) for all sites:
   - In the URL bar go to about:preferences#privacy and scroll to "Cookies and Site Data" → click "Manage Data…" → Remove All → Save Changes.
5. To create a new Firefox profile (isolated fresh session):
   - In the address bar go to about:profiles.
   - Click "Create a New Profile," follow the prompts, and then click "Launch profile in new browser" to open a new window for that profile.
6. Quit Firefox and relaunch the new profile. Visit a site to confirm you're signed out.

E. Optional deeper cleanup and verification

1. Extensions: In each browser, open the extensions/add-ons page and disable any session-synchronizing or password-syncing extensions before clearing data. (Chrome: chrome://extensions, Firefox: about:addons, Safari: Safari → Settings → Extensions.)
2. Password managers: Clearing cookies does not remove saved passwords stored by the browser or a third-party password manager. If you want to remove saved credentials, use the browser's Passwords/settings area to delete them individually.
3. Verify sign-out: After clearing and rotating profiles, open a site where you were previously signed in and confirm it prompts for login.
4. If you used a synced account (e.g., Chrome signed into Google), sign-out from Settings → You and Google (or do not sign in to the new profile) to avoid re-syncing cookies or sessions.

## Tips

- If you need to preserve some logins, export passwords (or use a password manager) before clearing cookies.
- Creating a new browser profile is the safest way to "rotate" sessions while preserving the old profile as a backup.
- For automation or bulk admin operations across many machines, consider using MDM/managed policies or browser-specific profile templates instead of manual UI steps.
- Deleting site data is irreversible for that profile; double-check before removing profiles entirely.
- Private/Incognito windows are useful for temporary rotated sessions without modifying existing profile data.

Use this procedure whenever you need to remove all logged-in sessions and start with a fresh browser session on macOS.
