---
name: amazon-checkout-place-order
description: >-
  Completes checkout on Amazon.in (or Amazon) for an item already in the cart: confirms the cart item, selects a saved shipping address, chooses the default payment method, reviews price threshold, pauses for OTP/2FA if required, places the order, and captures confirmation screenshots. Use when asked to place an order already prepared in the user's Amazon cart.
---

## Steps

1. Open the browser and go to https://www.amazon.in/cart (or open Amazon cart page already in the session). Use Cmd+L to focus the address bar and paste if needed.
2. Confirm the correct product is in the cart by matching the product title/ASIN/URL to the provided product link or identifier (e.g., verify the URL contains the product ASIN or visually verify the product title). If it is not present, stop and report (do NOT search again).
3. Click Proceed to checkout (or Continue) to enter the shipping-selection page.
4. In the shipping address list, locate and select the user’s saved Mohali address (or the specified saved address). Click the yellow “Deliver to this address” / Confirm button to lock the address.
5. Scroll to or expand the Payment Method / Payment section. Select the account’s default payment method (e.g., default debit/credit card / Amazon Pay). If no default exists or the desired method is unavailable, stop and report alternatives.
6. Review the order total shown on the right/review page. If the total exceeds the approval threshold (default ₹10,000), pause and ask the user for explicit approval before continuing.
7. If the order total is approved (or below threshold), click to place the order. If the bank/payment gateway prompts for OTP / 2FA, DO NOT attempt to bypass it. Stop and ask the user to provide the OTP or to complete 2FA on their device, then continue once the user confirms or supplies the OTP.
8. After successful placement, wait for the Amazon order confirmation page to load. Capture screenshots showing the order number, total price paid, and estimated delivery date. Also capture either the order details page (Order Details) and/or the confirmation email in the user’s mail.
9. Save screenshots with clear filenames (e.g., amazon-order-confirmation-YYYYMMDD-1.png, -2.png). Record and return: product link/ASIN, final price paid, estimated delivery date, order number, and the screenshots.
10. If any problem prevents placing the order (address not selectable, payment method rejected, seller out of stock, or other errors), stop and report the specific issue and suggested alternatives (change address, use another payment method, contact bank, wait for restock).

## Tips

- Use Spotlight (Cmd+Space) → type the browser name to open if needed. Use Cmd+L to quickly focus the URL bar.
- Use browser Find (Cmd+F) to search the cart/checkout page for the product ASIN or part of the product title.
- For screenshots on macOS: Shift-Command-4 then Space to capture a window, or Shift-Command-4 to select an area. If automated screenshots are available in the environment, use them and ensure they clearly include order number, price, and delivery date.
- Do not retry product search/add-to-cart steps here — this skill assumes the item is already in the cart.
- Respect security: never attempt to bypass OTP/2FA. Pause and request user action when prompted for OTP or bank confirmation.
- Default approval threshold is ₹10,000; request explicit user approval if the order total exceeds this value.
