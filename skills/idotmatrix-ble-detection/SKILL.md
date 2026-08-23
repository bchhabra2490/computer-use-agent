---
name: idotmatrix-ble-detection
description: >-
  Determines whether a BLE pixel display (Apex / iDotMatrix family) uses the iDotMatrix protocol and whether an ESP32 can control it. When given a product page or device, it inspects product images/specs, searches community/open-source repos, extracts GATT UUIDs and packet references, and summarizes whether a BLE client (ESP32) can write pixel data or whether a wired LED data connector is exposed.
---

## Steps

1. Prepare the Mac environment
   - Open Google Chrome and Terminal.
   - Ensure you can run git and basic shell commands (git, grep, sed, find).

2. Inspect the product page and images in Chrome
   - Open the product page (ASIN or seller page) in Chrome and review all images.
   - Open each image, zoom in on PCB/connector photos and look for pin labels (VCC, GND, DIN/DOUT, CLK, TX/RX, JST, USB). Copy or save high-resolution images if available.
   - Check product description, technical specs, manuals, and seller Q&A for words like BLE, Bluetooth, iDotMatrix, iDM, or model names.

3. Search for community/open-source references
   - In Chrome, search for the product name or ASIN plus terms: "iDotMatrix", "iDot", "iDM", "Bluetooth", "BLE", "IdotMatrix ESP32" and "github".
   - Open likely GitHub repos, Home Assistant integrations, or Python clients for iDotMatrix/iDotMatrix-related projects.

4. Clone and inspect open-source clients on the Mac (Terminal)
   - In Terminal run the following (examples used for iDotMatrix):
     - git clone https://github.com/derkalle4/python3-idotmatrix-client.git /tmp/idot-client
     - git clone https://github.com/derkalle4/python3-idotmatrix-library.git /tmp/idot-lib
     - git clone https://github.com/tukies/iDotMatrix-HomeAssistant.git /tmp/idotmatrix-ha

   - Search these copies for BLE/GATT references and UUIDs:
     - grep -RInE 'UUID|fa02|fa03|FA02|FA03|BLE|NimBLE|write\(|notify|characteristic|service' /tmp/idot-lib /tmp/idot-client /tmp/idotmatrix-ha || true

   - Open the most relevant source files (client/connection manager, consts, image transport) and read the constants and frame-building code to identify:
     - Service/characteristic UUIDs used (common iDotMatrix UUIDs include 0000fa02-0000-1000-8000-00805f9b34fb for writes and 0000fa03-0000-1000-8000-00805f9b34fb for reads/notifications).
     - Frame format for pixel data (block/frame headers, sizes, checksum if any).

5. Record evidence and summary
   - Copy the discovered UUIDs, the GATT write characteristic, and a short sample of the frame format into a text note.
   - Note whether the project uses BLE central/client only (i.e., the display exposes BLE GATT and expects a central to write frames) or also exposes any wired LED data pins in images/specs.

6. Decide feasibility for ESP32 control
   - If BLE GATT write characteristic is present (e.g. fa02), an ESP32 can act as a BLE central/client to connect and write pixel frames.
   - Identify which ESP32 BLE stack to use: Arduino-NimBLE or ESP-IDF/NimBLE. Search the cloned repos for client implementation examples to mirror packet construction.

7. Prepare a minimal ESP32 test plan (on the Mac)
   - Create a small repo or folder for a test sketch.
   - Prepare a BLE-central example using Arduino-NimBLE or ESP-IDF NimBLE that:
     - Scans for the display (device name pattern: e.g. starts with "IDM-" or similar).
     - Connects, discovers services, finds the write characteristic UUID, and writes a short frame (e.g., set a single pixel or a small color block).
   - Save the sample packet bytes you extracted from the libraries into a file (hex) so you can paste them into the ESP sketch.

8. Optional: verify with desktop BLE tools before flashing ESP32
   - Use a desktop BLE app (e.g. nRF Connect for Desktop or a Chrome BLE extension) to scan for the device, connect, discover services, and try a manual write to the write characteristic to observe behavior. Document the results.

9. Summarize and store findings
   - Produce a one-page summary: product page screenshot(s), discovered UUIDs, frame format notes, whether a physical LED data connector was found, and an action recommendation (use ESP32 BLE client with Arduino-NimBLE / ESP-IDF). Save the summary to ~/Desktop/apex-idotmatrix-report.txt and screenshot key product images to ~/Desktop/apex-idotmatrix-images/.

## Tips

- Search terms that quickly find community work: "iDotMatrix", "iDotMatrix BLE", "iDotMatrix protocol", "IDM-" (device name), and the product ASIN.
- Common iDotMatrix BLE UUIDs to look for: 0000fa02-0000-1000-8000-00805f9b34fb (write) and 0000fa03-0000-1000-8000-00805f9b34fb (read/notify).
- If product images do not show an exposed LED-data connector, the device likely expects BLE-only control; look for JST 4/5-pin sockets or exposed WS2812-style strips if wired control is present.
- When preparing the ESP32 sketch, prefer NimBLE-based client examples—search for "NimBLEClient" or "BLEClient" examples matching the discovered UUIDs.
- Use desktop BLE tools to validate the GATT characteristics before flashing hardware. That saves time when constructing frames.

When to use this skill: run it when you need to determine whether a BLE pixel display is controlled via a documented BLE protocol (and therefore can be driven by an ESP32 acting as BLE central) or when you need the exact GATT UUIDs/frame layout for building an ESP32 client.
