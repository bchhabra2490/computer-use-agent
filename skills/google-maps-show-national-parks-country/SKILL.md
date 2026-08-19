---
name: google-maps-show-national-parks-country
description: >-
  Opens Google Maps in Chrome, runs a Maps search for “national parks in <country>”, centers/zooms the map to show country-wide results, expands the left-side place list, captures a verification screenshot, and copies the Maps URL. Use when the user asks to view national parks across a country on a Mac desktop.
---

## Steps
1. Open Google Chrome (Spotlight: Cmd+Space → type "Chrome" → Enter) and bring it to the front.
2. Focus the address bar (Cmd+L), type `https://maps.google.com` and press Enter. Wait for the page to finish loading.
3. Focus the Maps search box by pressing `/` (slash). In the search box type `national parks in <country>` (replace `<country>` with the target country name, e.g. "India") and press Enter.
4. Wait for the search results to load. When results appear, expand the left-hand place list (if it collapsed) by clicking the first result or the list header so you can see multiple listed parks.
5. Zoom and pan until the map view shows the entire country (use the minus key `-`, trackpad pinch, or the on-screen +/− controls). This ensures pins/markers for parks across the whole country are visible.
6. Optionally, click individual list entries to highlight specific parks and verify markers on the map.
7. Copy the full page URL (Cmd+L → Cmd+C) to the clipboard for sharing or record-keeping.
8. Capture a screenshot of the map and the expanded list for verification (Shift+Cmd+4 to select area or use any preferred screenshot tool).

## Tips
- If the short query returns a small area or only nearby parks, try alternative queries like "national parks and wildlife sanctuaries in <country>" or "parks in <country>".
- Some Google Maps features (special layers) may vary by account or region; if a dedicated Parks layer appears in the layers/menu controls, toggle it to improve visual clarity.
- If too many pins clutter the map, zoom in to review clusters or click the left-hand list entries to navigate to individual parks.
- No Google sign-in is required for searching, but signed-in accounts may show saved lists or additional details.
- When automating, avoid waiting fixed time periods — detect the page load/spinner or presence of the results list before proceeding.
