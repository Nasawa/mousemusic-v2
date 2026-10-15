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
- Theme setting (B-1): `theme` is read case-insensitively (stripped and lowercased, so `" Dark "` → `dark`). Any
  other value → `system` + W3.
- Position: saved in `window_x`/`window_y` (logical px, `null` = centre on primary). On load, if the saved point isn't on any monitor's work area, centre the window and don't overwrite the saved values until the user moves it (§11 UX-Q1).
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
│       Volume  [━━━━━━━━━━━━●━━━]  80 %          │   row 5
│  Note length  [━━━━●━━━━━━━━━━━]  250 ms        │   row 6
│     [ ] Hold notes (legato)  [ ] Taskbar notes  │   row 7  two checkboxes (§12)
│  MIDI output  [ Microsoft GS Wavetable ▾ ] [⟳]  │   row 8  device + Reconnect
│     Shortcut  [ Ctrl+Alt+M         ▾ ]          │   row 8c global shortcut
│ ─────────────────────────────────────────────── │
│  ● Stopped — press Start or Ctrl+Alt+M          │   row 9  status line (wraps)
└─────────────────────────────────────────────────┘
```

Tab order is top to bottom, left to right: Start → Scale → Key → Low → High → Instruments → Volume → Note length →
Hold notes → Taskbar notes → MIDI output → Reconnect → Shortcut. Start has focus when the window opens.

### 1.2 Controls

| # | Label (exact) | Widget | Values / range | Default | Setting key | Behaviour |
|---|---|---|---|---|---|---|
| 0 | `▶  Start` / `■  Stop` | ttk.Button, default button (Enter / Space) | toggle | `▶  Start` | — (not persisted; `start_on_launch` is file-only) | Posts `start`/`stop` to the engine. The label flips **only after** the engine confirms (so if the open fails, it stays `▶  Start`). Hint text `Ctrl+Alt+M` in grey to the right (shows the shortcut that is **actually active**, which may be the fallback `Ctrl+Alt+Shift+M`; `(shortcut off)` when none) |
| 1 | `Scale` | readonly Combobox | `Chromatic`, `Major`, `Minor`, `Pentatonic major`, `Pentatonic minor`, `Blues` | `Pentatonic major` | `scale` | Applies live while playing |
| 2 | `Key` | readonly Combobox, narrow | `C`, `C♯`, `D`, `E♭`, `E`, `F`, `F♯`, `G`, `A♭`, `A`, `B♭`, `B` | `C` | `root` | Applies live. Disabled (greyed) when Scale = Chromatic, since key has no effect there |
| 3 | `Pitch range` | two readonly Comboboxes + the word `to` | octaves `C0`…`C8` (MIDI 12…108), step 12 | `C2` to `C7` (36–96) | `low_note`, `high_note` | If the user picks low ≥ high, the other box moves so the range is at least one octave (no error). Only octave Cs are offered in the UI. A non-C value from the file shows its note name, e.g. `G2`, as an extra item |
| 4 | `Instruments` | readonly Combobox | `Classic (8)`, `Mellow (6)`, `Percussive (7)`, `Piano only (1)`, `Full GM library (128)` | `Classic (8)` | `instrument_set` | The number is the row count, i.e. how many bands the screen is split into top to bottom. Tooltip on hover: `Top of the screen to bottom: <names>` |
| 5 | `Volume` | ttk.Scale + value label | 0–100 %, step 1 | 80 % | `volume` | Label `80 %`. Sent as CC7 Channel Volume (`round(volume*127/100)`) on open, on Start and on every change. Live. `velocity` (default 100) is file-only |
| 6 | `Note length` | ttk.Scale + value label | 50–2000 ms, step 10 | 250 ms | `note_length_ms` | Label `250 ms`. **Disabled** when Hold notes is checked |
| 7 | `Hold notes (legato)` | ttk.Checkbutton | on/off | off | `legato` | When on, a note holds until the cursor enters the next cell or until Stop |
| 7b | `Taskbar notes` | ttk.Checkbutton, same row as 7 | on/off | off | `taskbar_mode` | Each taskbar icon gets its own note. Applies live. See §12 |
| 8 | `MIDI output` | readonly Combobox, ellipsized at ~24 chars, full name in tooltip | WinMM device names | `Microsoft GS Wavetable Synth` | `midi_device` | **Re-enumerates every time the dropdown opens** (§9). Choosing a device while playing silences, closes and reopens (engine `set_device`). If the list is empty the combobox shows `No MIDI output found` and is disabled |
| 8b | `⟳` (tooltip `Reconnect`) | small ttk.Button | — | — | — | Closes and reopens the selected device. Use it after unplugging headphones etc. Status: `Reconnecting…` then the normal status |
| 8c | `Shortcut` | readonly Combobox | `Ctrl+Alt+M`, `Ctrl+Alt+Shift+M`, `Ctrl+Alt+P`, `Ctrl+Alt+F9`, `Off` (a custom value from the file is listed first) | `Ctrl+Alt+M` | `hotkey` | Re-registers live on change. If the chosen key is taken, `Ctrl+Alt+Shift+M` is tried as a fallback (W7); if both fail, W4 |
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

Tray icon per state (P2, `assets/icons/`): Stopped → `tray-idle.ico`, Playing → `tray-playing.ico`, Error → `tray-error.ico`. Warnings keep the idle or playing icon.

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
