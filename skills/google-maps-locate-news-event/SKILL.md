---
name: google-maps-locate-news-event
description: >-
  Finds a location named in a recent news article (e.g. a glacial-lake outburst), verifies the place name in the article, then opens Google Maps in Chrome, searches for that place, centers and zooms to show nearby towns/terrain, and switches to satellite view for verification and screenshots.
---

## Steps

1. Open Google Chrome: Cmd+Space, type "Google Chrome", press Enter. Wait until Chrome is in front.

2. Find a news article that names the event site:
   - Press Cmd+L to focus the address/search bar, type a concise news search such as: "recent <event type> <country> news" (for example: "recent glacial lake outburst Nepal news") and press Enter.
   - Open 1–2 authoritative results (news outlets, government or university pages) and read the headline/first paragraph to find the exact place name used by reporters (lake name, valley, village, district).
   - If the article gives coordinates, copy them. If the article only names a lake/village/river, copy that name exact as written.

3. Verify and extract the canonical place string:
   - If coordinates are available, use them directly (format: latitude, longitude). Copy them to the clipboard.
   - Otherwise copy the exact place name from the article (e.g., "Tsho Rolpa Glacial Lake" or the local settlement name) into the clipboard.

4. Open Google Maps for the extracted place:
   - In Chrome press Cmd+L, type https://www.google.com/maps and press Enter (or use the address bar to search the copied string with: https://www.google.com/maps/search/?api=1&query=<paste-URL-encoded-string> ).
   - If you have coordinates, paste them directly into the Maps search box (latitude, longitude) and press Enter.
   - If you have a place name, paste it into the Maps search box and press Enter.

5. Center and zoom to show nearby towns and terrain:
   - Wait for the place card and map to load. If multiple matches appear, choose the result whose description or coordinates match the article (click the correct result in the left panel or on the map pin).
   - Use the + key (press +) repeatedly or click the map’s + zoom control until nearby towns/labels and surrounding terrain are visible at an appropriate scale. Aim to show the event site plus at least one or two named settlements or rivers for context.
   - If the article named a nearby town or river, confirm that town/river labels are visible in the viewport.

6. Switch to Satellite view:
   - Click the Layers button (stacked-squares icon) in the bottom-left area of the map, then choose "Satellite" (or toggle the satellite imagery option). If a checkbox for labels exists, enable it so town names remain visible over satellite imagery.
   - Wait a moment for tiles to load; if imagery does not appear, reload the page (Cmd+R) and re-enable Satellite.

7. Verify match against the news article:
   - Compare the map view to any location descriptors in the article (district, river, distance from a known town). If mismatch, return to the article, extract any alternate place names or coordinates, and repeat the search.

8. Capture verification artifacts (optional but recommended):
   - To record the result, take a screenshot of the map: Cmd+Shift+4 then Space and click the Chrome window (or use Cmd+Shift+3 for full-screen). Save it to Desktop and annotate the filename with the event name and date.

## Tips

- Prefer coordinates from the article when present — they are unambiguous and map directly.
- If multiple lakes/places share a name, confirm administrative area (district, province) from the article and include that in the map search (e.g., "Tsho Rolpa, Dolakha District, Nepal").
- If Google Maps returns a non-local result, add the country name to the search query (e.g., "<place name>, Nepal").
- If Satellite imagery is not available at the desired zoom, try slightly different zoom levels or switch to the browser’s developer user agent (rare) — more commonly the imagery will appear after reloading.
- When in doubt, open two tabs side-by-side: the news article and Maps, so you can confirm textual descriptors quickly while adjusting map view.

Use this skill when you need a reproducible desktop procedure to locate and visually verify a news-reported geographic event in Google Maps on macOS.
