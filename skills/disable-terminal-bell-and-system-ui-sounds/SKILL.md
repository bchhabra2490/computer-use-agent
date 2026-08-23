---
name: disable-terminal-bell-and-system-ui-sounds
description: >-
  Disables audible bells across macOS and common terminal apps, configures Readline/zsh to avoid beeps, searches shell and app startup files for bell/emitting sequences and removes or neutralizes them, and reports the files changed. Use when you want a reproducible way to silence system and terminal beeps on a Mac.
---

## Steps

1. Prepare backups
   - Create a timestamped backup folder for any files you will change:
     mkdir -p "$HOME/.config/disable-bell-backups/$(date +%Y%m%d-%H%M%S)"
   - Copy common startup files into the backup folder before editing (repeat as needed):
     cp -p ~/.zshrc ~/.bashrc ~/.profile ~/.zprofile ~/.inputrc "$HOME/.config/disable-bell-backups/"

2. Turn off macOS interface sound effects (GUI + command)
   - GUI: Open System Settings → Sound → Sound Effects and uncheck “Play user interface sound effects”.
   - Terminal command (applies the same setting):
     defaults write -g com.apple.sound.uiaudio.enabled -bool false && killall SystemUIServer

3. Disable audible bell in Apple Terminal
   - GUI: Open Terminal → Preferences → Profiles → select each profile → Advanced → uncheck “Audible bell” (you can enable visual bell instead if you want a visual indicator).
   - (Optional) If you prefer to script the preference change, back up Terminal settings first; then you can set preferences per profile. Confirm with a new Terminal window.

4. Disable audible bell in other terminal apps
   - iTerm2: Preferences → Profiles → Terminal → check “Silence bell” (or uncheck “Audible bell”).
   - kitty: edit ~/.config/kitty/kitty.conf and add the line:
     bell none
   - Warp / other GUI terminals: open Preferences and look for “Audible bell”, “Bell”, or “Sound” and disable the audible option for each profile.

5. Configure Readline (bash / many shells) to be silent
   - Add or update ~/.inputrc with the single line:
     set bell-style none
   - Apply immediately for current bash session:
     bind -f ~/.inputrc
   - New shells will use this automatically.

6. Configure zsh to suppress the bell
   - Edit ~/.zshrc and add one of these (both are safe; use whichever is accepted by your zsh):
     setopt NO_BEEP
     # or, if your zsh recognizes the positive option name:
     unsetopt beep
   - Save and apply:
     source ~/.zshrc

7. Search shell and app startup files for explicit bell emitters and back them up
   - Look for literal BEL characters and common escaped forms. Run these searches and inspect results before changing anything:
     # literal BEL (ASCII 7)
     grep -n $'\a' ~/.zshrc ~/.bashrc ~/.profile ~/.zprofile ~/.bash_profile ~/.inputrc 2>/dev/null || true

     # escaped sequences that commonly cause a bell in scripts/strings
     grep -n -E "\\\a|\\007|\\x07|\$'\\a'|echo -e .*\\a|printf .*\\a" -R ~ -I --exclude-dir={.git,node_modules} 2>/dev/null || true

   - For application integrations (e.g. Conductor, prompt/tooling), also inspect the app shell-integration scripts in ~/Library/Application\ Support/ and ~/.config/ for occurrences.

8. Remove or neutralize found bell sequences (safe, backed-up edits)
   - Always copy the file to the backup location before changing it, e.g.:
     cp -p path/to/file "$HOME/.config/disable-bell-backups/"

   - To remove literal BEL characters from a file while keeping a .bak of the original (automated safe pass):
     perl -0777 -pe 's/\x07//g' -i.bak path/to/file
     # the original is saved as path/to/file.bak; verify manually before deleting the .bak

   - To remove simple escaped backslash sequences like "\\a" from plain strings (manual review recommended):
     perl -0777 -pe 's/\\a//g' -i.bak path/to/file
     # NOTE: this can change legitimate strings; prefer manual edits using an editor for complex cases.

   - For explicit commands like `echo -e "\a"` or `printf "\a"`, comment them out or replace with a silent alternative (for example: comment the line with # or replace with a visual indicator such as echo "[notification]" or use terminal notifications that don't beep).

9. Reload shells and apps to apply changes
   - source ~/.zshrc (or restart Terminal/iTerm2/kitty)
   - For Readline changes use: bind -f ~/.inputrc or start a new shell
   - Restart apps (Terminal, iTerm2, kitty) to pick up per-app preference changes

10. Verify
   - From a new shell window, run a harmless test that would normally trigger a bell (be aware it will produce a sound if you missed something):
     printf "\a"  # do this only after you expect bells to be disabled
   - Confirm no audible sound plays; if a bell still sounds, re-check the profile settings, ~/.inputrc, and any scripts that were found in step 7 (remote hosts, tmux, or multiplexers can also generate bells).

11. Produce a short report of changes you made
   - List files you backed up and any files you modified (the backup folder contains originals). Example summary items:
     - Backups saved to: ~/.config/disable-bell-backups/<timestamp>
     - Modified: ~/.inputrc (added `set bell-style none`)
     - Modified: ~/.zshrc (added `setopt NO_BEEP`)
     - Modified: ~/.config/kitty/kitty.conf (added `bell none`)
     - Edited: ~/Library/Application Support/…/shell-integration (removed $'\a' sequences)
   - Keep the .bak files produced by perl edits or the timestamped backups until you confirm behavior for a day or two.

## Tips

- Don't mass-replace escaped sequences without reviewing them; replacing `\\a` inside arbitrary strings can break other expected behavior. Use backups and inspect diffs before and after editing.
- Remote systems you SSH into can send bell characters; disabling local terminal bells won't stop remote-side notifications unless the remote prompt/config is changed as well.
- Some prompts and third-party prompt frameworks (powerlevel10k/oh-my-zsh plugins) may intentionally emit bells. Look in prompt/theme files and plugins before blanket-removing sequences.
- If you prefer a visual cue instead of a sound, enable "visual bell" in your terminal profile (Terminal/iTerm2) and leave the audible setting off.
- Keep the backups directory until you are sure nothing important was removed: ~/.config/disable-bell-backups/<timestamp>

## Example quick checklist to include in your report
- Backups created at: ~/.config/disable-bell-backups/<timestamp>
- System UI sounds: turned OFF via System Settings and defaults write
- Terminal.app profiles: Audible bell disabled (per-profile)
- iTerm2/kitty/other: per-app bell settings updated (listed exact files/steps)
- Readline: ~/.inputrc updated with `set bell-style none`
- zsh: ~/.zshrc updated with `setopt NO_BEEP` (or `unsetopt beep`)
- Files inspected & edited: list file paths and the specific change (e.g., removed literal BEL chars, commented out printf/echo that emitted \a)

Use this skill whenever you need a consistent, auditable process to silence terminal beeps system-wide and remove bell-emitting lines from startup scripts on macOS.
