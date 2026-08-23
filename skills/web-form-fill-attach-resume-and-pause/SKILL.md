---
name: web-form-fill-attach-resume-and-pause
description: >-
  Fills contact information on a web application, uploads a local resume file, completes any remaining required fields, captures a verification screenshot, and stops for explicit user confirmation before submitting. Use when applying online or updating application forms where email, name, and a resume upload must be corrected and verified on macOS.
---

## Steps

1. Focus the browser and bring the application tab forward (Google Chrome is preferred). If multiple windows/tabs contain the site, choose the one that shows the active application form.
2. Find the Contact / Contact Information section and locate the Email field. Select the current text and type the correct address (replace the field contents fully).
3. Locate the First Name and Last Name fields. Click each field and type the correct values (e.g., First Name: Bharat, Last Name: Chhabra). If the form uses a single "Name" box, replace it with the full name.
4. Locate the Phone field and any other obvious required contact fields and fill them with the candidate's details.
5. Find the resume / supporting documents / CV upload control:
   - If it opens the macOS native file picker, click the control to open it. Press Cmd+Shift+G to open the "Go to Folder" dialog, paste the full path to the resume (for example /Users/your-username/Downloads/Resume.pdf) and press Return. Select Resume.pdf and click Open.
   - If the upload control uses a web drag-and-drop area and also has a file-choose button, use the file-choose button to open the native picker and follow the same Cmd+Shift+G paste+Open flow.
   - If the site accepts a direct path or has a separate selection UI, use the site’s provided option to attach the file from the Downloads folder.
6. Wait for a visible upload confirmation (an attachment name, thumbnail, progress bar that reaches 100%, or a success message). If the form shows file size limits or rejects the file, note the error and either attach an alternate resume file or instruct the user.
7. Scan the form for other required fields (marked with * or red) or for inline validation errors. Common required items to check: address, city, country, work authorization, minimum experience, portfolio URL. Fill any empty required fields that you can confidently supply.
8. After making edits, capture a screenshot of the filled Contact / Supporting Documents section and save it (so the user can verify what will be submitted).
9. Do not click the final Submit / Apply / Finish button. Instead, stop and prompt the user for explicit confirmation to proceed. When prompting, summarize: updated email value, attached filename and path, and any required fields you filled or could not fill.

## Tips

- Use Cmd+Shift+G in the macOS file picker to jump directly to a full path; that avoids manual navigation.
- If the upload area accepts drag-and-drop only, you can open Finder to the file (Cmd+Shift+G → folder path), click and drag Resume.pdf onto the browser window’s drop area.
- If the form requires two-step attachments (upload then save in a separate panel), confirm both steps are done and that the attachment appears in the application’s review/summary area.
- If the site requires signing in or 2FA before changes persist, pause and notify the user for credential/2FA input rather than attempting to proceed.
- If a required field is ambiguous, leave it blank and report it to the user rather than guessing.
- Always stop before the final submission and present the screenshot plus a one-line checklist: (email updated, resume attached, required fields filled/missing) so the user can confirm or request changes.
