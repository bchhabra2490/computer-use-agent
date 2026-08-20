---
name: verify-raspberry-pi-os-boot-partition
description: >-
  Verifies a prepared removable disk on macOS contains a Raspberry Pi OS boot (FAT) partition and required boot files (e.g., kernel, config.txt, cmdline.txt) and reports whether the card appears bootable. Use when you want a repeatable, terminal-based verification of an imaged SD card on a Mac.
---

## Steps

1. Open Terminal (Spotlight: Cmd+Space → type Terminal → Enter).

2. Identify removable disks and the target disk number:

   - Run:
     ```
     diskutil list
     ```
   - Find the disk entry matching the SD card size (e.g., ~8 GB / 16 GB / 32 GB). Note the disk identifier (e.g., /dev/disk2 or disk12).

3. Inspect the disk and partition table:

   - Run a detailed info summary:
     ```
     diskutil info /dev/diskN
     ```
     (replace diskN with the identifier from step 2).

   - Also examine the partition map (GPT/MBR) and visible partition types:
     ```
     sudo gpt -r show /dev/diskN
     fdisk /dev/diskN 2>/dev/null | head -n 80
     ```
   - If diskutil reports "No partition map" or the partition table looks empty/damaged, stop and report the missing partition map.

4. Mount the boot (FAT) partition, if present and not already mounted:

   - Typical Raspberry Pi images create a small FAT32 partition labeled "boot" or similar (msdos / Windows_FAT_32). Look for a partition with TYPE or IDENTIFIER like diskNs1 and a FAT filesystem.

   - To mount all mountable partitions on that disk:
     ```
     diskutil mountDisk /dev/diskN
     ```
     or to mount a specific partition (e.g., diskNs1):
     ```
     diskutil mount /dev/diskNs1
     ```

   - After mounting, note the mount point under /Volumes (e.g., /Volumes/boot or /Volumes/RECOVERY).

5. Verify expected boot files on the mounted FAT partition:

   - Change into the mount point (replace <MOUNTPOINT> with the actual path under /Volumes):
     ```
     ls -la "/Volumes/<MOUNTPOINT>"
     ```
   - Confirm presence of these common Raspberry Pi boot files (file names may vary by OS version):
     - config.txt
     - cmdline.txt
     - start.elf, fixup.dat (or *.elf / *.dat family)
     - kernel image(s): kernel.img, kernel7.img, kernel8.img, or vmlinuz-*
     - device tree blobs: *.dtb (e.g., bcm2711-rpi-4-b.dtb)
   - Example quick check (adjust mount point):
     ```
     for f in config.txt cmdline.txt start.elf kernel.img kernel7.img kernel8.img *.dtb; do
       echo "--- checking: $f"; ls -l "/Volumes/<MOUNTPOINT>"/$f || true
     done
     ```

   - Note any missing expected files. If the FAT partition is empty or the files are absent, report the missing items.

6. Optional: inspect root filesystem presence (informational)

   - Raspberry Pi rootfs is normally an ext4 partition which macOS does not mount natively. Presence of that partition in the partition table (TYPE ext4 or Linux filesystem) is a good sign even if you cannot read it. Confirm it appears in `diskutil list` or `gpt show` as a second partition occupying most of the card.

7. Disk verification and final assessment:

   - Run disk verification on the device (reports partition-map issues):
     ```
     diskutil verifyDisk /dev/diskN
     ```
   - If the FAT boot partition exists and contains the expected boot files, report that the card appears bootable for Raspberry Pi hardware (though full boot success depends on matching Pi model and intact rootfs).
   - If partition map missing, no FAT partition, or critical boot files missing, report that the card does not appear bootable and recommend re-imaging.

8. Eject the card safely when done:

   ```
   diskutil eject /dev/diskN
   ```

## Tips

- Common missing-file symptoms:
  - Missing config.txt or cmdline.txt: Raspberry Pi will not boot or will fall back to defaults; re-image or restore those files from a fresh image.
  - Only a single large raw partition but no FAT partition: image process likely failed—re-image the SD card.
  - Empty FAT partition with just a few small files: an incomplete or corrupted image write.

- If the root (ext4) partition must be inspected on macOS, use a Linux VM, an ext4-fuse tool, or attach the card to a Linux machine—do not attempt risky low-level repairs on macOS without a backup.

- Re-imaging recommendation: use the Raspberry Pi Imager or dd from a verified .img file; after re-imaging, rerun these verification steps.

- This procedure checks for expected files and partition structure but cannot absolutely guarantee a successful boot on every Pi model (firmware/kernel compatibility and a valid rootfs are also required).
