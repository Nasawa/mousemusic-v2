# MouseMusic

> The full README (download, SmartScreen, troubleshooting) is task P4. This file currently contains only the taskbar
> section, so P4 can merge around it.

## Hearing your taskbar

MouseMusic can give **every taskbar icon its own note**, so you can tell your pinned apps apart by ear. The rest of the
screen sounds exactly the same as before.

### Turn it on

1. In MouseMusic, tick **Taskbar notes** (next to *Hold notes*).
2. In Windows, open **Settings → Personalization → Taskbar → Taskbar behaviors** and set **Taskbar alignment** to
   **Left**. With centered icons the notes still work, but icons move when apps open and close, so an app won't keep
   its note.
3. Click **Start** and slowly move the mouse along the taskbar. Each icon plays the next note up the scale, and the
   status line shows `Taskbar 3`, `Taskbar 4` and so on.

What you'll hear:

- **Taskbar icons** use their own instrument, so you always know you're on the taskbar.
- **A second monitor's taskbar** (if *Show my taskbar on all displays* is on) plays the same notes on a different
  instrument. The status line shows `Taskbar 2/3` (monitor 2, icon 3).
- **The tray and clock** on the right count down from the highest note, starting at the clock (`Tray 1`). Opening
  apps doesn't change them.
- If you have more icons than notes, the notes start again from the bottom, a little quieter.

### Fine-tuning (settings file)

These settings aren't in the window. Edit `%APPDATA%\MouseMusic\settings.json` (or the `settings.json` next to the exe
in portable mode) while MouseMusic is closed:

| Setting | Default | What it does |
|---|---|---|
| `taskbar_mode` | `false` | Same as the **Taskbar notes** checkbox |
| `taskbar_slot_dip` | `48` | Width of one icon at 100 % scaling. MouseMusic scales it for you at 125/150/200 % |
| `taskbar_offset_dip` | `0` | Space to skip at the left end (e.g. the Start or Widgets button) before the first note |
| `taskbar_low_note` | `48` (C3) | Note of the first icon. The following icons go up the current **Scale** and **Key** |
| `taskbar_high_note` | `96` (C7) | Highest note. Past it, notes start again from `taskbar_low_note` |
| `taskbar_program` | `12` | Instrument for the main taskbar (General MIDI number, 0–127) |
| `taskbar_secondary_program` | `13` | Instrument for taskbars on other monitors |
| `taskbar_monitors` | `"all"` | `"primary"` = only the main taskbar makes notes |
| `taskbar_tray` | `true` | `false` = the tray and clock area are treated as ordinary taskbar slots |
| `taskbar_tray_slot_dip` | `32` | Width of one tray icon at 100 % |

**If notes don't line up with your icons:**

- **Notes change in the middle of an icon:** the slot width doesn't match. Hover slowly from the first icon to the
  last, and count the icons you pass per note change. If each note covers more than one icon, lower
  `taskbar_slot_dip` (e.g. 40). If an icon gets two notes, raise it (e.g. 56). Small-icon taskbar tweaks usually need
  about 32–40.
- **The first note lands on the Start button:** set `taskbar_offset_dip` to roughly the width of what you want to
  skip (about 48 per button at 100 % scaling).
- Different scaling on each monitor is handled automatically, so you don't need separate values.
- Invalid values are reset to the default, and MouseMusic shows *"Some settings were out of range and have been reset."*

**Good to know:**

- Auto-hide taskbars work. Moving to the screen edge plays the icon under the cursor as the taskbar slides in.
- If Windows Explorer restarts, taskbar notes pause for a couple of seconds, then come back by themselves.
