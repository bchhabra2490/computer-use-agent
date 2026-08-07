---
name: amazon-search-verify-add-to-cart
description: >-
  Performs an Amazon product search, verifies the product page includes required technical keywords/specs, captures a screenshot and product URL, and adds the verified item to the cart. Use when asked to find and add a technical product (hardware/module/dev board) on Amazon while confirming features.
---

## Steps

1. Open a web browser (Chrome or Safari).
2. Go to the Amazon domain required (e.g., https://www.amazon.in). Press Cmd+L, type the URL, and press Enter.
3. Sign in if prompted (click the Sign in link, enter credentials). If already signed in, continue.
4. Click the Amazon search box, type the first query (e.g., "ESP32 S3 audio board"), and press Enter. Take a screenshot of the search results.
5. Replace the search text (Cmd+A) with the second query (e.g., "ESP32-S3 audio development board") and press Enter. Take another screenshot of results if useful.
6. Optionally enable/filter for Prime listings and sort/filter by customer ratings if available (click the Prime checkbox and use the sort menu).
7. From results, open candidate product pages in new tabs and inspect them. Prefer listings with high ratings, Prime badge, and reputable sellers.
8. On a product page, confirm the product explicitly lists the target chipset/part and audio features. Use Cmd+F and search for required keywords (example: "ESP32-S3", "audio", "I2S", "INMP441", "MAX98357A", "DAC", "ADC", "mic", "headphone").
9. Capture a screenshot that clearly shows the product title, price, seller, and key specs. To capture the visible product page window on macOS: press Cmd+Shift+4, then Space, then click the browser window; the screenshot will save to the default location (typically Desktop). If you need the page content beyond the viewport, scroll and capture additional screenshots.
10. Copy the product URL: press Cmd+L to focus the address bar, then Cmd+C to copy.
11. Click the yellow "Add to Cart" button on the product page (do not proceed to checkout). Wait for the confirmation (a small toast/cart update).
12. Verify the cart was updated: click the cart icon and confirm the item appears (title and price). If unsure, capture a screenshot of the cart contents.
13. If the selected item is unavailable or not suitable, repeat steps 7–12 for up to 2 additional alternatives and record their links and prices.
14. Report back with: chosen product link, price, saved screenshot(s) location or file(s), seller, and whether Add to Cart succeeded. Do not perform checkout.

## Tips

- Use Cmd+F to quickly find technical keywords on product pages.
- Prefer listings that show "Prime" badge and have a seller with good ratings.
- Check the "Product information" and "Technical Details" sections for explicit chipset and audio component listings.
- If seller or product descriptions are ambiguous, open the manufacturer datasheet link or ask the seller questions via the product page before adding to cart.
- Save screenshots immediately after capture and use clear filenames (e.g., "amazon_esp32s3_productname_price.png").
- Respect account security: don’t store or transmit passwords in logs or reports.
