---
name: goodreads-export-read-shelf
description: >-
  Exports a user's Goodreads library and produces a CSV containing only books on the 'read' shelf. Use when you need a reproducible read-shelf CSV saved to Desktop and Downloads; handles either the built-in export (filtering by shelf columns) or, if export lacks shelf data, paginated scraping of the Read shelf.
---

## Steps

1. Open Chrome (Spotlight: Cmd+Space → type "Google Chrome" → Enter). If Chrome isn't available use the default browser instead.

2. Go to https://www.goodreads.com (Cmd+L, paste URL, Enter).

3. Check sign-in status: look for avatar/profile in the top-right. If not signed in, click "Sign in" and choose the browser-saved credentials when prompted.
   - If a 2‑factor / OTP prompt appears at any point, stop immediately and ask the user for the code; do not proceed.

4. Once signed in, click "My Books" in the top navigation.

5. On the My Books page find and open "Import & Export" (sometimes under Tools or at the top/bottom of My Books). If you can't find the link, press Cmd+F and search for "Import" or "Export".

6. Click "Export Library" (this downloads goodreads_library_export.csv). Wait for the download to finish:
   - Open Chrome downloads (Cmd+J) or monitor ~/Downloads until the CSV appears and the file size stops changing.

7. Inspect the downloaded CSV to see if it contains shelf information:
   - Open the CSV in a text editor (TextEdit / VS Code) or Numbers, or check columns programmatically.
   - Look for column names like `Bookshelves`, `Exclusive Shelf`, `shelf`, or similar.

8a. If the export CSV includes shelf columns:
   - Create a new CSV that contains only rows where the book is on the "read" shelf.
   - Required output columns: title, author, year, ISBN (if available), date read, rating (use whichever of these columns are present).
   - Save the filtered file as `goodreads_read_books.csv` in two places: ~/Desktop/goodreads_read_books.csv and ~/Downloads/goodreads_read_books.csv.

   Example Python filtering (run from Terminal):

   python3 - <<'PY'
   import csv, os
   src=os.path.expanduser('~/Downloads/goodreads_library_export.csv')
   out_desktop=os.path.expanduser('~/Desktop/goodreads_read_books.csv')
   out_downloads=os.path.expanduser('~/Downloads/goodreads_read_books.csv')
   with open(src, newline='', encoding='utf-8-sig') as f:
       rows=list(csv.DictReader(f))
   # normalize shelf column names
   def has_read(r):
       for key in ['Bookshelves','bookshelves','Exclusive Shelf','exclusive_shelf','shelf']:
           if key in r and r[key]:
               if 'read' in r[key].lower():
                   return True
       return False
   selected=[r for r in rows if has_read(r)]
   if selected:
       # choose output columns available
       cols=['Title','Author','Year','ISBN','Date Read','Rating']
       cols=[c for c in cols if c in selected[0]]
       with open(out_desktop,'w',newline='',encoding='utf-8') as fo:
           w=csv.DictWriter(fo,fieldnames=cols)
           w.writeheader()
           for r in selected:
               w.writerow({c:r.get(c,'') for c in cols})
       import shutil
       shutil.copy(out_desktop,out_downloads)
   PY

8b. If the export CSV does NOT include shelf info or Export is unavailable:
   - In Goodreads go to My Books → Shelves → select the "Read" shelf.
   - Paginate through the Read pages by clicking "next". For each page scrape each listed book's title and author; if the listing shows date read and rating capture those as well.
   - Compile a CSV with columns: title, author, date read, rating (include rating only if visible).
   - Save that CSV as `goodreads_read_books.csv` to both Desktop and Downloads.

   Notes for scraping: use the browser console to extract structured data if comfortable (e.g. document.querySelectorAll), or copy page lists into a temp text file and parse.

9. Verify saved files exist:
   - ~/Desktop/goodreads_read_books.csv
   - ~/Downloads/goodreads_read_books.csv

10. Open Finder and reveal the Desktop copy (Finder → go to Desktop or run `open -R ~/Desktop/goodreads_read_books.csv`). Select the file and take a screenshot which clearly shows the filename and location in Finder.

11. Stop and report back with the file path and a note about whether the export contained shelf info or scraping was used.

## Failure / safety checks

- If a 2FA/OTP prompt appears, stop and ask the user for the code.
- If sign-in is blocked or Goodreads layout prevents locating Import & Export or Shelves, stop and ask the user how to proceed.
- Do not proceed to other accounts or websites. Do not post anything to Goodreads.

## Tips

- Use Cmd+J to check downloads quickly.
- If Numbers opens CSV with odd encoding, try reopening in a text editor with utf-8-sig.
- When scraping, prefer the site export if it contains shelf columns — it's more reliable than scraping UI.
- Keep both Desktop and Downloads copies so the user can access the file immediately.
