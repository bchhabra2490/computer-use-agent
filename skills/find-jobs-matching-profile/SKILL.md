---
name: find-jobs-matching-profile
description: >-
  Searches major job boards and company career pages for openings that match the user's stored profile/resume; opens and captures each matching posting, extracts key metadata, saves screenshots and a CSV summary to the Desktop for review. Use when the user asks to find job openings tailored to their saved profile/skills/location preferences.
---

## Steps

1. Locate the candidate profile/resume used for searching:
   - Read the user's stored profile/memory for job-title, skills, preferred locations, remote preference, and resume path (e.g., ~/Downloads/Resume.pdf or the website URL). If the memory is missing or ambiguous, prompt the user for title, top 4 skills, preferred location(s), and remote/onsite preference.

2. Build conservative search queries from the profile:
   - Primary title (e.g., "Full Stack Engineer"), plus 2–4 skill keywords (e.g., "Node.js React Python"), and location + remote keyword (e.g., "India remote" or "Bengaluru").
   - Also prepare site-scoped queries for major sites, for example:
     - site:linkedin.com "Full Stack Engineer" Node React Python India remote
     - site:wellfound.com "Full Stack" Node React remote
     - site:indeed.com "Full Stack" Node React Python India
     - site:greenhouse.io "Full Stack" Node React
     - site:lever.co "Full Stack" Node React

3. Open Google Chrome and create a new window dedicated to the job search.
   - If sign-in/2FA is required to view full job details (LinkedIn/Wellfound), stop and prompt the user to sign in; continue after the user confirms sign-in is complete.

4. Run the prepared searches one-by-one and collect candidate links:
   - For each search, open the query in a new tab. Use site-scoped queries first (LinkedIn, Wellfound, Indeed, Greenhouse, Lever), then broader Google queries.
   - On each search results page, open the top 10–20 results in new tabs (middle-click or right-click → Open in New Tab) but limit to a total of 20–30 candidate postings across all sites to keep the run practical.

5. For each candidate job posting tab (process tabs left-to-right):
   - Bring the tab to front.
   - Capture a full-page screenshot and save it to ~/Desktop/jobs-matching-screenshots/ with a numeric prefix (e.g., 01_mem0_senior-full-stack.png).
   - Extract and record these fields into an in-memory table (or a temporary CSV-ready structure):
     - source_site (LinkedIn/Wellfound/Indeed/Greenhouse/other)
     - job_title
     - company_name
     - location (or Remote)
     - posted_date (as written on page)
     - seniority/level (if visible)
     - job_url (copy full URL)
     - salary (if shown)
     - match_notes: presence/absence of the profile's top skills (list matching keywords found on the page)
     - screenshot_filename
   - If a posting is gated (login required) or blocked, write a short note in match_notes ("login_required" or "blocked_by_captcha") and still save the page screenshot if possible.

6. Compute a simple match score for each posting (0–100):
   - +40 if exact title contains primary title token(s)
   - +10 per top skill keyword found (cap at +40)
   - +10 if location matches a preferred location or posting is Remote and user prefers remote
   - +10 if seniority aligns (e.g., user is mid-level and posting is Mid/Senior)
   - Normalize/cap total at 100. Save this value as match_score in the table.

7. Save results to disk:
   - Create folder ~/Desktop/jobs-matching-<YYYYMMDD-HHMM>/
   - Save a CSV named results.csv in that folder with the columns: source_site,job_title,company_name,location,posted_date,seniority,salary,match_score,match_notes,screenshot_filename,job_url
   - Move the screenshots into the same folder under screenshots/ and ensure screenshot_filename paths in the CSV are relative to the folder.

8. Produce a short human summary and present to the user:
   - List the top 5 matches sorted by match_score, including title, company, location, posted_date, and job_url.
   - Offer to (a) open any of the top matches in the browser, (b) prepare and attach the saved resume for applications, or (c) run a scripted apply flow (if the user requests and if an application skill exists/approved).

9. Clean up:
   - Close any leftover result tabs the user no longer needs (prompt before mass-closing).
   - Leave the results folder on the Desktop and report its path to the user.

## Tips

- Respect rate limits and CAPTCHAs: if a site prompts for CAPTCHA or blocks programmatic access, pause and ask the user to proceed manually.
- Use 14–30 day posted_date filters where available to prefer recent openings.
- When searching LinkedIn or Wellfound, prefer the jobs listing interface (not company posts) to capture structured metadata.
- If the user has multiple role preferences (e.g., Full Stack, Backend), run separate batches and label the results folders accordingly.
- If the user wants automated applying, require explicit confirmation and ensure the resume path and contact info come from a verified, user-approved source before submitting.
- Keep the default candidate limit modest (20–30) to make review fast; allow the caller to request a larger batch if desired.
