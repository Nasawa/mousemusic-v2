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
| `taskbar_monitors` | enum `primary` \| `all` | `primary` | file-only | Which taskbars count (see Q1) |
| `cell_width_dip` | int 0 or 16–400 | `0` (= current behaviour) | file-only, **phase 2** | A: fixed desktop column width, with B wrapping |

Invalid values → that key's default + W3. No `schema` bump (older builds ignore unknown keys).

### 4.2 Taskbar geometry (`platform/win_taskbar.py`, new)

- **Primary taskbar:** `SHAppBarMessage(ABM_GETTASKBARPOS)` returns `rc` and `uEdge` (bottom/top/left/right). With
  per-monitor-v2 awareness these are physical virtual-desktop px, the same space as `GetCursorPos`.
- **Secondary taskbars** (`taskbar_monitors: all`): enumerate top-level windows with class `Shell_SecondaryTrayWnd` and
  `GetWindowRect`. The edge is inferred from the rect against `MonitorFromRect` → `GetMonitorInfo` (`rcMonitor`).
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

1. Each tick: if `taskbar_mode` is on and the cursor is inside a zone rect → **zone cell** `("tb", slot)`. Otherwise the
   normal `(col, row)` cell. Cell identity includes the zone, so moving between them always counts as a cell change.
2. `slot = floor((pos - start) / slot_px)`. If `pos < start` (inside the offset) → slot `-1` = a silent cell (no note, but
   it's still a cell so the hysteresis and rate-limit state stays consistent).
3. Note = `scale_notes_from(taskbar_low_note)[slot]`. If it's past `taskbar_high_note`, wrap modulo the
   in-range notes and use velocity × 0.7.
4. **Hysteresis:** the same 2 physical px rule, applied along the zone's axis. **Rate limit:** unchanged (30 ms, latest
   wins). At 48 px slots a fast sweep (~3000 px/s) crosses a slot every ~16 ms, so the limit drops intermediates as
   designed. Slow hovering, the actual use, is never limited.
5. **Instrument:** entering the zone sends a program change to `taskbar_program` before the note-on. Leaving restores
   the row's program before the next note (the same rule as a row change, §5). Instrument rows (Y) are ignored inside the
   zone.
6. Status line inside the zone: `E4 · Taskbar 7 · Marimba` (slot numbers 1-based for humans).

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
  - invalid keys → default + W3
  - `taskbar_mode: false` → mapping identical to today, as a property test across random points
- **Engine (fake clock and cursor):** a slow sweep along a 20-slot bar gives 20 distinct ascending notes. A fast
  sweep respects the rate limit. Hover jitter of ±1 px at a slot edge gives no retrigger.
- **Windows (A-win):** `win_taskbar` returns a rect that contains the Start button's rect, and the edge is bottom on the
  default setup. The geometry refreshes after a taskbar setting change.
- **Manual (Grace):** see the task list below.

## 5. Task split

### Sprite (dev and CI)
- **CG-S1** Pure zone mapping in `mapping.py` plus the settings keys and validation in `config.py`.
  *AC:* the tests above pass. With `taskbar_mode: false`, mapping output is byte-identical to today's (property test).
  Coverage ≥ 90 %.
- **CG-S2** `platform/win_taskbar.py` (ABM_GETTASKBARPOS, Shell_SecondaryTrayWnd, GetDpiForMonitor) and the refresh hooks.
  *AC:* the A-win test passes on CI. An Explorer restart doesn't crash and just deactivates the zone until the next refresh.
- **CG-S3** Engine and scheduler integration: zone cells, program change on enter/leave, wrap velocity, status text.
  *AC:* engine tests pass, and LT-01 still shows ≤ 1 tick of added latency.
- **CG-S4 (phase 2, separate PR)** `cell_width_dip` desktop mode, with B wrapping.

### Pragma (UX and README)
- **CG-P1** `docs/ux.md`: the row 7 checkbox, tooltip and status format. README section "Hearing your taskbar":
  setting the alignment to Left, the file-only keys, and how to tune `taskbar_offset_dip`/`taskbar_slot_dip` for
  scaling or icon size.
  *AC:* a user can enable the mode and tune it from the README alone.
- **CG-P2** Listen-check `taskbar_program` against all three instrument sets. Marimba vs. Classic's Marimba row may
  collide, so propose an alternative if needed (e.g. 13 Xylophone or 108 Kalimba).
  *AC:* a short note in `docs/curation.md`.

### Grace (QA)
- **CG-G1** Test-plan section TB-xx covering:
  - 2 monitors, taskbar on the primary, left alignment, 100/150 % scaling: each pinned icon gives a distinct note, and
    the same icon gives the same note after a restart
  - centered alignment: deterministic, no errors
  - auto-hide
  - taskbar moved to the other monitor (`taskbar_monitors`)
  - Explorer restart
  - small-icons registry tweak (shows the need for `taskbar_slot_dip`)
  *AC:* results recorded in the RC checklist.
- **CG-G2** Measure the actual Windows 11 icon pitch at 100/125/150/200 % on 23H2 and 24H2 with a screenshot ruler.
  *AC:* numbers posted on #16. The `taskbar_slot_dip` default is confirmed or corrected before CG-S1 merges.

## 6. Open questions

- **Q1** Christopher's two monitors: is the taskbar he wants to hear on the primary display only, or also on the
  secondary (Windows 11 shows taskbars on all displays by default)? The default is `primary`; `all` is implemented either way.
- **Q2** Should the zone also cover the system tray (right side of the taskbar)? Proposal: yes, it's just more slots, with
  no special handling.
- **Q3** Is the 48 DIP default right for his icon size and Windows build? CG-G2 measures it.
