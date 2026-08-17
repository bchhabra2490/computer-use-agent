---
name: github-contributions-analysis
description: >-
  Fetches a GitHub user's 1-year contributions calendar, parses daily counts into CSV, computes summary statistics (daily/weekly/monthly totals, rolling averages, weekday distribution, 30/90-day windows, weekly trend), saves CSVs and a human-readable analysis on the Desktop, and handles browser/terminal fallback and error screenshots. Use when you want a reproducible one-year contributions analysis on macOS.
---

## Steps

1. Preconditions (macOS)
   - Use Terminal and a GUI browser (Google Chrome recommended).
   - Target username: supply as variable when running (default: a provided username).

2. Check login status on GitHub (macOS GUI)
   - Open Chrome: open -a 'Google Chrome' 'https://github.com'
   - Wait for page load and inspect the top-right: if avatar/username is visible you are logged in. Record login status (username or "not logged in").
   - Note: If not logged in, GitHub will not show private contributions in the public contributions calendar.

3. Fetch contributions calendar SVG (preferred: curl)
   - Terminal (preferred):
     - curl -sS -L "https://github.com/users/<username>/contributions" -o /tmp/contributions.svg
     - Confirm file exists and contains markup: wc -c /tmp/contributions.svg; head -n 40 /tmp/contributions.svg
   - Fallback (browser):
     - In Chrome open https://github.com/<username>
     - Right-click the contributions calendar area and choose Inspect → locate the calendar markup. Copy outerHTML of the calendar element and save as /tmp/contributions.svg (or Save As from the Elements panel into a file). If necessary, save the full page and extract the calendar HTML into /tmp/contributions.svg.

4. Parse the calendar file into a daily CSV
   - Accept either SVG <rect> cells (older/current markup) or HTML <td> cells/tooltips.
   - For each day extract: date (ISO YYYY-MM-DD) and count (integer). If the markup places the count only inside a title/aria-label/tooltip like "X contributions on Month D, YYYY", parse that text to extract the count and date.
   - Build a CSV with headers: date,count,weekday,week_index
     - weekday: Mon, Tue, Wed, Thu, Fri, Sat, Sun (use the date's weekday name)
     - week_index: integer week index where week_index = floor((date - earliest_date).days / 7). (This yields 0..51 for a 365-day span.)
   - Write temporary CSV: /tmp/github_contributions.csv and final: ~/Desktop/github_contributions.csv

   Example robust parsing approach (Python):
   - Attempt regex to find all <rect[^>]*> elements and match data-date and data-count attributes.
   - If not found, search for table cells or tooltip text nodes with patterns like "data-date=\"YYYY-MM-DD\"" or text like "123 contributions on Month D, YYYY" and convert Month D, YYYY to ISO.
   - Ensure output is exactly one row per date for the last 365 days. If duplicates are present, deduplicate by taking the numeric count for that date.

5. Compute statistics (Python recommended; can use pandas or stdlib)
   - Load the daily CSV and sort by date ascending.
   - Basic stats (daily): total = sum(counts), mean = mean(counts), median, std (population or sample — note which you use). Use floating precision for mean/std.
   - Mean per week = total / 52.0
   - Mean per month = total / 12.0
   - Last 30-day and last 90-day windows: compute sum and mean over the most-recent 30 and 90 dates.
   - Day-of-week distribution: for each weekday compute average contributions (sum for that weekday / number of occurrences of that weekday in the 365-day window). Report busiest weekday (highest mean) and least busy.
   - Weekly sums: create 52 weekly buckets using the week_index above. For each week compute start_date (earliest date in the week) and sum of contributions in that week. Save as ~/Desktop/github_weekly_summary.csv with headers week_index,week_start_date,sum
   - 4-week rolling average: compute centered or trailing 4-week rolling average on weekly sums (trailing is simplest: avg over current week and prior 3 weeks). Save rolling average in the weekly CSV or separately.
   - Trend: compute linear regression (ordinary least squares) of weekly sums vs week_index (0..51). Report the slope (contributions per week per week). Interpret:
     - If slope > 0.01 * mean_week_sum → "increasing"
     - If slope < -0.01 * mean_week_sum → "decreasing"
     - Otherwise → "stable"
     (Adjust thresholds if desired; this heuristic detects meaningful percent change over the year.)

6. Save results to Desktop and create human-readable summary
   - Save the daily CSV: ~/Desktop/github_contributions.csv
   - Save weekly CSV: ~/Desktop/github_weekly_summary.csv (columns: week_index,week_start_date,week_sum,rolling_4wk_avg)
   - Save analysis text: ~/Desktop/github_push_frequency_analysis.txt. Include:
     - header: username and login status (if not logged in, explicitly say private contributions will be missing)
     - bullet points: total contributions (365d), mean/median/std per day, mean per week/month, last-30d and last-90d sums & means, busiest weekday and average per-week, 52-week trend slope and interpretation (increasing/stable/decreasing), top 3 busiest single days (date,count)
     - short recommended insights (e.g., "average pushes per week ≈ X", "busiest weekday: Tue with avg Y contributions", "recent 30-day trend: rising/falling stable")

7. Error handling and verification
   - If any network fetch or parsing step fails:
     - Capture screenshots of the browser and Terminal: use macOS screencapture or the UI to take screenshots and save them as ~/Desktop/github_analysis_error_1.png, ...
       - Example command: screencapture -x ~/Desktop/github_analysis_error_1.png
     - Write an error note to ~/Desktop/github_push_frequency_analysis.txt describing what failed and what partial outputs (if any) were produced. Attach paths to saved screenshots and partial CSVs.
   - If parsing produced fewer than 365 unique dates, note this in the summary and save whatever was parsed.

8. Final step: reveal Desktop for user review
   - Open the Desktop folder so the user can inspect outputs: open ~/Desktop
   - Optionally open the summary text file with the default text editor: open -a TextEdit ~/Desktop/github_push_frequency_analysis.txt

## Tips

- Prefer Python with pandas if available (pandas makes grouping, rolling windows, and regression straightforward). If pandas is not available, the stdlib plus numpy (or math/statistics + simple OLS formula) is sufficient.
- Parsing nuance: GitHub markup can change. The script should try both attribute-based parsing (data-date/data-count) and tooltip/body text parsing (e.g., "X contributions on Month D, YYYY").
- Week indexing: using week_index = floor((date - earliest_date).days / 7) yields stable 0..51 indexing; GitHub's visual week columns typically start on Sunday — mention this if you want week_start aligned to Sundays.
- Private contributions: explicitly warn in the summary when not logged in because the public contributions calendar omits private activity.
- Reuse: keep the script generic (accept username and output directory) so it can be run for other users easily.

## Example minimal python invocation

- Save a parsing/analysis script to /tmp/analyze_github_contribs.py and run:
  - python3 /tmp/analyze_github_contribs.py --username bchhabra2490 --outdir ~/Desktop

The script should implement the parsing and stat calculations described above, write the three output files to the Desktop, and exit with a clear status and error messages when parsing or network steps fail.
