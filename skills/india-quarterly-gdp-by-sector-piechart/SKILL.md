---
name: india-quarterly-gdp-by-sector-piechart
description: >-
  Finds India’s official quarterly GVA/GDP release (MOSPI), extracts agriculture/industry/services values for a specified quarter, makes a sectoral pie chart image, and saves a short source-and-notes file (nominal/real, base year). Use when you want a reproducible chart and citation from the official press release.
---

## Steps

1. Identify the target quarter and search MOSPI press releases in Google Chrome
   - In Chrome, search: site:mospi.gov.in "Estimates of Gross Domestic Product" "Q1" "2025-26" (replace quarter/year as needed).
   - Open the MOSPI press release or press note PDF that matches the requested quarter.

2. Verify the released table and record metadata
   - On the MOSPI press note page or its linked PDF, find the table titled something like "Gross Value Added (GVA) at basic prices by economic activity" or "Sectoral distribution of GDP/GVA". 
   - Note whether the table is at current prices (nominal) or constant prices (real). Also note the base year (e.g., base 2011-12, 2015-16, 2017-18 etc.). Save the press-note URL.

3. Download or open the press note PDF
   - Click the PDF link and save it to ~/Downloads or open it in Preview.
   - If the PDF table is selectable, copy the three sector rows (Agriculture, Industry, Services) and their values (unit usually crore rupees) to the clipboard. If not selectable, take a clear screenshot and transcribe the three values.

4. Create a small CSV on the Desktop with the three sector values
   - In Chrome/Preview/TextEdit/Numbers, prepare a CSV file with two columns: sector,value
   - Example (replace numbers with the official values you copied):
     sector,value
     Agriculture,123456
     Industry,234567
     Services,345678
   - Save as: ~/Desktop/india_Q1_2025-26_gva_by_sector.csv (adjust quarter/year naming to match the data)

5. Prepare the plotting environment on the Mac (Terminal)
   - Open Terminal (Spotlight: Cmd+Space → type Terminal).
   - Ensure Python 3 is available: python3 --version
   - If needed, install minimal plotting deps for the user: python3 -m pip install --user pandas matplotlib

6. Run the plotting script to compute shares and save a pie chart
   - In Terminal, create and run a short Python script. Example commands:

     cat > ~/Desktop/plot_gva_by_sector.py << 'PY'
     import pandas as pd
     import matplotlib.pyplot as plt
     import sys

     csv_path = sys.argv[1] if len(sys.argv) > 1 else '/Users/$USER/Desktop/india_Q1_2025-26_gva_by_sector.csv'
     out_png = sys.argv[2] if len(sys.argv) > 2 else '/Users/$USER/Desktop/india_Q1_2025-26_sector_pie.png'

     df = pd.read_csv(csv_path)
     # normalize values to numeric (strip commas if present)
     df['value'] = df['value'].astype(str).str.replace(',','').astype(float)
     labels = df['sector'].tolist()
     values = df['value'].tolist()

     fig, ax = plt.subplots(figsize=(6,6))
     wedges, texts, autotexts = ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=140, textprops={'fontsize':10})
     ax.set_title('Sectoral share of GVA/GDP — Q (as provided)')
     plt.tight_layout()
     plt.savefig(out_png, dpi=150)
     print('Saved pie chart to', out_png)
     PY

     # Run the script (adjust CSV name if you used another filename):
     python3 ~/Desktop/plot_gva_by_sector.py ~/Desktop/india_Q1_2025-26_gva_by_sector.csv ~/Desktop/india_Q1_2025-26_sector_pie.png

   - After running, open the saved PNG on the Desktop to verify (double-click to open in Preview).

7. Save a short source-and-notes text file
   - Create ~/Desktop/india_Q1_2025-26_gva_sources.txt containing:
     - MOSPI press note URL(s) (full URL)
     - Exact table name, whether values are at current prices (nominal) or constant prices (real), and the base year
     - Units used in the table (e.g., crore rupees)
     - Any transformation you did (e.g., used GVA at basic prices directly; if you converted GVA→GDP used taxes/subsidies adjustment and show formula)

   - Example commands:
     echo "Source: <full MOSPI URL>" > ~/Desktop/india_Q1_2025-26_gva_sources.txt
     echo "Table: Gross Value Added (GVA) at basic prices by economic activity" >> ~/Desktop/india_Q1_2025-26_gva_sources.txt
     echo "Prices: current prices (nominal) — base year XXXX" >> ~/Desktop/india_Q1_2025-26_gva_sources.txt

8. Deliver and verify
   - Open the PNG and the sources text file to confirm they match.
   - Keep the original press-note PDF in ~/Downloads for archival.

## Tips

- Check whether the MOSPI table reports GVA at 'basic prices' or GDP at 'market prices'. For a true GDP sectoral pie, you may need GDP at market prices (GVA + taxes - subsidies). If the press note gives only GVA by sector, state clearly in the notes that the chart is sectoral GVA, not GDP (unless you explicitly convert).

- Units and magnitude: MOSPI often reports values in crore rupees. Keep raw units and label the chart or the notes accordingly.

- If table copy/paste fails from the PDF, use a screenshot and transcribe numbers carefully; double-check thousand separators and decimal points.

- If you prefer a GUI spreadsheet workflow: paste the three rows into Numbers, compute percentages there, then export a pie chart image (File → Export To → PNG). The Python route is optional but reproducible.

- When scripting, replace $USER or the CSV/PNG filenames consistently to match your saved file locations.

- If plotting libraries are not permitted on the machine, create the CSV and use Numbers or Excel to make and export the pie chart instead.

- Always cite the MOSPI press note URL and copy the exact table title and footnotes into the sources file so later reviewers can confirm nominal vs real/base-year assumptions.
