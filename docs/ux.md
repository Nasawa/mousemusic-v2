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
- Size: **340 × 300** logical px at 100% scaling, fixed (not resizable). It's within the ≤ 360×300 budget in §10 P1.
  Tk handles DPI scaling. Don't hard-code physical px.
- Position: centred on the primary monitor on first run, then last position remembered (see Open questions Q1).
- Icon: `assets/icon.ico` (P2).
- Layout: ttk `grid`, two columns (label right-aligned, control left-aligned), 8 px padding, 4 px row gap.

### 1.1 Wireframe

```
┌ MouseMusic ───────────────────────────── _ □ ✕ ┐
│                                                 │
│  [ ▶  Start ]                Ctrl+Alt+M         │   row 0  Start/Stop button + hotkey hint
│ ─────────────────────────────────────────────── │
│        Scale  [ Pentatonic major       ▾ ]      │   row 1
│          Key  [ C  ▾ ]                          │   row 2
│  Pitch range  [ C2 ▾ ]  to  [ C7 ▾ ]            │   row 3
│  Instruments  [ Classic (8)            ▾ ]      │   row 4
│       Volume  [━━━━━━━━━━━●━━━━]  90            │   row 5
│  Note length  [━━━━●━━━━━━━━━━━]  250 ms        │   row 6
│               [ ] Hold notes (legato)           │   row 7
│  MIDI output  [ Microsoft GS Wavetable ▾ ] [⟳]  │   row 8  device + Reconnect
│ ─────────────────────────────────────────────── │
│  ● Stopped — press Start or Ctrl+Alt+M          │   row 9  status line
└─────────────────────────────────────────────────┘
```

Tab order is top to bottom, left to right: Start → Scale → Key → Low → High → Instruments → Volume → Note length →
Hold notes → MIDI output → Reconnect. Start has focus when the window opens.

### 1.2 Controls

| # | Label (exact) | Widget | Values / range | Default | Setting key | Behaviour |
|---|---|---|---|---|---|---|
| 0 | `▶  Start` / `■  Stop` | ttk.Button, default button (Enter / Space) | toggle | `▶  Start` | — (not persisted; `start_on_launch` is file-only) | Posts `start`/`stop` to the engine. The label flips **only after** the engine confirms (so if the open fails, it stays `▶  Start`). Hint text `Ctrl+Alt+M` in grey to the right (shows the current `hotkey` value) |
| 1 | `Scale` | readonly Combobox | `Chromatic`, `Major`, `Minor`, `Pentatonic major`, `Pentatonic minor`, `Blues` | `Pentatonic major` | `scale` | Applies live while playing |
| 2 | `Key` | readonly Combobox, narrow | `C`, `C♯`, `D`, `E♭`, `E`, `F`, `F♯`, `G`, `A♭`, `A`, `B♭`, `B` | `C` | `root` | Applies live. Disabled (greyed) when Scale = Chromatic, since key has no effect there |
| 3 | `Pitch range` | two readonly Comboboxes + the word `to` | octaves `C0`…`C8` (MIDI 12…108), step 12 | `C2` to `C7` (36–96) | `low_note`, `high_note` | If the user picks low ≥ high, the other box moves so the range is at least one octave (no error). Only octave Cs are offered in the UI. A non-C value from the file shows its note name, e.g. `G2`, as an extra item |
| 4 | `Instruments` | readonly Combobox | `Classic (8)`, `Mellow (7)`, `Percussive (7)`, `Piano only (1)`, `All 128 GM (128)` | `Classic (8)` | `instrument_set` | The number is the row count, i.e. how many bands the screen is split into top to bottom. Tooltip on hover: `Top of the screen to bottom: <names>` |
| 5 | `Volume` | ttk.Scale + value label | 1–127 | 90 | `velocity` | Value label shows the raw number. Live |
| 6 | `Note length` | ttk.Scale + value label | 50–2000 ms, step 10 | 250 ms | `note_length_ms` | Label `250 ms`. **Disabled** when Hold notes is checked |
| 7 | `Hold notes (legato)` | ttk.Checkbutton | on/off | off | `legato` | When on, a note holds until the cursor enters the next cell or until Stop |
| 8 | `MIDI output` | readonly Combobox, ellipsized at ~24 chars, full name in tooltip | WinMM device names | `Microsoft GS Wavetable Synth` | `midi_device` | **Re-enumerates every time the dropdown opens** (§9). Choosing a device while playing silences, closes and reopens (engine `set_device`). If the list is empty the combobox shows `No MIDI output found` and is disabled |
| 8b | `⟳` (tooltip `Reconnect`) | small ttk.Button | — | — | — | Closes and reopens the selected device. Use it after unplugging headphones etc. Status: `Reconnecting…` then the normal status |
| 9 | status line | ttk.Label, single line, ellipsized | see §1.3 | — | — | Coloured dot + text. Errors stay until resolved. They are never auto-dismissed |

All settings save automatically (debounced 500 ms, per §4). There is **no Save, Apply, or OK button.**

Not in the UI by design (file-only, per §4/§5): `poll_hz`, `screen_mode`, `start_on_launch`, `hotkey`, hysteresis.

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
- Icon: `assets/icon.ico`. Two variants (P2 delivers both): **idle** (normal) and **playing** (with a small green dot
  or note badge), so state shows at a glance. Until P2 lands, Sprite uses one icon.
- Tooltip (hover), exact:
  - Stopped: `MouseMusic vX.Y.Z — Stopped`
  - Playing: `MouseMusic vX.Y.Z — Playing`
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

No checked states in v0.1. The architecture limits the menu to these three items. See Q3 for optional extras.

### 2.3 Notifications (tray balloons)
Used only for these cases (they are seen when the window is hidden):

| When | Title | Body |
|---|---|---|
| First close-to-tray | `MouseMusic is still running` | `It's in the system tray. Right-click the icon to quit.` (If playing: `It's still playing in the system tray. Press Ctrl+Alt+M to stop, or right-click the icon to quit.`) |
| Device lost while window hidden | `MouseMusic stopped` | `Lost connection to <device>. Click to open MouseMusic.` |
| Hotkey couldn't register (startup) | — | Not a balloon: status-line warning only (§4) |

Set a flag after the first-close balloon. See Q2 about where it's stored.

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
8. First ✕ → hide to tray + first-close balloon (§2.3).

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
| **W1** | Saved `midi_device` not found at startup or after re-enumeration. Falls back to device 0 (§9) | `"<saved device>" not found. Using <device 0> instead.` | Auto-selected. Clears on the next Start or on the user picking any device. The saved setting changes only if the user picks a device or plays with the fallback (see Q4) |
| **W2** | Settings file corrupt → renamed `settings.json.bak`, defaults loaded (§4) | `Your settings file couldn't be read, so defaults were restored. The old file was saved as settings.json.bak.` | Shown at startup until the first Start or 15 s, whichever is later. Help → `#settings-reset` |
| **W3** | Some settings values invalid → clamped or reset (§4) | `Some settings were out of range and have been reset.` | Same dismissal as W2. Details go in the log |
| **W4** | Global hotkey taken: `RegisterHotKey` fails (another app owns Ctrl+Alt+M) or the `hotkey` string won't parse | `Ctrl+Alt+M is in use by another app, so the shortcut is off. Use the Start button.` | The hint next to Start changes to `(shortcut off)` in grey. App works normally otherwise. Clears after 15 s. The hint stays |
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

---

## 5. Keyboard

| Key | Scope | Action |
|---|---|---|
| `Ctrl+Alt+M` | **Global** (`RegisterHotKey`) | Toggle Start/Stop, even when the window is hidden |
| `Space` / `Enter` | Window, Start focused | Toggle |
| `Tab` / `Shift+Tab` | Window | Move focus (order in §1.1) |
| `Alt+↓` or `F4` | Combobox | Open the list (standard ttk) |
| `←` `→` | Slider | Step (Volume ±1, Note length ±10 ms). `PgUp`/`PgDn` ±10 / ±100 |
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
- Numbers come with their units: `250 ms`. Volume is unitless.
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
- [ ] Window matches §1.1 order and §1.2 labels exactly, ≤ 360×300 at 100%.
- [ ] Every control applies live and persists across restarts.
- [ ] Start label flips only on engine confirmation. Failures show E-copy.
- [ ] Tray menu has exactly `Start/Stop`, `Show window` (default), separator, `Quit`. The tooltip matches §2.1.
- [ ] First run shows the hint, and `first_run_done` is set on the first successful Start.
- [ ] E1–E5 and W1–W5 are reachable (with `--dry-run`/fake backend errors) and show the exact copy.

## 9. Out of scope (later tasks)
Icon art and theming (P2), instrument set names/contents after listen test (P3), README anchors and SmartScreen steps (P4).

---

## 10. Open questions

- **Q1 Window position persistence.** Remembering the last position needs a new settings key (e.g. `window_x`,
  `window_y`) that isn't in §4. Proposal: add it as optional keys, ignored if off-screen. Archimedes to confirm, or we
  always centre.
- **Q2 First-close balloon flag.** Needs a key such as `tray_hint_shown` (not in §4). Alternative: reuse
  `first_run_done` (but that's set on first Start, so the semantics differ). Proposal: add `tray_hint_shown: false`.
- **Q3 Tray extras.** The architecture fixes the tray at Start/Stop, Show window, Quit. Should we add checked items like
  `Hold notes` or an `Instruments ▸` submenu? Recommend **no** for v0.1, to keep it simple.
- **Q4 Fallback device persistence (W1).** If the saved device is missing, should the fallback overwrite
  `midi_device`? Proposal: don't overwrite until the user picks one explicitly, so a temporarily unplugged synth comes back
  on the next launch.
- **Q5 Volume scale.** Volume maps to note-on `velocity` (1–127), not channel volume (CC7). The GS synth's velocity curve
  is soft at the low end. Should Volume be 0–100% mapped to velocity, or would CC7 be better? Using CC7 would add a
  message type, which is still a short message so the spec allows it. Defaulting to velocity per §4.
- **Q6 Pitch-range granularity.** The UI offers octave Cs only (C0–C8). Is that enough, or do power users need
  semitone ranges? (They can still edit the JSON.)
- **Q7 Help link target.** Help links need a stable README URL. Use `https://github.com/Nasawa/mousemusic-v2#no-sound`
  etc. P4 must keep these anchors.
- **Q8 Mid-play device-loss detection (E4).** This depends on `midiOutShortMsg` returning errors. The GS synth may
  fail silently on endpoint change (W6). G4 should confirm what's detectable.
