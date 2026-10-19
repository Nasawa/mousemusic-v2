# MouseMusic v2 — UX Spec (P1)

Owner: Pragma (UX) · Implements: Sprite (S6 app shell) · Source of truth for behaviour: `ARCHITECTURE.md`

This doc covers **what the user sees and reads**. If it ever disagrees with `ARCHITECTURE.md`, the architecture wins.
File a note in [Open questions](#10-open-questions).

Design principles:
1. **Silent until asked.** Nothing plays until the user clicks Start or presses Ctrl+Alt+M.
2. **One small window, no menus or dialogs in normal use.** Problems show in the status line, not in pop-ups.
3. **Never a traceback.** Every failure has plain-language copy and one obvious next step.
4. **Stable mapping.** The UI never changes the mapping silently. The sound changes only when the user changes a control.

---

## 1. Main window

- Title: `MouseMusic` (no version in the title bar. Version goes in the tray tooltip and `--version`.)
- Size: **minimum 340 × 360** logical px at 100% scaling, not user-resizable. The width is fixed. The height
  **grows to fit** a wrapped status message and shrinks back to the minimum afterwards (ARCHITECTURE §11 B-2/B-4).
  This supersedes the old ≤ 360×300 budget. Tk handles DPI scaling. Don't hard-code physical px.
  *Implementation note:* main's code still uses a 340 × 330 minimum (`ui/window.py` `HEIGHT`). Sprite changes it to 360.
- Height cap (B-2): the window never grows taller than the **work area** of the monitor it's on. If the wrapped
  status still doesn't fit, the status shows as many whole lines as fit and the last visible line ends with `…`. The
  full text is in the status tooltip and the log. No scrollbar.
- Staying on screen (B-3): whenever the height changes, the window position is re-clamped into its monitor's work
  area with the same `ui/placement.py` logic used on restore (it grows downward, and moves up only if the bottom
  would leave the work area).
- Returning after a clamp (C-1): when the status shrinks again, the window goes back to the position it had **before**
  the temporary clamp move, but only if the user hasn't moved it since. If they have, it stays where they put it. Height
  always follows the content, with a minimum of 340 × 360 and the work-area cap (B-2).
- Screen readers (C-2): the status line's accessible name/description is always the **full** message, even when the
  visible text is truncated with `…`. A changed message is announced **once** (no repeats on re-wrap or resize). Its
  position in the tab order is after Reconnect (keyboard users can reach and re-read it).
- Theme setting (B-1, see §11): `theme` is read case-insensitively (stripped and lowercased, so `" Dark "` → `dark`). Any
  other value → `system` + W3.
- Rows (Q-D1, §12): the Taskbar notes checkbox shares row 7 with Hold notes (no extra row), and the Theme row (8d) is already counted in the 360 minimum (ARCHITECTURE §11 Q-D1).
- Position: saved in `window_x`/`window_y` (logical px, `null` = centre on primary). On load, if the saved point isn't on any monitor's work area, centre the window and don't overwrite the saved values until the user moves it (§11 UX-Q1).
- Icon: `src/mousemusic/assets/icon.ico` (P2).
- Layout: ttk `grid`, two columns (label right-aligned, control left-aligned), 8 px padding, 4 px row gap.

### 1.1 Wireframe

```
┌ MouseMusic  (min 340 × 360, grows to fit) ─ _ ✕ ┐
│                                                 │
│  [ ▶  Start ]                Ctrl+Alt+M         │   row 0  Start/Stop button + hotkey hint
│ ─────────────────────────────────────────────── │
│        Scale  [ Pentatonic major       ▾ ]      │   row 1
│          Key  [ C  ▾ ]                          │   row 2
│  Pitch range  [ C2 ▾ ]  to  [ C7 ▾ ]            │   row 3
│  Instruments  [ Classic (8)     ▾ ] [Preview]   │   row 4  set + Preview (4b)
│       Volume  [━━━━━━━━━━━━●━━━]  80 %          │   row 5
│  Note length  [━━━━●━━━━━━━━━━━]  250 ms        │   row 6
│     [ ] Hold notes (legato)  [ ] Taskbar notes  │   row 7  two checkboxes (§12)
│  MIDI output  [ Microsoft GS Wavetable ▾ ] [⟳]  │   row 8  device + Reconnect
│     Shortcut  [ Ctrl+Alt+M         ▾ ]          │   row 8c global shortcut
│        Theme  [ System (Dark)      ▾ ]          │   row 8d theme (§11)
│ ─────────────────────────────────────────────── │
│  ● Stopped — press Start or Ctrl+Alt+M          │   row 9  status line (wraps)
└─────────────────────────────────────────────────┘
```

Tab order is top to bottom, left to right: Start → Scale → Key → Low → High → Instruments → Preview → Volume → Note length →
Hold notes → Taskbar notes → MIDI output → Reconnect → status line (C-2) → Shortcut → Theme. Start has focus when the window opens.

### 1.2 Controls

| # | Label (exact) | Widget | Values / range | Default | Setting key | Behaviour |
|---|---|---|---|---|---|---|
| 0 | `▶  Start` / `■  Stop` | ttk.Button, default button (Enter / Space) | toggle | `▶  Start` | — (not persisted; `start_on_launch` is file-only) | Posts `start`/`stop` to the engine. The label flips **only after** the engine confirms (so if the open fails, it stays `▶  Start`). Hint text `Ctrl+Alt+M` in grey to the right (shows the shortcut that is **actually active**, which may be the fallback `Ctrl+Alt+Shift+M`; `(shortcut off)` when none) |
| 1 | `Scale` | readonly Combobox | `Chromatic`, `Major`, `Minor`, `Pentatonic major`, `Pentatonic minor`, `Blues` | `Pentatonic major` | `scale` | Applies live while playing |
| 2 | `Key` | readonly Combobox, narrow | `C`, `C♯`, `D`, `E♭`, `E`, `F`, `F♯`, `G`, `A♭`, `A`, `B♭`, `B` | `C` | `root` | Applies live. Disabled (greyed) when Scale = Chromatic, since key has no effect there |
| 3 | `Pitch range` | two readonly Comboboxes + the word `to` | octaves `C0`…`C8` (MIDI 12…108), step 12 | `C2` to `C7` (36–96) | `low_note`, `high_note` | If the user picks low ≥ high, the other box moves so the range is at least one octave (no error). Only octave Cs are offered in the UI. A non-C value from the file shows its note name, e.g. `G2`, as an extra item |
| 4 | `Instruments` | readonly Combobox | `Classic (8)`, `Mellow (6)`, `Percussive (7)`, `Piano only (1)`, `Full GM library (128)` | `Classic (8)` | `instrument_set` | The number is the row count, i.e. how many bands the screen is split into top to bottom. Tooltip on hover: `Top of the screen to bottom: <names>` |
| 4b | `Preview` | small ttk.Button, same row as 4 | — | — | — | Plays a short C-major scale (C4–C5, 8 notes, ~1.5 s) with the set's **first** instrument on the selected MIDI output, in the background. Tooltip `Play a short scale with <name>, the first instrument in this set`. **Disabled while playing/connecting** (tooltip `Stop first to preview an instrument`), while a preview runs, and with no MIDI output. Start cancels a running preview first. Errors use E1–E5 |
| 5 | `Volume` | ttk.Scale + value label | 0–100 %, step 1 | 80 % | `volume` | Label `80 %`. Sent as CC7 Channel Volume (`round(volume*127/100)`) on open, on Start and on every change. Live. `velocity` (default 100) is file-only |
| 6 | `Note length` | ttk.Scale + value label | 50–2000 ms, step 10 | 250 ms | `note_length_ms` | Label `250 ms`. **Disabled** when Hold notes is checked |
| 7 | `Hold notes (legato)` | ttk.Checkbutton | on/off | off | `legato` | When on, a note holds until the cursor enters the next cell or until Stop |
| 7b | `Taskbar notes` | ttk.Checkbutton, same row as 7 | on/off | off | `taskbar_mode` | Each taskbar icon gets its own note. Applies live. See §12 |
| 8 | `MIDI output` | readonly Combobox, ellipsized at ~24 chars, full name in tooltip | WinMM device names | `Microsoft GS Wavetable Synth` | `midi_device` | **Re-enumerates every time the dropdown opens** (§9). Choosing a device while playing silences, closes and reopens (engine `set_device`). If the list is empty the combobox shows `No MIDI output found` and is disabled |
| 8b | `⟳` (tooltip `Reconnect`) | small ttk.Button | — | — | — | Closes and reopens the selected device. Use it after unplugging headphones etc. Status: `Reconnecting…` then the normal status |
| 8c | `Shortcut` | readonly Combobox | `Ctrl+Alt+M`, `Ctrl+Alt+Shift+M`, `Ctrl+Alt+P`, `Ctrl+Alt+F9`, `Off` (a custom value from the file is listed first) | `Ctrl+Alt+M` | `hotkey` | Re-registers live on change. If the chosen key is taken, `Ctrl+Alt+Shift+M` is tried as a fallback (W7); if both fail, W4 |
| 8d | `Theme` | readonly Combobox | `System (Light)` / `System (Dark)`, `Light`, `Dark` | `System (…)` | `theme` | Applies live. See §11 Dark mode |
| 9 | status line | ttk.Label, **wraps** to the window width | see §1.3 | — | — | Coloured dot + text. Long messages wrap onto more lines and the window grows taller to fit (shrinking back afterwards). Truncated with `…` only when the window has reached the work-area height (§1, B-2); the full text is then in the tooltip. Errors stay until resolved. They are never auto-dismissed |

All settings save automatically (debounced 500 ms, per §4). There is **no Save, Apply, or OK button.**

Not in the UI by design (file-only, per §4/§5/§11): `velocity`, `poll_hz`, `screen_mode`, `start_on_launch`, hysteresis. `hotkey` is also editable in the file: modifiers Ctrl/Alt/Shift/Win in any order plus A–Z, 0–9 or F1–F12 (e.g. `Ctrl+Alt+M`), or `Off`; it is normalised (`alt+ctrl+m` → `Ctrl+Alt+M`) and an invalid value resets to `Ctrl+Alt+M` (W3).

### 1.3 Status line

Format while playing: `<dot> <Note> · <Instrument> · <Device>`, where the device name is shortened to ~20 chars with `…`.

| State | Dot | Text (exact) |
|---|---|---|
| Stopped (normal) | grey `●` | `Stopped — press Start or Ctrl+Alt+M` |
| Playing, before first note | green `●` | `Playing — move the mouse · Microsoft GS Wavetable…` |
| Playing | green `●` | `E4 · Vibraphone · Microsoft GS Wavetable…` |
| Opening / reconnecting | grey `●` | `Connecting to <device>…` / `Reconnecting…` |
| Warning (still works) | amber `▲` | warning text from §4 |
| Error (can't play) | red `■` | error text from §4 |

Tray icon per state (P2, `src/mousemusic/assets/icons/`): Stopped → `tray-idle.ico`, Playing → `tray-playing.ico`, Error → `tray-error.ico`. Warnings keep the idle or playing icon.

- Note names use sharps for display (`C♯4`) unless the key is a flat key (`F`, `B♭`, `E♭`, `A♭`), in which case flats are used. Octave numbering: middle C = `C4` (MIDI 60).
- Instrument names come from `instruments.py` (title case, e.g. `Nylon Guitar`).
- The status updates at most every 50 ms (the `root.after(50)` drain). Show the latest only.
- The dot shape changes as well as the colour (●/▲/■), so colour isn't the only signal.

### 1.4 Window behaviour

- **Close (✕):** hides the window to the tray. Playback **continues** if it was playing. The first time only, show a
  tray balloon notification (see §2.3). The architecture calls this a "one-time tooltip".
- **Minimize (_):** normal taskbar minimize.
- **Second launch:** the existing window is shown, restored and focused. The second process exits silently.
- **Esc** in the window: hides to tray (same as ✕, no balloon).

---

## 2. Tray icon

### 2.1 Icon & tooltip
- Icon: `src/mousemusic/assets/icon.ico`. Two variants (P2 delivers both): **idle** (normal) and **playing** (with a small green dot
  or note badge), so state shows at a glance. Until P2 lands, Sprite uses one icon.
- Tooltip (hover), exact:
  - Stopped: `MouseMusic vX.Y.Z — Stopped · Ctrl+Alt+M`
  - Playing: `MouseMusic vX.Y.Z — Playing · Ctrl+Alt+M`
  (` · <shortcut>` names the active shortcut and is omitted when the shortcut is off.)
  - Error: `MouseMusic vX.Y.Z — No sound (click for details)`
  (Windows caps tooltips at 127 chars. These are well under.)
- **Left-click (default action):** Show window. (pystray `default=True` on "Show window".)

### 2.2 Menu (exact order and labels)

```
  Start                  Ctrl+Alt+M     ← text toggles to "Stop" while playing
  Show window                           ← bold (default item)
  ─────────────
  Quit
```

| Item | Label | Behaviour |
|---|---|---|
| 1 | `Start` / `Stop` | Same as the window button. The hotkey hint is optional, only if pystray can render it. Otherwise the label alone |
| 2 | `Show window` | Shows, restores and focuses the window. Default item |
| — | separator | |
| 3 | `Quit` | Silences (note-off, All Notes Off, reset), closes the device, saves settings, exits. No confirmation |

No checked states in v0.1. The architecture limits the menu to these three items. No extras in v0.1 (§11 UX-Q3).

### 2.3 Notifications (tray balloons)
Used only for these cases (they are seen when the window is hidden):

| When | Title | Body |
|---|---|---|
| First close-to-tray | `MouseMusic is still running` | `It's in the system tray. Right-click the icon to quit.` (If playing: `It's still playing in the system tray. Press Ctrl+Alt+M to stop, or right-click the icon to quit.`) |
| Device lost while window hidden | `MouseMusic stopped` | `Lost connection to <device>. Open MouseMusic from the tray icon.` |
| Hotkey couldn't register (startup) | — | Not a balloon: status-line warning only (§4) |

After the first-close balloon, set `tray_hint_shown = true` (default `false`). It is separate from `first_run_done` (§11 UX-Q2).

---

## 3. First-run flow

"First run" means `first_run_done` is `false` or the settings file doesn't exist.

1. User double-clicks `MouseMusic-vX.Y.Z-win64.exe`. (SmartScreen "Windows protected your PC" → *More info → Run
   anyway* is covered by the README, P4. The app can't affect it.)
2. Splash: none. The window should appear within 3 s (§10 S7 AC). Show the window as soon as Tk is up, then enumerate devices.
3. Window opens centred, Stopped, Start focused. The tray icon appears.
4. Status line on first run shows a one-line hint instead of the normal stopped text:
   `Click Start, then move your mouse. Left↔right = pitch, up↕down = instrument.`
   This shows until the first Start.
5. Device check (runs during step 3):
   - Saved/default device present → nothing extra.
   - Default missing but other devices exist → select device 0, amber warning W1 (§4).
   - No devices → red error E1. Start is disabled.
6. User clicks Start (or Ctrl+Alt+M). The device opens and the status goes `Connecting…` then `Playing — move the mouse`.
7. Moving the mouse plays notes. Set `first_run_done = true` on the **first successful Start**, not at launch, so a user
   who quits right away sees the hint again next time.
8. First ✕ → hide to tray + first-close balloon (§2.3), shown only while `tray_hint_shown` is `false`, then set it to `true`.

No wizard, no welcome dialog, no EULA screen.

---

## 4. Errors and warnings

Rules: status line only, no modal dialogs (the one exception is F1, a fatal startup error, which has no window to show
a status in). Plain words, no error codes in the main text. The code goes to the log. Each message says **what happened
+ what to do**. Where a link helps, the status line shows a clickable `Help` link at the end that opens the
README troubleshooting anchor in the browser.

README anchors (P4 must create them): `#no-sound`, `#no-midi-device`, `#device-busy`, `#settings-reset`.

### Errors (red ■, playback cannot happen or has stopped)

| ID | Cause (from spec) | Exact message | Recovery / UI behaviour |
|---|---|---|---|
| **E1** | No MIDI output devices: `midiOutGetNumDevs() == 0` (e.g. N/KN editions with GS synth removed) | `No MIDI output found. Install a MIDI synth, then click ⟳.  Help` | Start disabled. Device combo shows `No MIDI output found`, disabled. ⟳ and opening the dropdown re-enumerate. If a device appears, clear the error, select it and enable Start. Help → `#no-midi-device`. App keeps running |
| **E2** | Device busy, held by another app: `MMSYSERR_ALLOCATED` on open | `<device> is being used by another app. Close it, or pick another output.  Help` | Start reverts to `▶  Start`. User can pick another device or click ⟳/Start to retry. Help → `#device-busy` |
| **E3** | Other open failure (`MMSYSERR_BADDEVICEID`, `MMSYSERR_NODRIVER`, `MMSYSERR_NOMEM`, unknown) | `Couldn't open <device>. Try ⟳ or pick another output.  Help` | As E2. Log the MMSYSERR code. Help → `#no-sound` |
| **E4** | Device lost mid-play: `midiOutShortMsg` returns an error (unplugged USB synth, driver reset) | `Lost connection to <device>. Playback stopped. Click ⟳ to reconnect.` | Engine silences (best effort) and stops. Button → `▶  Start`. Tray balloon if the window is hidden (§2.3). Start auto-reopens (§9) |
| **E5** | Unexpected engine exception (top-level handler) | `Something went wrong and playback stopped. Click Start to try again.` | Silence paths run (§5). Full traceback goes to the log only. Repeated failures: same text. User can open the log via `--log-level` / README |

### Warnings (amber ▲, app still works)

| ID | Cause | Exact message | Recovery |
|---|---|---|---|
| **W1** | Saved `midi_device` not found at startup or after re-enumeration. Falls back to device 0 (§9) | `"<saved device>" not found. Using <device 0> instead.` | Auto-selected. Clears on the next Start or on the user picking any device. The fallback is never written to `midi_device`. Only an explicit user pick writes it. W1 shows on each launch while the saved device is missing. Start/⟳ re-enumerate and reopen the saved device by name if it has come back (§11 UX-Q4, OQ-12) |
| **W2** | Settings file corrupt → renamed `settings.json.bak`, defaults loaded (§4) | `Your settings file couldn't be read, so defaults were restored. The old file was saved as settings.json.bak.` | Shown at startup until the first Start or 15 s, whichever is later. Help → `#settings-reset` |
| **W3** | Some settings values invalid → clamped or reset (§4) | `Some settings were out of range and have been reset.` | Same dismissal as W2. Details go in the log |
| **W4** | Global shortcut unavailable: `RegisterHotKey` fails for the configured shortcut **and** the `Ctrl+Alt+Shift+M` fallback | `Ctrl+Alt+M and Ctrl+Alt+Shift+M are in use by other apps, so the shortcut is off. Use the Start button.` (if the configured key *is* the fallback: `Ctrl+Alt+Shift+M is in use by another app, so the shortcut is off. Use the Start button.`) | The hint next to Start changes to `(shortcut off)` in grey. App works normally otherwise. Clears after 15 s. The hint stays. Not shown when Shortcut = `Off` |
| **W7** | Configured shortcut taken, fallback `Ctrl+Alt+Shift+M` registered | `Ctrl+Alt+M is in use by another app, so the shortcut is Ctrl+Alt+Shift+M instead.` | Clears after 15 s. The hint, stopped status and tray tooltip show the active shortcut |
| **W5** | Settings can't be saved (APPDATA read-only, disk full, portable exe on a read-only stick) | `Settings can't be saved right now. Changes will last until you quit.` | Show once per session. Retry on the next change. Log the path and the OS error |
| **W6** | Audio endpoint changed (headphones unplugged) and the GS synth may go silent. Not detectable by WinMM, so this is **not an automatic message**. It's covered by the ⟳ tooltip and README `#no-sound` | — | ⟳ Reconnect |

### Fatal (modal, only before the window exists)

| ID | Cause | Message (Windows MessageBox, title `MouseMusic`) |
|---|---|---|
| **F1** | Tk/UI can't start or a startup crash before the window | `MouseMusic couldn't start.\n\nA log was saved to:\n%LOCALAPPDATA%\MouseMusic\logs\mousemusic.log` [OK] |

Precedence when several apply: Error > Warning > first-run hint > normal status. Only one message shows at a time.
When the error clears, show the next pending warning, if any, then the normal status.

### CLI (support) copy
- `--list-devices` with zero devices prints `No MIDI output devices found.` and exits 0.
- Otherwise it prints `0: Microsoft GS Wavetable Synth`, one per line.
- `--play-instrument <program>` (GM program 0–127) plays the same short scale as Preview on the saved device (or the §9 fallback), prints `Playing GM program 40 (Violin)...` then `Done: played on <device>.`, and exits 0. An invalid program prints `--play-instrument needs a GM program number from 0 to 127 (<detail>).` to stderr and exits 2. A MIDI error prints the E1–E5 status text to stderr and exits 1. Works with `--dry-run` and `--portable`.

---

## 5. Keyboard

| Key | Scope | Action |
|---|---|---|
| `Ctrl+Alt+M` (configurable, fallback `Ctrl+Alt+Shift+M`) | **Global** (`RegisterHotKey`) | Toggle Start/Stop, even when the window is hidden |
| `Space` / `Enter` | Window, Start focused | Toggle |
| `Tab` / `Shift+Tab` | Window | Move focus (order in §1.1) |
| `Alt+↓` or `F4` | Combobox | Open the list (standard ttk) |
| `←` `→` | Slider | Step (Volume ±1 %, Note length ±10 ms). `PgUp`/`PgDn` ±10 % / ±100 ms |
| `Esc` | Window | Hide to tray |

Mnemonic underlines (Alt+letter) are deferred to P2.

---

## 6. Copy style guide

- **Voice:** plain, calm, second person, short. Say "MIDI output", not "WinMM device" or "port".
- **Sentence case** for labels and messages (`Note length`, `Show window`). Product name always `MouseMusic`, one word, with a capital M in both halves.
- **Messages:** what happened + what to do, ≤ ~90 characters for the status line. No exclamation marks, no "Oops", no
  blame ("you"), no error codes in the UI (log them).
- Device names are shown verbatim, in quotes only when reporting one missing.
- Use the real characters: `—` em dash, `…` ellipsis, `·` middle dot, `♯` `♭`.
- Numbers come with their units: `250 ms`, `80 %`.
- Buttons are verbs (`Start`, `Stop`, `Quit`). Don't add "Are you sure?".
- All strings live in one module (e.g. `ui/strings.py`) so P2/P4 can edit copy without touching logic. This is a suggestion, not a spec change.

---

## 7. Mapping to architecture

| UX element | Architecture ref |
|---|---|
| Off at launch, hotkey, controls list, close-to-tray, status format | §2 |
| Settings keys/defaults, autosave, portable, corrupt → .bak | §4 |
| Scales, sets, legato, silence paths | §5 |
| Status via queue / 50 ms drain, tray callbacks post commands | §6 |
| E1/E2/W1, re-enumerate on dropdown open, Reconnect, single-instance focus | §9 |

## 8. Acceptance checklist for S6
- [ ] Window matches §1.1 order and §1.2 labels exactly, minimum 340×360 at 100%, grows to fit, never taller than the work area and always inside it (B-2/B-3).
- [ ] Every control applies live and persists across restarts.
- [ ] Start label flips only on engine confirmation. Failures show E-copy.
- [ ] Tray menu has exactly `Start/Stop`, `Show window` (default), separator, `Quit`. The tooltip matches §2.1.
- [ ] First run shows the hint, and `first_run_done` is set on the first successful Start.
- [ ] E1–E5 and W1–W5 are reachable (with `--dry-run`/fake backend errors) and show the exact copy.

## 9. Out of scope (later tasks)
Icon art and theming (P2), instrument set names/contents after listen test (P3), README anchors and SmartScreen steps (P4).

---

## 10. Open questions — all resolved

All of these were resolved by Archimedes in `ARCHITECTURE.md` §11. That section is binding, and this doc has been updated to match.

| # | Question | Resolution (§11) |
|---|---|---|
| Q1 | Window position persistence | ✅ `window_x`/`window_y`, logical px, `null` = centre. Off-screen → centre, no overwrite until moved (§1) |
| Q2 | First-close balloon flag | ✅ `tray_hint_shown` (default `false`), separate from `first_run_done` (§2.3, §3) |
| Q3 | Tray extras | ✅ None in v0.1. Start/Stop, Show window, separator, Quit (§2.2) |
| Q4 | Fallback device persistence | ✅ Never written to `midi_device`. W1 shows each launch while missing. The saved device is reopened when it's back (§4 W1) |
| Q5 | Volume scale | ✅ `volume` 0–100 % (default 80) → CC7. `velocity` file-only, default 100 (§1.2) |
| Q6 | Pitch-range granularity | ✅ Octave Cs (C0–C8) only. Semitones JSON-only, shown as an extra item (§1.2) |
| Q7 | Help link target | ✅ `https://github.com/Nasawa/mousemusic-v2#<anchor>`, anchors defined in `ui/strings.py`. P4 keeps them (§4) |
| Q8 | Mid-play device-loss detection | ✅ Any non-zero `midiOutShortMsg` → silence, close, stop (E4). No polling or auto-reconnect. Silent endpoint changes → manual ⟳ (W6) |

---

## 11. Dark mode (issue #21)

Targeted for rc3/rc4. Goal: the window looks native next to other Windows 11 apps in both themes, follows the
Windows app theme by default, and can be overridden. Nothing here changes audio or the engine.

### 11.1 Control and setting

| Item | Spec |
|---|---|
| Label | `Theme` (row 8d, below `Shortcut`, above the status separator, see §1.1). Last in tab order |
| Widget | readonly ttk.Combobox, width 18 |
| Values (exact) | `System (Light)` or `System (Dark)` (first item; the suffix shows what Windows is set to right now), `Light`, `Dark` |
| Settings key | `theme`: `"system"` \| `"light"` \| `"dark"`. Default **`"system"`**. Unknown value → `"system"` with W3 (same as other enums, §11 OQ-8) |
| Behaviour | Applies live on selection, no restart. Saved with the normal 500 ms debounce |
| Height | Minimum 340 × 360, grows to fit (ARCHITECTURE §11 Q-D1) |

Resolving the effective theme (pure function, testable without Windows):
1. If Windows **high contrast** is on → `high_contrast` (§11.6). The `theme` setting is ignored but kept.
2. Else if `theme` is `light` or `dark` → that.
3. Else (`system`) read `HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize`, DWORD
   `AppsUseLightTheme`: `0` → dark, `1` → light. Missing key or value, or read error → **light** (and log at debug).
   Note: use `AppsUseLightTheme`, not `SystemUsesLightTheme` (that one is for the taskbar).

### 11.2 Following live Windows changes

- **Primary: `WM_SETTINGCHANGE`.** Windows broadcasts it to top-level windows when the app theme changes, with
  `lParam` = the string `"ImmersiveColorSet"`. High-contrast toggles arrive as `WM_SETTINGCHANGE` with
  `wParam == SPI_SETHIGHCONTRAST` (0x0043). The existing hidden message window on the hotkey thread (§6, which
  already receives power and session broadcasts) handles both and posts `("theme_changed", None)` to `ui_queue`.
  The Tk thread re-resolves and re-applies the theme. No new thread.
- **Backup:** re-resolve when the main window gains focus (`<FocusIn>` on root), in case the broadcast was missed
  (defensive only: the message window is a top-level window, so it does receive broadcasts). Cheap: one registry read.
- **No polling timer.**
- Debounce: one Windows theme switch sends several broadcasts. Coalesce re-applies to at most one per 250 ms.
- When `theme` is `light` or `dark`, Windows changes don't affect the window, but `System (…)` still updates its suffix.

### 11.3 Title bar

- After the Tk root exists and **before it is first shown** (it starts withdrawn; see `app._run_app`), get the
  frame window handle with `GetParent(root.winfo_id())`, then call
  `DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, &BOOL(dark), sizeof(BOOL))`:
  1. attribute **20** (Windows 10 20H1+ and Windows 11);
  2. if that returns a failure HRESULT, retry with **19** (older Windows 10 builds 17763–18985);
  3. if both fail or `dwmapi` isn't present → do nothing (light title bar, log at debug). It never raises.
- Live change: set the attribute again, then force a non-client repaint, so Windows 10 updates without a restart:
  `SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOMOVE|SWP_NOSIZE|SWP_NOZORDER|SWP_FRAMECHANGED)`.
- High contrast: always pass `FALSE` (the system draws the title bar in high-contrast colours).
- Tooltips are `overrideredirect` windows with no title bar. They only need palette colours.
- Optional, not required: on Windows 11 22H2+ the caption colour could match `bg` via `DWMWA_CAPTION_COLOR` (35). Leave
  it out of v0.x.

### 11.4 Palette tokens

Theme engine: **ttk `clam`** for both Light and Dark. It's the stdlib theme that honours every colour option. `vista`
ignores most of them. Fonts and spacing are unchanged (Segoe UI 9 via `TkDefaultFont`). The light palette
deliberately looks close to Windows 11 light, so switching from `vista` to `clam` doesn't feel like a different app.

| Token | Light | Dark | Used for |
|---|---|---|---|
| `bg` | `#F3F3F3` | `#202020` | Root window, frames, labels, separator gaps, checkbutton background |
| `surface` | `#FFFFFF` | `#2D2D2D` | Combobox field, button face, popdown list, tooltip background |
| `surface_hover` | `#F0F0F0` | `#383838` | Button and combobox `active` state |
| `text` | `#1B1B1B` | `#F3F3F3` | All labels, field text, status text, button text |
| `text_secondary` | `#5C5C5C` | `#B8B8B8` | Hotkey hint next to Start, value labels (`80 %`, `250 ms`) |
| `border` | `#8A8A8A` | `#8A8A8A` | Field and button borders, separators, checkbox outline |
| `accent` | `#4F46E5` | `#5B54E8` | Start button face (default button), checkbox check fill |
| `on_accent` | `#FFFFFF` | `#FFFFFF` | Text and glyphs on `accent` |
| `focus` | `#4F46E5` | `#A5A0FF` | Focus ring (`focuscolor`), focused field border |
| `disabled_text` | `#9E9E9E` | `#6E6E6E` | Text of disabled widgets (Key on Chromatic, Note length with legato, empty MIDI output) |
| `disabled_surface` | `#F7F7F7` | `#262626` | Field background when disabled |
| `track` | `#8A8A8A` | `#8A8A8A` | Slider trough |
| `thumb` | `#4F46E5` | `#A5A0FF` | Slider handle |
| `select_bg` / `select_fg` | `#4F46E5` / `#FFFFFF` | `#4F46E5` / `#FFFFFF` | Selected row in the popdown list, selected text in combobox field |
| `link` | `#4338CA` | `#A5A0FF` | `Help` link in the status line (replaces the hard-coded `#2563EB`) |
| `dot_idle` | `#6B6B6B` | `#A3A3A3` | Status dot: Stopped, Connecting (replaces `GREY`) |
| `dot_ok` | `#15803D` | `#4ADE80` | Status dot: Playing (replaces `GREEN`) |
| `warn` | `#A14A06` | `#FBBF24` | Status ▲ warning glyph (replaces `AMBER`) |
| `error` | `#B91C1C` | `#F87171` | Status ■ error glyph (replaces `RED`) |

The status *text* always uses `text`. Only the glyph is coloured, and the glyph shape (●/▲/■) already carries the
meaning (§1.3). `status.py` returns a semantic colour role (`idle`/`ok`/`warn`/`error`) instead of a hex value. The
window maps the role to the active palette.

### 11.5 Widget mapping

All via `ttk.Style` on `clam`, with `style.configure` plus `style.map` for states. Re-run the whole function on every theme change.

| Widget / style | Options |
|---|---|
| root `tk.Tk`, tooltip `tk.Toplevel` | `configure(bg=bg)` (tk, not ttk, so it must be set directly) |
| `.` (defaults) | `background=bg, foreground=text, bordercolor=border, focuscolor=focus, troughcolor=track, selectbackground=select_bg, selectforeground=select_fg, insertcolor=text`; map `foreground` `disabled → disabled_text` |
| `TFrame`, `TLabel` | `background=bg, foreground=text` |
| `Hint.TLabel` (new; replaces `foreground="grey"`) | `foreground=text_secondary` |
| `Value.TLabel` (volume and note length values) | `foreground=text_secondary` |
| `Link.TLabel` (Help) | `foreground=link`, underlined font as now |
| `Status.TLabel` / `Dot.TLabel` | text `text`. Dot foreground is set per state from `dot_idle`/`dot_ok`/`warn`/`error` |
| `Tooltip.TLabel` | `background=surface, foreground=text, bordercolor=border`, relief solid 1 |
| `TButton` (⟳) | `background=surface, foreground=text, bordercolor=border, lightcolor=surface, darkcolor=surface`; map `active → surface_hover`, `pressed → border`, `disabled → disabled_surface/disabled_text`, `focus → bordercolor focus` |
| `Accent.TButton` (Start/Stop) | `background=accent, foreground=on_accent`; map `active` → `accent` with hover lighten 8 %, `focus` → `bordercolor focus` |
| `TCombobox` | `fieldbackground=surface, background=surface, foreground=text, arrowcolor=text, bordercolor=border, lightcolor=surface, darkcolor=surface`; map `readonly` `fieldbackground → surface` (clam greys readonly fields otherwise), `focus → bordercolor focus`, `disabled → fieldbackground disabled_surface, foreground disabled_text, arrowcolor disabled_text`, `selectbackground/selectforeground` in readonly focus → `surface`/`text` (so a readonly field doesn't show a blue selection highlight) |
| Combobox **popdown list** (a classic `tk.Listbox`, not themed by ttk) | Before creating any combobox: `root.option_add("*TCombobox*Listbox.background", surface)`, and likewise `foreground=text`, `selectBackground=select_bg`, `selectForeground=select_fg`, `font=TkDefaultFont`, `borderWidth=0`. The popdown's scrollbar uses `*TCombobox*Listbox` siblings. Style `Vertical.TScrollbar` with `background=surface, troughcolor=bg, arrowcolor=text`. **Live change:** `option_add` only affects new widgets, so for each existing combobox: `pd = root.tk.call("ttk::combobox::PopdownWindow", combo)` then `root.tk.call(f"{pd}.f.l", "configure", "-background", surface, ...)` |
| `TCheckbutton` (Hold notes) | `background=bg, foreground=text, indicatorbackground=surface, indicatorforeground=on_accent, upperbordercolor=border, lowerbordercolor=border`; map `selected → indicatorbackground accent`, `active → background bg`, `disabled → foreground disabled_text` |
| `Horizontal.TScale` | `troughcolor=track, background=thumb, bordercolor=thumb, lightcolor=thumb, darkcolor=thumb`; map `active → background focus`, `disabled → background disabled_text`. Clam draws the trough with `bordercolor`, so set it to `track` on the trough element via `Horizontal.Scale.trough` `troughcolor` and keep the slider at `thumb` |
| `TSeparator` | `background=border` |

### 11.6 High contrast

- Detect with `SystemParametersInfoW(SPI_GETHIGHCONTRAST)` and the `HCF_HIGHCONTRASTON` flag, at startup and on `WM_SETTINGCHANGE`.
- When it's on, **don't apply any palette.** Use the `vista` theme (on Windows, `winnative` if `vista` is missing), no
  `option_add` colours, and Tk's system colour names (`SystemButtonFace`, `SystemWindowText`, `SystemHighlight`), so
  the user's high-contrast colours win. Status glyphs use `SystemWindowText` (the shape carries the state). Dark title
  bar attribute is `FALSE`.
- The `Theme` combobox stays enabled and its setting is saved, but it has no visible effect. Its tooltip reads
  `Windows high contrast is on, so MouseMusic uses your contrast colours.`
- Turning high contrast off re-applies the saved theme live.

### 11.7 Tray icon, menu and notifications

- **Icon:** the existing indigo tile (`#4F46E5`) with a white glyph is a solid shape, so it reads on both taskbar
  colours. Measured contrast of the tile edge: 5.67:1 vs the light taskbar `#F3F3F3`, and 2.59:1 vs the dark taskbar
  `#202020`. Below 3:1 on dark, but the white glyph inside is 6.29:1 against the tile, and the glyph is what the eye
  reads (the same approach as many coloured-tile tray icons). **No separate dark-taskbar icon set is required.** The
  idle/playing/error badges keep their white ring, which separates them from any taskbar colour. Taskbar colour comes
  from `SystemUsesLightTheme`, not from the app theme, so the tray icon must **not** follow the `theme` setting.
- **Menu:** pystray uses a native Win32 popup menu. Windows draws it in the classic light style unless the process
  opts in through undocumented `uxtheme` ordinals (`SetPreferredAppMode`, #135). **v0.x: leave the tray menu native/light.**
  That's consistent with many Win32 apps (see Q-D3). Labels are unchanged.
- **Notifications:** balloons and toasts are drawn by Windows and follow the system theme automatically. No work needed.
- **High contrast:** Windows renders the menu and notifications in high-contrast colours. The icon is unchanged.

### 11.8 New wording

| Where | Text |
|---|---|
| Label | `Theme` |
| Values | `System (Light)`, `System (Dark)`, `Light`, `Dark` |
| Combobox tooltip (normal) | `System follows your Windows app theme.` |
| Combobox tooltip (high contrast) | `Windows high contrast is on, so MouseMusic uses your contrast colours.` |
| W3 (existing) | Reused for an invalid `theme` value. No new message |

### 11.9 Contrast results

Computed with `tools/contrast.py` (WCAG 2.x relative luminance; the script exits non-zero on any failure, and CI can
run it). Thresholds: text ≥ 4.5:1, UI components and focus indicators ≥ 3:1. Disabled controls are exempt (WCAG
1.4.3), but are still kept distinguishable.

| Theme | Foreground | Background | Ratio | Min | Result |
|---|---|---|---|---|---|
| light | `text` #1B1B1B | `bg` #F3F3F3 | 15.52:1 | 4.5 | pass |
| light | `text` #1B1B1B | `surface` #FFFFFF | 17.22:1 | 4.5 | pass |
| light | `text_secondary` #5C5C5C | `bg` #F3F3F3 | 6.03:1 | 4.5 | pass |
| light | `text_secondary` #5C5C5C | `surface` #FFFFFF | 6.69:1 | 4.5 | pass |
| light | `on_accent` #FFFFFF | `accent` #4F46E5 | 6.29:1 | 4.5 | pass |
| light | `select_fg` #FFFFFF | `select_bg` #4F46E5 | 6.29:1 | 4.5 | pass |
| light | `link` #4338CA | `bg` #F3F3F3 | 7.12:1 | 4.5 | pass |
| light | `warn` #A14A06 | `bg` #F3F3F3 | 5.41:1 | 4.5 | pass |
| light | `error` #B91C1C | `bg` #F3F3F3 | 5.83:1 | 4.5 | pass |
| light | `border` #8A8A8A | `surface` #FFFFFF | 3.45:1 | 3.0 | pass |
| light | `border` #8A8A8A | `bg` #F3F3F3 | 3.11:1 | 3.0 | pass |
| light | `focus` #4F46E5 | `bg` #F3F3F3 | 5.67:1 | 3.0 | pass |
| light | `focus` #4F46E5 | `surface` #FFFFFF | 6.29:1 | 3.0 | pass |
| light | `track` #8A8A8A | `bg` #F3F3F3 | 3.11:1 | 3.0 | pass |
| light | `thumb` #4F46E5 | `bg` #F3F3F3 | 5.67:1 | 3.0 | pass |
| light | `accent` #4F46E5 | `bg` #F3F3F3 | 5.67:1 | 3.0 | pass |
| light | `dot_idle` #6B6B6B | `bg` #F3F3F3 | 4.80:1 | 3.0 | pass |
| light | `dot_ok` #15803D | `bg` #F3F3F3 | 4.52:1 | 3.0 | pass |
| light | `disabled_text` #9E9E9E | `bg` #F3F3F3 | 2.41:1 | — | exempt (disabled) |
| dark | `text` #F3F3F3 | `bg` #202020 | 14.68:1 | 4.5 | pass |
| dark | `text` #F3F3F3 | `surface` #2D2D2D | 12.41:1 | 4.5 | pass |
| dark | `text_secondary` #B8B8B8 | `bg` #202020 | 8.21:1 | 4.5 | pass |
| dark | `text_secondary` #B8B8B8 | `surface` #2D2D2D | 6.94:1 | 4.5 | pass |
| dark | `on_accent` #FFFFFF | `accent` #5B54E8 | 5.41:1 | 4.5 | pass |
| dark | `select_fg` #FFFFFF | `select_bg` #4F46E5 | 6.29:1 | 4.5 | pass |
| dark | `link` #A5A0FF | `bg` #202020 | 7.04:1 | 4.5 | pass |
| dark | `warn` #FBBF24 | `bg` #202020 | 9.76:1 | 4.5 | pass |
| dark | `error` #F87171 | `bg` #202020 | 5.89:1 | 4.5 | pass |
| dark | `border` #8A8A8A | `surface` #2D2D2D | 3.99:1 | 3.0 | pass |
| dark | `border` #8A8A8A | `bg` #202020 | 4.72:1 | 3.0 | pass |
| dark | `focus` #A5A0FF | `bg` #202020 | 7.04:1 | 3.0 | pass |
| dark | `focus` #A5A0FF | `surface` #2D2D2D | 5.95:1 | 3.0 | pass |
| dark | `track` #8A8A8A | `bg` #202020 | 4.72:1 | 3.0 | pass |
| dark | `thumb` #A5A0FF | `bg` #202020 | 7.04:1 | 3.0 | pass |
| dark | `accent` #5B54E8 | `bg` #202020 | 3.01:1 | 3.0 | pass |
| dark | `dot_idle` #A3A3A3 | `bg` #202020 | 6.46:1 | 3.0 | pass |
| dark | `dot_ok` #4ADE80 | `bg` #202020 | 9.35:1 | 3.0 | pass |
| dark | `disabled_text` #6E6E6E | `bg` #202020 | 3.20:1 | — | exempt (disabled) |


Notes: dark `accent` vs `bg` is 3.01:1, right at the limit, so don't darken it. Light `border` vs `bg` is 3.11:1, so
borders sit on `surface` fields (3.45:1) where it matters.

### 11.10 Build checklist (Sprite)

- [ ] `config.py`: add `theme: str = "system"` (enum `system|light|dark`, invalid → default + W3). Round-trip test.
- [ ] `ui/theme.py` (new, pure, no Tk import at module level): `PALETTES`, `resolve(theme, apps_use_light, high_contrast) -> "light"|"dark"|"high_contrast"`, tests for every combination.
- [ ] `platform/win_theme.py`: `apps_use_light_theme() -> bool | None` (winreg), `high_contrast_on() -> bool`, `set_dark_title_bar(hwnd, dark) -> bool` (attr 20 then 19, then `SWP_FRAMECHANGED`). All failures return a value, never raise.
- [ ] Message window: handle `WM_SETTINGCHANGE` (`"ImmersiveColorSet"` or `SPI_SETHIGHCONTRAST`) → post `theme_changed`. Coalesce to 250 ms on the Tk side. Re-resolve on root `<FocusIn>`.
- [ ] `window.py`: `apply_theme(palette)` configures every style in §11.5 and the root `bg`, re-skins existing combobox popdowns, and updates tooltips. Call it **before** the first `deiconify()` (no light flash) and on each change.
- [ ] Remove hard-coded colours: `foreground="grey"` (hint) → `Hint.TLabel`; `#2563EB` (Help) → `Link.TLabel`; `status.py` `GREY/GREEN/AMBER/RED` → roles mapped to palette tokens.
- [ ] Start/Stop uses `Accent.TButton`.
- [ ] Theme combobox row 8d, values per §11.8 with a live `System (…)` suffix. Tab order last.
- [ ] High contrast path per §11.6.
- [ ] Tray: no changes (icon and menu as §11.7).
- [ ] `tools/contrast.py` passes, and is optionally added to CI.
- [ ] Manual check on Windows 11: switch Settings → Personalization → Colors → *Choose your mode* while the app is open and stopped and playing. The title bar, window, open popdown and tooltips all flip within ~1 s, with no restart and no audio glitch. Repeat with high contrast (Left Alt+Left Shift+Print Screen). Check at 100 % and 150 % scaling.

### 11.11 Open questions (dark mode) — all resolved

Resolved by Archimedes in ARCHITECTURE.md §11 (5ef93d1). That section is binding.

| # | Question | Resolution |
|---|---|---|
| Q-D1 | Window height | ✅ No "More…" area. Minimum **340 × 360**, grows to fit. The P1 ≤ 360×300 budget is superseded |
| Q-D2 | `theme` in the settings schema | ✅ Added to §4 defaults (`"system"`), validated like other enums (unknown or wrong type → `system` + W3). No `schema` bump |
| Q-D3 | Dark tray menu | ✅ Stays light (system default) in v0.x. No undocumented `uxtheme` ordinals |
| Q-D4 | Theme engine | ✅ Stdlib `clam` with our palette tokens. No `sv-ttk` |
| Q-D5 | Message window receives broadcasts | ✅ Yes, it's a hidden top-level window (answered from the code) |

---

## 12. Taskbar notes (CG-P1, design #23 / issue #16)

Behaviour is defined in `docs/design/cell-granularity.md` (PR #23). This section covers only what the user sees.
If the two disagree, the design doc wins for behaviour and this doc wins for wording (ARCHITECTURE §11 A-6).

### 12.1 Control

| Item | Spec |
|---|---|
| Label (exact) | `Taskbar notes` |
| Widget | `ttk.Checkbutton` on **row 7, right of `Hold notes (legato)`**, in the same frame. No extra row, so the window stays at its minimum height |
| Tooltip (exact) | `Each taskbar icon gets its own note. Works best with taskbar icons aligned left.` |
| Settings key / default | `taskbar_mode`, `false`. The other `taskbar_*` keys are file-only (README "Hearing your taskbar") |
| Tab order | … Note length → Hold notes → **Taskbar notes** → MIDI output → … |
| Keyboard | Space toggles it when focused, like every checkbutton |
| Live | Takes effect on the next engine tick. No restart, and no Stop needed while playing |
| Enabled state | Always enabled, even when no taskbar is currently found (it may appear later, see §12.3) |

### 12.2 Status line inside the zone

Format follows the normal `<Note> · <Instrument> · <Device>` (§1.3), with the instrument part replaced by the zone:

| Where the cursor is | Status text (exact pattern) | Example |
|---|---|---|
| Primary taskbar, app icon slot k (1-based) | `<Note> · Taskbar <k> · <Instrument>` | `E4 · Taskbar 7 · Xylophone` |
| Taskbar on monitor m (not primary) | `<Note> · Taskbar <m>/<k> · <Instrument>` | `E4 · Taskbar 2/7 · Celesta` |
| Tray area, slot k from the right (1 = clock end) | `<Note> · Tray <k> · <Instrument>` | `C7 · Tray 1 · Xylophone` |
| Offset area before slot 1 (silent) | `Taskbar · no note here` | — |

- Monitor numbers are Windows' display numbers (1 = primary), not enumeration order, so they match Settings → Display.
- The device name is dropped inside the zone, to keep the line short. It returns when the cursor leaves.
- Instrument names come from `instruments.py`. Examples use the CG-P2 recommendation (`docs/listen-check.md`).

### 12.3 Situations

| Situation | Behaviour (from the design) | What the user sees |
|---|---|---|
| Taskbar **auto-hide** on | The zone uses the taskbar's shown rect. When hidden, the cursor at the screen edge is inside it, so it plays the slot under the cursor (and Windows slides the taskbar out) | Normal zone status. No message |
| Taskbar on **another monitor**, or taskbars on **all displays** | Each taskbar is its own zone, anchored to its own left edge, scaled to its own monitor's DPI. Slot k has the same pitch on every monitor, and a different instrument on non-primary taskbars | `Taskbar 2/7 · …` on the secondary |
| "Show my taskbar on all displays" **off** | Only the primary taskbar is a zone. The other monitors use the normal desktop mapping right to the bottom edge | Desktop status there |
| Taskbar **centered** | Still deterministic, but icons move as apps open and close, so an app won't keep its note | No message. The README and the tooltip recommend Left alignment |
| **No taskbar found** (Explorer restarting, an API error) | Zone inactive, desktop mapping everywhere. Retried every 2 s and on display or setting changes | No message (per design). The checkbox stays checked |
| Vertical taskbar (third-party tools) | Slots run top to bottom. Best effort | Same status format |

**New wording:** only the status patterns in §12.2 and the tooltip. No new W/E codes. An invalid `taskbar_*` value uses the existing W3.

### 12.4 Checklist for Sprite (UI part of CG-S1–S3)

- [ ] `strings.py`: `LABEL_TASKBAR = "Taskbar notes"`, `TASKBAR_TOOLTIP`, `STATUS_TASKBAR = "{note} · Taskbar {slot} · {instrument}"`, `STATUS_TASKBAR_MON = "{note} · Taskbar {monitor}/{slot} · {instrument}"`, `STATUS_TRAY = "{note} · Tray {slot} · {instrument}"`, `STATUS_TASKBAR_SILENT = "Taskbar · no note here"`.
- [ ] `window.py`: put the checkbutton in the row 7 frame, right of Hold notes, with 16 px between them, and bind it to `controller.set_taskbar_mode`. Tooltip as in §12.1. Tab order as in §12.1.
- [ ] `config.py`: `taskbar_mode: bool = False` (and the file-only keys per design §4.1). Round-trip test.
- [ ] `status.py`: the zone status patterns, slot numbers 1-based, monitor number = Windows display number.
- [ ] No message for a missing taskbar. Log at debug only.
- [ ] Manual: check the window still fits at its minimum width at 100/150/200 % with both checkboxes on row 7. If the label clips, shorten the gap before wrapping (see Q-T1).

### 12.5 Open questions (taskbar notes)

- **Q-T1 Width.** `[ ] Hold notes (legato)   [ ] Taskbar notes` is ~300 logical px of text at Segoe UI 9. That fits in
  340 at 100 %, but it's tight in some locales and fonts. Fallback: label `Hold notes` (drop "(legato)", keep it in a
  tooltip). Sprite to measure.
- **Q-T2 "Not found" feedback.** The design says no user message when no taskbar is found. Users who check the box and
  hear nothing new may be confused. Option: add `(no taskbar found)` to the tooltip while the zone is inactive.
  Recommend yes (it's tooltip-only, not a status message). Archimedes?
- **Q-T3 Instruments.** CG-P2 recommends `taskbar_program` 13 Xylophone and `taskbar_secondary_program` 8 Celesta
  instead of 12/13 (see `docs/listen-check.md`). Needs Archimedes' sign-off and a human listen on Windows.
