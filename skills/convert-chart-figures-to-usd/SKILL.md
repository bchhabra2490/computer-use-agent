---
name: convert-chart-figures-to-usd
description: >-
  Extracts numeric figures from a chart or screenshot on macOS (using Live Text or OCR), obtains a current or user-specified INR→USD exchange rate, converts each figure to USD, and saves a CSV and an annotated image copy to the Desktop. Use when you need reproducible currency conversion of numbers shown in images or exported charts.
---

## Steps

1. Locate and open the chart/image
   - In Finder or Terminal, open the image with Preview: open ~/Desktop/<filename>.png
   - If the chart spans multiple displays, bring Preview to the front and zoom until the numeric labels are legible.

2. Extract the numeric figures and their labels
   - Preferred (Live Text available): use the text-selection cursor in Preview to select the numeric labels and their short labels (e.g., "Agriculture: ₹12,000 crore"). Copy into a new plain-text file (TextEdit → Format → Make Plain Text) and save as ~/Desktop/<filename>-numbers.txt.
   - Fallback (OCR):
     - If tesseract is installed: make a high-resolution screenshot of the chart area (Preview → File → Take Screenshot or macOS screenshot shortcut), then run in Terminal:
       python3 - <<PY
import sys,subprocess
img='~/Desktop/<screenshot>.png'
cmd=['tesseract',img,'stdout']
print(subprocess.check_output(cmd).decode())
PY
       Copy the OCR output to ~/Desktop/<filename>-numbers.txt and clean up misreads.
     - If tesseract is not available, open the image in Chrome and use Google Lens (right-click → Search image with Google) or upload the image to Google Drive and open with Google Docs to get OCR text; copy results to ~/Desktop/<filename>-numbers.txt.
   - Manually verify the text file: ensure each line contains a short label and a numeric amount plus unit (e.g., "Agriculture and allied: ₹12,000 crore" or "Agriculture: 12,000" with a noted unit).

3. Confirm units and scale
   - Verify whether the chart numbers are in thousands, millions, billions, crores, or already in currency units (check axis labels and caption). Add a header comment line to ~/Desktop/<filename>-numbers.txt noting the unit (for example: UNIT=INR; SCALE=crore meaning multiply listed numbers by 10^7 to get INR).

4. Obtain the exchange rate
   - Option A (manual / exact): Ask the user for the exchange rate to use (or confirm using the one you prefer).
   - Option B (fetch current): In Google Chrome, search "INR to USD" or open a reliable API. To fetch programmatically in Terminal and parse without jq, run:
     rate=$(curl -s 'https://api.exchangerate.host/latest?base=INR&symbols=USD' | python3 -c "import sys, json; print(json.load(sys.stdin)['rates']['USD'])")
     This sets $rate to the INR→USD rate (how many USD = 1 INR). Save the numeric rate and the source to ~/Desktop/<filename>-rate.txt.
   - Confirm the rate and source before using it.

5. Convert the extracted numbers to USD and save CSV
   - Create a small Python converter that reads your numbers file, applies SCALE and the exchange rate, and writes a CSV on the Desktop. Example (run in Terminal, editing file names as needed):
     python3 - <<PY
import csv, re
rate = float(open('/Users/$(whoami)/Desktop/<filename>-rate.txt').read().strip()) if False else float('${rate if ' + '""' + ' else ""}')
# Replace the line above with manual setting if you pasted rate; or instead run interactively to set `rate`.
infile='~/Desktop/<filename>-numbers.txt'
outfile='~/Desktop/<filename>-usd.csv'
unit_scale = {'thousand':1e3,'million':1e6,'billion':1e9,'crore':1e7,'lakh':1e5}
# Read and parse lines like: Label: ₹12,000 crore  OR  Label: 12,000 (assume unit comment)
with open(infile) as f, open(outfile,'w',newline='') as out:
    writer=csv.writer(out)
    writer.writerow(['label','inr_raw','scale','inr','usd'])
    unit_comment=None
    lines = [l.strip() for l in f if l.strip() and not l.strip().startswith('#')]
    # Optionally handle a UNIT/SCALE header line
    for line in lines:
        # crude parse: extract label and numeric+unit
        m=re.match(r"([^:]+):?\s*₹?\s*([0-9,\.]+)\s*([^\s]*)", line)
        if not m:
            # fallback: try find first number
            nums=re.findall(r"[0-9,\.]+", line)
            if not nums:
                continue
            label=line.split(':',1)[0]
            num=nums[0]
            scale=''
        else:
            label=m.group(1).strip()
            num=m.group(2).replace(',','')
            scale=m.group(3).lower()
        try:
            numf=float(num)
        except:
            continue
        multiplier = unit_scale.get(scale, 1.0)
        inr = numf * multiplier
        usd = inr * rate
        writer.writerow([label, numf, scale or '1', int(inr) if inr>1e6 else inr, round(usd,2)])
print('Saved', outfile)
PY
   - If you prefer, run the same conversion interactively in a Python REPL; ensure the path to the rate file and numbers file match.

6. (Optional) Annotate the image with USD labels
   - Duplicate the original image: cp ~/Desktop/<filename>.png ~/Desktop/<filename>-usd-annotated.png
   - Open the duplicate in Preview, open the Markup toolbar, add text boxes beside each label and paste the converted USD values (rounded as desired). Save the annotated copy.

7. Report and save artifacts
   - Ensure these files are on the Desktop: <filename>-numbers.txt, <filename>-rate.txt, <filename>-usd.csv, and optionally <filename>-usd-annotated.png.
   - Copy the CSV path to the clipboard: pbcopy < ~/Desktop/<filename>-usd.csv
   - Inform the user (or log) the exchange rate used and the CSV location.

## Tips

- Always confirm the chart's unit (₹, INR, billions, crores). A mistaken unit (crore vs. million) changes results by orders of magnitude.
- If OCR quality is poor, transcribe the few numeric labels manually — that is faster and more reliable for small charts.
- When programmatically fetching rates, prefer a documented API (exchangerate.host or another stable source) and include the timestamp/source in the saved rate file.
- Round USD values consistently (e.g., 2 decimal places) and state rounding policy in the CSV header or a sidecar README.
- For reproducibility, save the exact image, the extracted text, the rate + source, and the produced CSV together on the Desktop with consistent filenames.

## When not to use this skill

- One-off conversions you only need to eyeball quickly (use a calculator or quick Google query instead).
- Images where labels are ambiguous or where numbers are embedded in complex graphics; prefer manual transcription in those cases.
