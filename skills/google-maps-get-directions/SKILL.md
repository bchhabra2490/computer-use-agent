---
name: google-maps-get-directions
description: >-
  Opens Google Maps on macOS, enters an origin (saved Home or a specified address) and a destination, shows available routes and travel times, expands step-by-step directions, and offers send/copy actions. Use when you need reproducible directions from Home (or another origin) to a named place.
---

## Steps

1. Open Google Chrome (Spotlight: Cmd+Space, type "Chrome", Enter) or bring an existing Chrome window to the front.
2. In Chrome’s address bar go to https://www.google.com/maps/dir/ and press Enter.
   - (Alternative for automation) open the direct URL https://www.google.com/maps/dir/Origin/Destination where spaces are URL-encoded (example: /dir/Home/Sector+17,+Chandigarh).
3. If you used the blank Directions page, click the blue "Directions" button (left panel) to open origin/destination fields.
4. Set the origin:
   - Type `Home` and select the saved "Home" suggestion if it appears.
   - If "Home" is not saved or you prefer a specific start, type the full origin address and choose the correct suggestion.
5. Set the destination by typing the place name (e.g. "Sector 17, Chandigarh") and selecting the correct suggestion from the dropdown.
6. Wait until route cards and travel times appear in the left panel; choose the preferred route card by clicking it.
7. To see turn-by-turn directions, click the chosen route's "Details" (or "Steps") to expand the step list.
8. Optional actions:
   - Change travel mode by clicking the transport icons (car / transit / walk / bike) at the top of the left panel.
   - Click the three-dot menu or the "Send directions to your phone" control to send the route to a device or to copy the route link to the clipboard.
9. Verify the route and estimated travel time are visible. Capture a screenshot if you need a record.

## Tips

- If the signed-in Google account has no saved "Home", enter the exact origin address instead of relying on the label.
- The direct /maps/dir/Origin/Destination URL is the most reliable way to open a specific directions search when scripting or automating.
- When multiple suggestion results appear for a place name, choose the one with the correct city/state to avoid a wrong location.
- Use the "Leave now" dropdown to change departure/arrival time and get different ETA estimates.
- For public transit routes, expand each leg to see schedules and platform/line details.
