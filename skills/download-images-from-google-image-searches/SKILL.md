---
name: download-images-from-google-image-searches
description: >-
  Downloads 3–5 representative images from two Google Image search tabs into a new folder on the Mac Desktop. Use when the user needs a small, labeled dataset of images (two categories) saved locally for review or analysis.
---

## Steps

1. Prepare a destination folder on the Desktop
   - Switch to Finder (click Desktop or use Cmd+Tab to Finder).
   - With Desktop visible, create a new folder: File → New Folder (or Cmd+Shift+N).
   - Name it descriptively, e.g. `Desktop/Bearings_vs_Actuators`.

2. Confirm the two Google Images searches are open in Chrome
   - In Google Chrome, verify you have one tab for the first search (e.g. "robot bearings") and another tab for the second (e.g. "robot actuators").
   - If not open, open each search URL in its own tab.

3. Download 3–5 representative images from the first search (bearings)
   - Switch to the tab with the bearings search.
   - Click a clear thumbnail to open the larger preview at the right or in the lightbox.
   - Prefer: Right‑click the large preview and choose "Open image in new tab". If that option is not available, choose "Open image in new window" or "Save image as…" instead.
   - In the new tab with only the image, save it: Cmd+S → navigate to `Desktop/Bearings_vs_Actuators` → Save. Use a short descriptive filename (or keep the default).
   - Close the image tab (Cmd+W) and return to the search results.
   - Repeat until you have saved 3–5 distinct bearing images.

   Notes on alternatives:
   - If the large preview context menu includes "Save image as…", you may use that directly and choose the destination folder.
   - If the site prevents direct saving, open the image in a new tab and use Cmd+S. If that still fails, capture the visible image area using Chrome’s context menu: "Open image in new tab" then right-click → "Save image as…". As a last resort, use a fullscreen screenshot of the preview (Shift+Cmd+4 to select) and save the PNG into the destination folder.

4. Download 3–5 representative images from the second search (actuators)
   - Switch to the tab with the actuators search and repeat step 3, saving 3–5 images into the same `Desktop/Bearings_vs_Actuators` folder.

5. Verify and optionally rename files
   - Open the destination folder in Finder and confirm the expected number of files (6–10 images).
   - Optionally rename files to include a category prefix, e.g. `bearing_01.jpg`, `actuator_02.jpg` for easier later identification: select a file → Return to rename, or use a bulk rename (right-click → Rename).

6. Final check
   - Open a couple of saved images in Preview to verify they are full-resolution and not thumbnails.
   - If any saved files are low-resolution thumbnails, re-download a larger source image following step 3 alternatives.

## Tips

- Prefer "Open image in new tab" + Cmd+S — this reliably saves the original image instead of a Google-served thumbnail.
- When saving many images, include the category name in filenames for later automation or analysis.
- Respect copyright: avoid downloading images you do not have the right to reuse for distribution. For datasets, prefer images from permissive sources or use the site’s licensing filter before saving.
- If a site blocks right-click saving, opening the image in a new tab is generally the most reliable workaround. If that is blocked too, use a carefully cropped screenshot as a last resort.
- Keep the number of images small (3–5 per category) unless you intend to build a larger dataset; for larger downloads consider using programmatic image-download tools instead of manual saving.
