---
name: upwork-update-profile-from-resume
description: >-
  Automates updating an Upwork freelancer profile from a local resume: extracts resume text, maps Title/Overview/skills/experience/education/portfolio, edits Upwork fields in Chrome (including selecting skill suggestions), uploads attachments, saves and captures verification screenshots. Use when you want to reproducibly align an Upwork profile to a resume on a Mac desktop.
---

## Steps

1. Prepare and back up current profile
   - Open Google Chrome (Spotlight: Cmd+Space, type "Chrome", Enter) and sign in to Upwork if needed. Pause for any 2FA/OTP.
   - Open your Upwork profile page (visit https://www.upwork.com/ and click your profile → View Profile) and take a full-page screenshot of the current profile for backup.
   - Copy the current Title and Overview into a local text file (Notes or ~/Desktop/upwork-profile-backup.txt) or copy to clipboard for undo if needed.

2. Extract resume text (PDF or plain text)
   - Locate your resume file (common paths: ~/Downloads/Resume.pdf or ~/Documents/Resume-latest.pdf).
   - In Terminal, extract plain text from a PDF: pdftotext '/path/to/Resume.pdf' - | pbcopy (this copies extracted text to clipboard). If resume is plain text, open it and copy.
   - Paste the extracted text into a temporary file ~/Desktop/resume-extracted.txt for easy search.
   - Manually scan the extracted text and note the exact desired: a) short Title (1 line), b) a 2–4 sentence Overview summary, c) a concise bullet list of top skills (10–20), d) 2–4 most relevant roles/companies + 1–2 concise achievement bullets each, e) education and certificates to include.

3. Map resume pieces to Upwork fields (decide lengths)
   - Title: Keep under Upwork's character limit (usually ~75–90 chars). Create a single-line Title such as: "Full-Stack Engineer | AI/LLM · Fintech & Payments".
   - Overview: Compose a 2–4 sentence client-facing summary using resume highlights (years experience, primary tech, domain, top results). Remove personal pronouns where needed and keep active, outcome-focused wording.
   - Skills list: pick 8–18 high-value skills from the resume (e.g., React, Node.js, TypeScript, GraphQL, Stripe, Razorpay, PostgreSQL, Redis, AWS, GCP, Python). Prioritize client-facing and platform/payment integrations.
   - Employment/Portfolio items: choose 2–4 projects with 1–2 outcome bullets each.

4. Edit Title and Overview in Chrome
   - On your Upwork profile page click Edit Profile (or the pencil/edit icon for Title/Overview).
   - Click the Title field, select all (Cmd+A), paste the prepared Title (Cmd+V).
   - Click the Overview field, select all, paste the prepared Overview. If character limits appear, shorten sentences and prefer measurable outcomes.
   - Take a screenshot of Title+Overview edited but NOT yet saved.

5. Update Skills using the Upwork skill-suggestion UI
   - In the Edit Profile modal, scroll to Skills / Search skills box.
   - For each skill from your prepared skills list:
     - Click the Search skills input, type the skill name exactly (e.g., "GraphQL"), wait for the suggestion dropdown to appear, then press ArrowDown and Enter (or click the suggestion) to add it. Do NOT just type and press Enter without selecting a suggestion—Upwork often requires selecting the suggestion item.
     - Repeat for all prioritized skills: payments gateways (Stripe, Razorpay, Paytm if available), frameworks (React, Node.js), languages (TypeScript, Python), databases (PostgreSQL, Redis), cloud (AWS, GCP).
   - After adding, visually confirm the skill tags appear. If a skill is not available in suggestions, note it in your mapping file for manual mention in Overview or Employment bullets instead.

6. Update Experience / Employment / Portfolio sections
   - In Edit Profile, find Employment / Experience entries: add or edit role titles, company names, dates, and 1–2 achievement bullets derived from the resume. Keep bullets short and client-focused (what you delivered and results).
   - For Portfolio, click Add Project, set title, short description, and attach files or link to an external case study. Use screenshots or a link to a demo when possible.
   - For resume/document upload: find the Resume/CV upload field (if you choose to attach), click Upload, and select the local resume file path. Confirm the upload completes.

7. Set rate / availability / visibility (if applicable)
   - If you want to update hourly rate, availability, or profile visibility, edit those fields now. Use the resume/market positioning to pick a consistent hourly rate and availability status.

8. Save changes and verify
   - Click Save (or Save Profile). If Upwork prompts for confirmations, review and confirm.
   - After saving, open the public view of your profile (View Profile as Public) and take a full-page screenshot showing Title, Overview, Skills, and top Experience/Portfolio entries for verification.
   - Compare the saved content to ~/Desktop/resume-extracted.txt and ~/Desktop/upwork-profile-backup.txt to ensure key items were transferred correctly.

9. Final checks and notes
   - If any skill tags did not accept, add them into the Overview or Experience text where appropriate and log which skills were not available.
   - If 2FA interrupted sign-in at any time, wait for user to complete before continuing.
   - Keep the backup screenshots and the extracted resume text on the Desktop for auditing; delete them only when you are confident.

## Tips

- When adding skills, always pick the suggestion entry from the dropdown (ArrowDown+Enter or click). Typing + Enter without selection often fails.
- Keep Overview client-focused: a strong opening sentence, 1–2 tech highlights, and one sentence about measurable outcomes or domain expertise (payments/fintech) is ideal.
- For character-limited fields, prepare multiple shortened variants of Title/Overview (full, medium, short) in ~/Desktop/upwork-profile-drafts.txt and paste the appropriate one if the UI truncates.
- If you maintain multiple resumes, prefer the resume variant that emphasizes contract/consulting outcomes and specific technologies clients search for.
- Capture screenshots before and after saving so you can revert if anything was changed unintentionally.

Use this skill whenever you need to align an Upwork freelancer profile to a local resume on a Mac desktop; it is intended to be followed interactively (pauses for sign-in/2FA and manual review where required).
