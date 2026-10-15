# Design: configurable cell granularity (issue #16)

Status: **Proposed** · Owner: Archimedes · Target: after rc2 (v0.2)

## 1. Problem and interpretation

Christopher wants to tell **taskbar icons apart by sound** across two monitors. Today the columns are the notes of the
selected scale and range, spread across the whole virtual desktop (§5). Real numbers, two 1920 px monitors side by
side (3840 px wide, 100 % scaling):

| Scale, range | Notes (columns) | Cell width | Icons per cell (48 px pitch) |
|---|---|---|---|
| Pentatonic major C2–C7 (default) | 26 | ~148 px | ~3 |
| Pentatonic major C0–C8 | 41 | ~94 px | ~2 |
| Chromatic C0–C8 | 97 | ~40 px | <1, but cells don't line up with icons, and the extreme octaves are inaudible or harsh on GS |
| Same at 150 % (icon pitch ~72 px physical) | | | still 1–2 icons per cell, misaligned |

So the range slider can't fix this. The cells have to follow the **icon pitch** and the **taskbar position**, not the
note count.

**Interpretation of "left-aligned taskbar":** Windows 11 can't dock the taskbar to the left side natively (top/left/right
docking was removed). So this design targets the **bottom (or top) taskbar with icons left-aligned**
(Settings → Personalization → Taskbar → Taskbar behaviours → Alignment: Left). Icons then sit at fixed offsets from the
taskbar's left edge, so a per-icon mapping is stable as long as the pinned order doesn't change. With **centered**
alignment the icons shift when apps open or close. The design still works (the mapping is tied to position, so it's
deterministic), but a given app won't keep a fixed note. That's documented, not detected, and harmless. Vertical
taskbars (third-party tools, Windows 10) are handled by the same code along the Y axis (§4.2), but they're best-effort.

Icon pitch: ~48 px per taskbar button at 100 % (button ~44 px plus spacing; the Windows 11 default "small/regular" size).
It scales with the **taskbar monitor's** DPI: 60 px at 125 %, 72 px at 150 %, 96 px at 200 %. On a 1920 px monitor
that's ~40 slots at 100 %, and Christopher's pinned set is probably 8–20.

## 2. Options considered

| Option | How | Pros | Cons | Verdict |
|---|---|---|---|---|
| **A. Cell width independent of the range** (`cell_width_dip`) | Columns are N DIP wide across the desktop. The note for a column walks the scale from `low_note` | Simple, general, helps everywhere | 3840 px / 48 = 80 columns. Pentatonic from C2 runs past C8 → needs B. Cells still don't line up with taskbar buttons unless the grid origin = taskbar left edge. The whole desktop becomes a busy, fine-grained sound field, which hurts the "learn the screen" goal | Useful as a general option, **phase 2** |
| **B. Cycling octaves** | When the column's note would pass `high_note`, wrap to `low_note` | Unlimited columns in a pleasant range | Ambiguous: the same note recurs, so absolute position can't be told by pitch alone (this is v1's `x % 128` problem again) unless something else (instrument or velocity) marks the cycle | Only as a **fallback** for A/C overflow, with the cycle marked by velocity |
| **C. Pitch bend** | Fine X position → bend within a note | Continuous, no new notes | GS bend range is ±2 semitones by default (RPN 0 changes are unreliable on GS). Bend is hard to hear as "position" and isn't discrete per icon, so it doesn't answer "which icon?". Also smears with the note-length and rate-limit model | **Rejected** |
| **D. Taskbar zone with its own mapping** | When the cursor is inside the taskbar rect, a separate grid applies: 1 column = 1 icon slot, aligned to the taskbar's left edge, with its own instrument. The rest of the desktop is unchanged | Exactly the use case. Cells line up with icons. Small, learnable set (~20 notes fit in 4 pentatonic octaves). The desktop mapping is untouched, so it doesn't break existing learning. A distinct instrument signals "you're on the taskbar" | Needs the taskbar rect, monitor and DPI. Only the taskbar benefits | **Recommended** |

## 3. Recommendation

**D (taskbar zone), with B as its overflow rule. A is phase 2 behind a file-only key, default off.**

- On the taskbar, each icon slot (~48 DIP × monitor scale) is one column. The column's note steps up the selected scale
  from `taskbar_low_note`, and the zone uses its own single instrument (`taskbar_program`, default Marimba 12: short,
  woody, distinct from the Classic rows). So every icon has a stable, distinct note with a clear "taskbar" timbre.
- The rest of the desktop keeps today's mapping exactly, so nothing users have learned changes.
- Defaults: 20 slots of pentatonic major from C3 = C3…C7, comfortably inside GS's good range. Wrapping (B) only starts
  past slot 25, and wrapped notes are marked with a lower velocity.

## 4. Specification

### 4.1 Settings keys (§4 additions, all validated per §11 OQ-8/A-4 rules)

| Key | Type / range | Default | UI | Meaning |
|---|---|---|---|---|
| `taskbar_mode` | bool | `false` | **Yes** (checkbox) | Turns on the taskbar zone |
| `taskbar_slot_dip` | int 24–128 | `48` | file-only | Icon pitch in DIP (96-DPI px). Physical width = `round(slot_dip × monitor_dpi / 96)` |
| `taskbar_offset_dip` | int 0–400 | `0` | file-only | Distance from the taskbar's left (or top) edge to the first slot. Covers a Start or widgets button the user wants to skip |
| `taskbar_low_note` | int 0–127 | `48` (C3) | file-only | Note of slot 0. Later slots step up the **current scale and key** |
| `taskbar_high_note` | int 0–127, ≥ low + 12 (OQ-8 rule) | `96` (C7) | file-only | Past this, wrap to `taskbar_low_note` (B) and play at `velocity × 0.7` so the wrap is audible |
| `taskbar_program` | int 0–127, not a drum kit | `12` (Marimba) | file-only | Instrument for the whole zone. Y is ignored inside the zone |
| `taskbar_monitors` | enum `primary` \| `all` | `all` | file-only | Which taskbars count. `all` is fully supported in phase 1 (Q1) |
| `taskbar_secondary_program` | int 0–127, not a drum kit | `13` (Xylophone) | file-only | Instrument for **non-primary** taskbars, so the same slot on two monitors sounds different (Q1) |
| `taskbar_tray` | bool | `true` | file-only | Notification area (tray icons and clock) is part of the zone, with its own right-anchored slots (Q2) |
| `taskbar_tray_slot_dip` | int 16–96 | `32` (provisional, set by CG-G2) | file-only | Tray icon pitch in DIP |
| `cell_width_dip` | int 0 or 16–400 | `0` (= current behaviour) | file-only, **phase 2** | A: fixed desktop column width, with B wrapping |

Invalid values → that key's default + W3. No `schema` bump (older builds ignore unknown keys).

### 4.2 Taskbar geometry (`platform/win_taskbar.py`, new)

- **Primary taskbar:** `SHAppBarMessage(ABM_GETTASKBARPOS)` returns `rc` and `uEdge` (bottom/top/left/right). With
  per-monitor-v2 awareness these are physical virtual-desktop px, the same space as `GetCursorPos`.
- **Secondary taskbars** (`taskbar_monitors: all`, the default): `ABM_GETTASKBARPOS` only reports the **primary**
  taskbar (`Shell_TrayWnd`). Secondary taskbars are found with `EnumWindows`, keeping visible top-level windows whose
  class is `Shell_SecondaryTrayWnd` (one per extra monitor when "Show my taskbar on all displays" is on), and reading
  `GetWindowRect`. The edge is inferred by comparing the rect with that monitor's `rcMonitor`
  (`MonitorFromRect` → `GetMonitorInfo`): it touches the bottom, top, left or right. Each taskbar is a separate zone
  with **its own anchor** (its own left or top edge + `taskbar_offset_dip`) and **its own monitor's DPI scale**, so a
  100 % primary and a 150 % secondary each line up with their own icons. If "Show my taskbar on all displays" is off,
  there are no secondary windows and only the primary zone exists.
- **Tray rect:** on the primary taskbar, `FindWindowEx(Shell_TrayWnd, "TrayNotifyWnd")` → `GetWindowRect` (covers the
  overflow chevron, the notification icons and the clock). On a secondary taskbar, the clock area child
  (`ClockButton`, or failing that the right-most `ToolbarWindow32`/`TrayNotifyWnd` if present) is used when found;
  otherwise the secondary taskbar has no tray part. A missing tray rect just means the app slots cover the whole bar.
- **Scale:** `GetDpiForMonitor(MonitorFromRect(rc), MDT_EFFECTIVE_DPI)` / 96. Slot width (physical) =
  `round(taskbar_slot_dip × scale)`.
- **Axis:** bottom/top → slots run along X from `rc.left + offset`. Left/right (non-native) → along Y from `rc.top + offset`.
- **Auto-hide:** the reported rect is the shown position. The zone is active only while the cursor is inside it, so a
  hidden taskbar at the screen edge just gives the slot under the cursor, which is fine.
- **Refresh:** on start, on `WM_DISPLAYCHANGE`, on `WM_SETTINGCHANGE` (taskbar moves and DPI changes broadcast it, and
  the message window already handles it per #22), and every 2 s with the existing metrics refresh. Taskbar geometry is
  read on the engine thread and is pure data afterwards.
- **Failure** (no taskbar, an Explorer restart, an API error): the zone is inactive and the desktop mapping applies. Log
  at debug. No user message.
- **Pure core:** `mapping.TaskbarZone(rect, axis, slot_px, offset_px)` plus `taskbar_cell(x, y, zone, grid)` contain
  no Win32 calls, so they're testable on Linux.

### 4.3 Mapping integration (§5)

1. Each tick: if `taskbar_mode` is on and the cursor is inside a zone rect → **zone cell** `("tb", monitor_index, part, slot)`,
   where `part` is `apps` or `tray`. Otherwise the
   normal `(col, row)` cell. Cell identity includes the zone, so moving between them always counts as a cell change.
2. `slot = floor((pos - start) / slot_px)`. If `pos < start` (inside the offset) → slot `-1` = a silent cell (no note, but
   it's still a cell so the hysteresis and rate-limit state stays consistent).
3. **Apps part:** note = `scale_notes_from(taskbar_low_note)[slot]`. **Every taskbar starts at `taskbar_low_note`**,
   so slot k has the same pitch on every monitor and the monitors are told apart by **instrument**: the primary uses
   `taskbar_program`, others use `taskbar_secondary_program`. (Continuing the numbering across monitors was rejected:
   it would depend on monitor order and on how many icons the first bar has, which breaks stability.) If a note is
   past `taskbar_high_note`, wrap modulo the in-range notes and use velocity × 0.7.
3a. **Tray part (Q2): anchored from the tray's right edge**, not continuing the app sequence. Tray slot 0 is the
   right-most slot (the clock/notification end), `slot = floor((tray.right - pos) / tray_slot_px)`, and notes
   **descend** the scale from `taskbar_high_note`. Why: tray icons are right-aligned, and both the number of pinned or
   open apps and centered alignment move the app sequence. Continuing it would make every tray note shift whenever an
   app opens. Right-anchoring keeps the clock and the right-most tray icons fixed, and descending from the top keeps
   them far in pitch from the app icons on the left (low notes). If the app and tray sequences would meet, the tray rect
   wins (it's checked first).
4. **Hysteresis:** the same 2 physical px rule, applied along the zone's axis. **Rate limit:** unchanged (30 ms, latest
   wins). At 48 px slots a fast sweep (~3000 px/s) crosses a slot every ~16 ms, so the limit drops intermediates as
   designed. Slow hovering, the actual use, is never limited.
5. **Instrument:** entering a zone sends a program change to that zone's program (primary → `taskbar_program`,
   others → `taskbar_secondary_program`; the tray uses its taskbar's program) before the note-on. Leaving restores
   the row's program before the next note (the same rule as a row change, §5). Instrument rows (Y) are ignored inside the
   zone.
6. Status line inside the zone: `E4 · Taskbar 7 · Marimba`, `E4 · Taskbar 2/7 · Xylophone` on a secondary, and
   `C7 · Tray 1 · Marimba` (slot numbers 1-based for humans; `2/` = monitor 2).

**Centered alignment:** nothing changes in the code. Slots stay at fixed positions from the taskbar's left edge, so
the mapping is still deterministic. Only the icon → app association moves. Documented in the README, not detected.

### 4.4 UI impact

One control, and **no extra row**. Row 7 becomes `[ ] Hold notes (legato)   [ ] Taskbar notes`, so the window stays at
the 340 × 360 minimum. Tooltip: `Each taskbar icon gets its own note. Works best with taskbar icons aligned left.`
Everything else is file-only (README documents the keys). Tray menu: unchanged.

### 4.5 Tests

- **Pure (CI):**
  - Slot index at 100/125/150/200 % (48/60/72/96 px)
  - offset region → silent
  - exact boundaries
  - wrap with velocity scaling
  - zone/desktop transitions count as cell changes
  - program change on enter/leave is ordered before note-on
  - top, left and right edges
  - zone on a negative-X secondary monitor
  - two taskbars at different DPI (100 % + 150 %): each anchored to its own edge with its own slot width; slot k has the
    same pitch on both and a different program
  - tray: right-anchored slots descending from `taskbar_high_note`; app-slot count changes don't move tray notes; the
    tray rect wins where it overlaps app slots; a missing tray rect → app slots cover the whole bar
  - invalid keys → default + W3
  - `taskbar_mode: false` → mapping identical to today, as a property test across random points
- **Engine (fake clock and cursor):** a slow sweep along a 20-slot bar gives 20 distinct ascending notes. A fast
  sweep respects the rate limit. Hover jitter of ±1 px at a slot edge gives no retrigger.
- **Windows (A-win):** `win_taskbar` returns a rect that contains the Start button's rect, and the edge is bottom on the
  default setup. It finds a `Shell_SecondaryTrayWnd` per extra monitor when one exists (skipped on a single-monitor
  runner) and a `TrayNotifyWnd` rect inside the primary bar. The geometry refreshes after a taskbar setting change.
- **Manual (Grace):** see the task list below.

## 5. Task split

### Sprite (dev and CI)
**Gate:** CG-G2 (measured icon and tray pitches) must be posted on #16 before CG-S1 merges. The `taskbar_slot_dip`
and `taskbar_tray_slot_dip` defaults come from it.

- **CG-S1** Pure zone mapping (including multiple zones, the tray part and secondary programs) in `mapping.py` plus the settings keys and validation in `config.py`.
  *AC:* the tests above pass. With `taskbar_mode: false`, mapping output is byte-identical to today's (property test).
  Coverage ≥ 90 %.
- **CG-S2** `platform/win_taskbar.py` (ABM_GETTASKBARPOS for the primary, EnumWindows for `Shell_SecondaryTrayWnd`,
  TrayNotifyWnd/clock rects, GetDpiForMonitor per taskbar) and the refresh hooks.
  *AC:* the A-win test passes on CI. An Explorer restart doesn't crash and just deactivates the zone until the next refresh.
- **CG-S3** Engine and scheduler integration: zone cells, program change on enter/leave, wrap velocity, status text.
  *AC:* engine tests pass, and LT-01 still shows ≤ 1 tick of added latency.
- **CG-S4 (phase 2, separate PR)** `cell_width_dip` desktop mode, with B wrapping.

### Pragma (UX and README)
- **CG-P1** `docs/ux.md`: the row 7 checkbox, tooltip and status format. README section "Hearing your taskbar":
  setting the alignment to Left, the file-only keys, and how to tune `taskbar_offset_dip`/`taskbar_slot_dip` for
  scaling or icon size.
  *AC:* a user can enable the mode and tune it from the README alone.
- **CG-P2** Listen-check `taskbar_program` **and `taskbar_secondary_program`** (they must be clearly different from
  each other) against all three instrument sets. Marimba vs. Classic's Marimba row may
  collide, so propose an alternative if needed (e.g. 13 Xylophone or 108 Kalimba).
  *AC:* a short note in `docs/curation.md`.

### Grace (QA)
- **CG-G1** Test-plan section TB-xx covering:
  - 2 monitors, taskbars on **both**, left alignment, 100/150 % scaling (including mixed DPI): each pinned icon on
    each taskbar gives a distinct note, the two monitors are distinguishable by instrument, and the same icon gives the
    same note after a restart
  - secondary taskbar: "Show my taskbar on all displays" off → only the primary zone; turned on at runtime → the
    secondary zone appears within one refresh; secondary monitor left of the primary (negative X)
  - tray: each tray icon and the clock give a distinct note; opening and closing apps doesn't change tray notes; the
    overflow chevron; adding or removing a tray icon only shifts slots to its left
  - centered alignment: deterministic, no errors
  - auto-hide
  - taskbar moved to the other monitor (`taskbar_monitors`)
  - Explorer restart
  - small-icons registry tweak (shows the need for `taskbar_slot_dip`)
  *AC:* results recorded in the RC checklist.
- **CG-G2 (gate for CG-S1)** Measure the actual Windows 11 **taskbar icon pitch and tray icon pitch** at
  100/125/150/200 % on 23H2 and 24H2 with a screenshot ruler, on primary and secondary taskbars.
  *AC:* numbers posted on #16. `taskbar_slot_dip` and `taskbar_tray_slot_dip` defaults are confirmed or corrected.
  CG-S1 doesn't merge before this.

## 6. Resolved questions

- **Q1 → resolved:** it must work on both of Christopher's monitors (#16). `taskbar_monitors` defaults to `all` and is
  fully supported in phase 1. Each taskbar has its own anchor and DPI. Each starts at `taskbar_low_note`, and the
  monitors are told apart by instrument (`taskbar_secondary_program`).
- **Q2 → resolved:** the tray and notification area is in the zone, with its own slots anchored from the right edge and
  descending from `taskbar_high_note` (§4.3 step 3a).
- **Q3 → resolved:** CG-G2 measures the pitches, and it is a gate. CG-S1 doesn't merge before it.
