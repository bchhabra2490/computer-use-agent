---
name: google-flights-multicity-cheapest-search
description: >-
  Automates a reproducible Google Flights multi‑city search on macOS: switches the trip type to Multi‑city, fills each leg (airport selection by IATA/name), sets departure dates, runs the search, captures the lowest fares, and optionally runs separate one‑way searches to compare totals. Use when you need the cheapest combined itinerary across two or more legs on specified dates.
---

## Steps

1. Open Google Chrome and load Google Flights: https://www.google.com/travel/flights
   - On macOS: Spotlight → type "Chrome" → Enter, or run: open -a "Google Chrome" "https://www.google.com/travel/flights".

2. Confirm locale/currency at top-right (use the site controls or query string) so prices display in the desired currency.

3. Change trip type to "Multi‑city":
   - Click the trip‑type selector (Round trip / One way / Multi‑city) and select "Multi‑city".

4. Add and fill legs:
   - For each leg, click the origin field, clear existing text (Cmd+A then Del), and type an airport city or IATA code (e.g. "IXC" or "Chandigarh").
   - When suggestions appear, pick the airport row (the specific airport line, not the city header). Prefer IATA rows like "Chandigarh (IXC)" or "Kempegowda Intl (BLR)".
   - Repeat for the destination field of that leg.
   - If you need more legs, click "Add flight" to append additional leg rows.

5. Set departure dates for each leg:
   - Click the date for a leg to open the calendar, navigate to the desired month, and click the exact day (e.g. 19 Sep).
   - Verify the chosen day shows on the leg row. Repeat for every leg.

6. Set passengers and cabin class if needed:
   - Click the passengers/cabin control and choose count and class; close the picker.

7. Run the search:
   - Click the Search (magnifying glass) button or press Enter while a field is focused.
   - Wait for results to load. If loading hangs, refresh the tab and try again.

8. Find the cheapest itinerary:
   - Sort or ensure results are ordered by price (default). Expand the lowest result to view detailed flight times, carriers, layovers, and total price.
   - Click the itinerary to open the booking options sidebar and find the page/vendor offering the fare.

9. Capture verification artifacts:
   - Copy the results page URL from the address bar (or use Chrome → Copy). Paste it into a new TextEdit or Notes file and save to Desktop with a short filename like "flights-ixc-del-blr-2026-09-19.txt".
   - Take a screenshot of the results (Shift+Cmd+4 or use macOS screenshot tool) and save it to the Desktop.

10. Optional — compare with two one‑way searches:
   - Run a one‑way search for leg A (origin→destination on the same date). Record the lowest one‑way price.
   - Run a one‑way search for leg B (origin→destination on the same date). Record the lowest one‑way price.
   - Sum the two one‑way fares and compare with the multi‑city combined fare. Note which is cheaper and save the comparison in the same TextEdit file.

11. Summarize findings:
   - In the saved text file, include: search parameters (origins/IATA, destinations/IATA, dates), cheapest multi‑city itinerary (carrier, times, total price), and one‑way comparison total (if run). Save and close.

## Tips

- Use IATA codes (e.g. IXC, DEL, BLR) to reduce ambiguous city suggestions.
- When selecting airports from suggestions, always click the specific airport row (it shows the IATA in parentheses) to avoid selecting a different nearby airport.
- If Google Flights URL parameters do not reliably prefill multi‑city legs, perform the steps in the UI rather than relying on query strings.
- If results are not shown or prices seem unusually low/high, open the itinerary detail and click the booking provider link — sometimes fees change on the vendor page.
- For repeatable records, include a timestamp in the saved filename or at the top of the TextEdit summary.
- To automate later, the saved URL + screenshot are sufficient to revisit the exact results quickly.
