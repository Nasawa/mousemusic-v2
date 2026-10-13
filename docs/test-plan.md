# MouseMusic v2 — Test Plan (G1)

Owner: Grace (QA) · Spec: [`ARCHITECTURE.md`](../ARCHITECTURE.md) (v1 of the doc) · Target: Windows 11 x64 (23H2 / 24H2)

This plan covers the manual matrix from §8, risk-based cases for **every** risk in §9, and the release-candidate (RC)
checklist that G3 uses. Spec references are written `§n`. When the spec gives no number or behaviour, this plan
**doesn't make one up**. The gap goes under [Open questions](#10-open-questions--spec-gaps) and the case is marked **OQ-n**.

Legend: **A** = automated (pytest in CI, fake clock/`FakeMidiOut`/fake cursor), **A-win** = automated Windows-only
(`@pytest.mark.windows_audio`, run on Grace's machine), **M** = manual on a real Win11 box/VM.

---

## 1. Test environments (manual matrix, §8)

| ID | OS | Display setup | Notes |
|---|---|---|---|
| E1 | Win11 23H2 | Single 1080p @ 100% | Baseline |
| E2 | Win11 24H2 | Laptop 4K @ 150% and @ 200% | DPI awareness |
| E3 | Win11 23H2 or 24H2 | Dual monitor, secondary **left** of primary (negative X) | Virtual-desktop normalization |
| E4 | Win11 24H2 | Mixed DPI (e.g. 4K @ 150% + 1080p @ 100%) | Per-monitor-v2 awareness |
| E5 | Clean Win11 VM, no Python installed | any | Packaging, SmartScreen, Defender (§7, S7 AC) |
| E6 | Win11 N/KN edition (if obtainable) | any | GS synth absent (§9) |

Run all of these with Defender on. SmartScreen first-run gets tested on E5. Bluetooth and USB audio switching gets
tested on at least one physical box (§8).

Tools: loopMIDI (virtual port), VirtualMIDISynth (alternative synth), MIDI-OX or a DAW (message monitor), Task Manager
/ Process Explorer (CPU, memory, handles), VirusTotal, a phone camera that can record slow-motion video (for latency).

---

## 2. MIDI device (§1 MIDI library, §5 scheduler, §9 "MIDI device missing or unavailable", "Audio endpoint change", S4)

| ID | Case | Steps | Expected | Type |
|---|---|---|---|---|
| MD-01 | Device enumeration | Run `MouseMusic.exe --list-devices` | Lists "Microsoft GS Wavetable Synth" (S4 AC) | M, A-win |
| MD-02 | Zero devices (unit) | `midiOutGetNumDevs` faked to 0. Start the engine | Friendly error and no exception. App keeps running (§9) | A |
| MD-03 | Zero devices (real) | E6, or disable all MIDI-out devices. Launch the exe and press Start | Clear message with a link to README troubleshooting. App stays up. `--list-devices` shows a friendly message, not a traceback (S4 AC) | M |
| MD-04 | `--self-test` with 0 devices | Run `--self-test` on the CI runner | Exit code 0 (§7 step 5) | A (release.yml) |
| MD-05 | Device busy / exclusive | Open the target port exclusively in another app (e.g. a hardware port or a single-client driver held by a DAW). Select it in MouseMusic and press Start | `MMSYSERR_ALLOCATED` (or similar) appears in the status line and is never thrown. App stays usable and switching back to the GS synth works (§9) | M; mapping covered by A (fake returns error codes) |
| MD-06 | Saved device missing | Set `midi_device` to a name that doesn't exist and launch | Falls back to device 0, logs it, plays sound (§9) | A + M |
| MD-07 | Re-enumerate on dropdown open | With the app running, start loopMIDI and create a port, then open the dropdown | The new port appears without a restart (§9) | M |
| MD-08 | loopMIDI routing | Select the loopMIDI port and route it to MIDI-OX or a DAW. Sweep the cursor | Note-on/off and program changes arrive on channel 0 only, **never channel 9** (§5). Program change comes before note-on on a row change | M |
| MD-09 | Virtual port removed mid-session | While playing through loopMIDI, delete the port | No crash and no hang. Error in the status line. No stuck note at the receiver. **OQ-1**: the spec doesn't define how a vanished device is detected mid-session | M |
| MD-10 | USB MIDI unplugged mid-session | Play to a USB synth or interface and unplug it | Same as MD-09. On replug, Reconnect or Stop→Start recovers (§9 "Auto-reopen on Start") | M |
| MD-11 | Audio endpoint change | GS synth playing to speakers. Unplug the headphones / switch the default output / connect and disconnect Bluetooth | If it goes silent, **Reconnect** (close + reopen) restores sound. Stop→Start also reopens automatically (§9) | M (G4) |
| MD-12 | Device change while a note sounds | Turn legato on and hold a note. Pick another device in the dropdown | Old device gets note-off → CC123 → `midiOutReset` before close. New device works (§5) | A (sequence on fake) + M |
| MD-13 | Single owner of the handle | Engine test: post `set_device` from a non-engine thread | All MIDI calls run on the engine thread (§6) | A |
| MD-14 | WinMM smoke | `tests/smoke/test_winmm_smoke.py` | Opens the GS synth and sends one note. Skipped when there's no device (§8) | A-win |

## 3. DPI scaling and multiple monitors (§1 cursor, §5 step 1 and 5, §6, §9 "DPI scaling", "Multi-monitor coordinates")

| ID | Case | Steps | Expected | Type |
|---|---|---|---|---|
| DM-01 | Normalization math | Table tests: corners, centre, `x = vx + vw - 1`, out-of-range points | `u, v` lie in `[0,1)` and get clamped (§5.1) | A |
| DM-02 | Negative origin | Virtual rect `(-1920, 0, 3840, 1080)` and also negative `vy` (monitor above) | Leftmost px → col 0, rightmost → last col. Pitch rises monotonically in X (§8) | A |
| DM-03 | Determinism | Same `(x,y,rect,settings)` evaluated repeatedly or after a restart | Same cell every time (§5.4) | A |
| DM-04 | Hysteresis | Jitter ±1 px at a boundary, then cross by 2 px | No cell change under 2 px. Change at ≥ 2 physical px (§5.5) | A (engine scripted path) |
| DM-05 | Cursor exactly on a boundary | x equals a column boundary | Defined, stable cell (G2 edge case) | A |
| DM-06 | Process is DPI aware | E2 @150% and @200%: launch the exe and check Task Manager → Details → "DPI awareness" column | Shows "Per-Monitor (v2)" (§9, manifest + `SetProcessDpiAwarenessContext`) | M |
| DM-07 | Full-screen sweep at scale | E2 @150%: `--dry-run`, sweep from the left edge to the right edge | First note = lowest, last = highest. No dead zone on the right (which is what you'd see if the coordinates were logical) | M |
| DM-08 | Mixed DPI consistency | E4: sweep across both monitors | Notes increase monotonically across the whole virtual desktop. Same position gives the same note on every run | M |
| DM-09 | Secondary on the left | E3: cursor at the far left of the secondary | Lowest note (col 0), no clamping glitch | M |
| DM-10 | Gaps / mismatched sizes | E3/E4 with different resolutions so the virtual rect has unreachable areas | No crash. Unreachable cells just never play (§9, accepted and documented) | M |
| DM-11 | Hot-plug | While playing, unplug the secondary monitor, then plug it back | Within ~2 s (or on `WM_DISPLAYCHANGE`) the mapping uses the new rect. No exception (§9) | M + A (fake metrics changing mid-path, G2) |
| DM-12 | Resolution / scale change at runtime | Change the scale 100%→150% in Settings while it's running | Mapping recomputed. Tk window still crisp (P2 AC) | M |
| DM-13 | `screen_mode: primary` | Set `primary` on E3 and move onto the secondary | Cursor clamped to the primary rect (§5.1) | A + M |
| DM-14 | UI crispness | E2 @100/150/200% | Window isn't blurry. Fits within ≤ 360×300 logical (P1/P2) | M |

## 4. Stuck notes (§2 item 4, §5 "Stop / Quit / device change / exception", §6 shutdown, §9 "Stuck notes")

Monitor with loopMIDI → MIDI-OX so you can see the messages, and with the GS synth so you can hear them. Run each case
with legato **off** and **on** (legato holds notes indefinitely, so it's the worst case).

| ID | Case | Steps | Expected | Type |
|---|---|---|---|---|
| SN-01 | Stop sequence | Fake: play a note, then Stop | Exactly: note-off(active) → CC123 (All Notes Off, ch 0) → `midiOutReset` (§5) | A |
| SN-02 | Quit from the tray | Hold a note and choose Tray → Quit | Silence. Process exits. Engine joined within the 1 s timeout (§6) | A (sequence) + M |
| SN-03 | Hotkey stop | Ctrl+Alt+M while a note sounds, app unfocused | Silence (S6 AC) | M |
| SN-04 | Device change | See MD-12 | Silence on the old device | A + M |
| SN-05 | Engine exception | Fake raises inside mapping/scheduler | Top-level handler silences the output, logs, no drone (§9) | A |
| SN-06 | Unhandled crash | Debug hook / `--dry-run` fault injection if available, else simulate via test | Silence via `atexit`/handler | A |
| SN-07 | Hard kill | Hold a legato note and run `taskkill /F /IM MouseMusic.exe` | The note stops. WinMM resets when the process closes the handle (§9). Check this on GS **and** loopMIDI→DAW, because a virtual port's receiver may **not** get a reset. Record the result (**OQ-2**) | M |
| SN-08 | Logoff / shutdown | Hold a note and sign out | `WM_ENDSESSION` path silences the output (§9) | M |
| SN-09 | Sleep / resume | Hold a note and put the PC to sleep (Start → Sleep), then resume | No drone after resume. Device still usable or recoverable with Reconnect. **OQ-3**: the spec doesn't mention sleep/resume (`WM_POWERBROADCAST`) | M |
| SN-10 | Device lost while sounding | See MD-09/MD-10 | No drone on the remaining or reattached device | M |
| SN-11 | Rapid start/stop | Toggle the hotkey 50× fast while moving | No stuck notes. No exceptions (G2 edge case) | A + M |
| SN-12 | Note-length expiry | `note_length_ms=250`, legato off, cursor still | Note-off about 250 ms after note-on, within one tick (8 ms at 125 Hz) (§6) | A |
| SN-13 | Rate limit | Cross 5 cells within 30 ms | One note-on for the latest cell when the window closes. No queue (§5) | A |
| SN-14 | Row-change retrigger | Move vertically within one column | Program change, then the same pitch is retriggered (§5) | A |

## 5. SmartScreen and Defender (§7, §9 "SmartScreen", "AV false positives")

| ID | Case | Steps | Expected | Type |
|---|---|---|---|---|
| SD-01 | SmartScreen first run | E5: download the exe from the Release with Edge (so it gets Mark-of-the-Web) and double-click it | "Windows protected your PC" → More info → Run anyway works. Matches the README screenshot (P4) | M |
| SD-02 | Publisher metadata | Exe → Properties → Details | VERSIONINFO has the product name, version = tag, and consistent company/publisher fields (§9) | M |
| SD-03 | Checksums | `Get-FileHash -Algorithm SHA256` on both artifacts | Matches `SHA256SUMS.txt` | M |
| SD-04 | Defender realtime | E5 with Defender on: download, run, use for 5 min | Not quarantined. No detection in Protection history | M |
| SD-05 | Defender manual scan | `MpCmdRun.exe -Scan -ScanType 3 -File <exe>` and the same on the extracted zip | No threats | M |
| SD-06 | VirusTotal | Upload the exe and the zip | Record the detection count and vendor names in the release PR (§9). Pass threshold: **OQ-4** | M |
| SD-07 | UPX disabled | Inspect the spec (`upx=False`). Check the exe for UPX section names | No UPX (§7) | M (review) |
| SD-08 | Onefile extraction | Launch the onefile exe and watch `%TEMP%\_MEI*` | Extracted on launch and removed after a clean Quit. Startup < 3 s on a clean VM (S7 AC) | M |
| SD-09 | `_MEI` cleanup after a kill | `taskkill /F`, then check `%TEMP%` | Record whether a `_MEI*` dir is left behind (known PyInstaller behaviour). Not blocking unless it grows on every run | M |
| SD-10 | Portable zip fallback | Unzip the onedir zip and run it | Works the same. This is the documented fallback if AV objects (§7) | M |
| SD-11 | No hooks | Review: no `SetWindowsHookEx`/pynput imports. Only `GetCursorPos` + `RegisterHotKey` (§1, §9) | Passes | M (code review) + A (optional grep test) |
| SD-12 | Single instance | Launch the exe twice | Second launch focuses the first window and exits. Named mutex `Local\MouseMusicV2` (§9) | M |
| SD-13 | Hotkey conflict | Another app already owns Ctrl+Alt+M. Launch | App still runs. **OQ-5**: the spec doesn't say how a failed `RegisterHotKey` should be reported | M |

## 6. Latency, timing and CPU (§1, §6, §9 "GS Wavetable Synth latency", "Timer resolution / CPU", G4)

The spec gives **no numeric target for end-to-end latency** (it only says GS is ~30–80 ms+ and "we never add latency
ourselves"). The numeric targets it does give are listed here. Everything else is **OQ-6**.

| Spec number | Source |
|---|---|
| Poll rate 125 Hz (8 ms tick) | §1, §4 `poll_hz`, §6 |
| Note-off resolution 8 ms at 125 Hz | §6 |
| Rate limit ≤ 1 note-on / 30 ms, latest wins | §5 |
| CPU ≈ 0 when stopped, < 2% playing | §9, S5 AC |
| Startup < 3 s on clean VM | S7 AC |
| Hysteresis 2 physical px | §5 |

| ID | Case | Method | Expected | Type |
|---|---|---|---|---|
| LT-01 | Internal latency (cell change → `short_msg`) | Engine test with fake clock + fake cursor. Assert the note-on goes out in the same tick as the cell change, with no queueing | ≤ 1 tick (8 ms) internal, except when the 30 ms rate limit applies | A |
| LT-02 | Loop timing on real Windows | `--dry-run --log-level debug` on E1: log tick timestamps for 60 s while playing | Ticks ≈ 8 ms with `timeBeginPeriod(1)` active. Report p50/p95/max jitter. Pass threshold **OQ-6** | M |
| LT-03 | End-to-end perceived latency, GS synth | Slow-motion video (240 fps) of a hand moving the mouse across a marked cell boundary plus the speaker audio. Count frames from crossing to audio onset. Repeat ≥ 20 times | Report median/p95. Compare with the documented 30–80 ms | M (G4) |
| LT-04 | End-to-end, alternative synth | Same as LT-03 with VirtualMIDISynth (and loopMIDI → DAW at a low buffer) | Report the delta versus GS. Feeds the G4 recommendation | M (G4) |
| LT-05 | Bluetooth output | LT-03 on a Bluetooth headset | Record it. Expected to be worse (§9) | M (G4) |
| LT-06 | CPU idle and playing | Process Explorer, 5 min stopped and 5 min continuous sweeping | ≈ 0% stopped. < 2% playing (S5 AC) | M |
| LT-07 | Timer period released | `powercfg /energy` (or check the timer resolution) after Stop | 1 ms period not held while stopped (§6) | M |
| LT-08 | 30-min soak | Scripted or manual continuous movement for 30 min | CPU and memory flat (G3). Memory-growth threshold **OQ-7** | M |
| LT-09 | Startup time | E5, cold and warm, onefile and onedir | < 3 s (S7 AC) | M |

## 7. Settings corruption and persistence (§4, S3)

| ID | Case | Steps | Expected | Type |
|---|---|---|---|---|
| SC-01 | Missing file | Delete `%APPDATA%\MouseMusic\settings.json` | Defaults per §4. File created on the first save | A + M |
| SC-02 | Malformed JSON | Write `{"schema": 1,` | Renamed to `settings.json.bak`, defaults used, no crash, warning logged (§4) | A + M |
| SC-03 | Empty / zero-byte file | Write a 0-byte file | Treated as corrupt (same as SC-02) | A |
| SC-04 | Partial (truncated) file | Truncate a valid file halfway | Same as SC-02 | A |
| SC-05 | Wrong types | `"velocity": "loud"`, `"poll_hz": null` | That key is reset to its default. Other keys are kept. Warning logged | A |
| SC-06 | Out-of-range | `velocity: 300`, `low_note: -5`, `low_note > high_note`, `poll_hz: 0` | Clamped or reset per §4. App runs. `low>high` resolution: **OQ-8** | A |
| SC-07 | Unknown keys | Add `"foo": 1` | Ignored (§4) | A |
| SC-08 | Unknown enum | `scale: "lydian"`, `instrument_set: "x"`, `screen_mode: "y"` | Reset to the default with a warning | A |
| SC-09 | Wrong top-level type / BOM / non-UTF-8 | `[]`, a UTF-8 BOM, Latin-1 bytes | No crash. Corrupt path or parsed tolerantly; record which | A |
| SC-10 | Future schema | `"schema": 99` | **OQ-9**: the spec defines `schema` for migrations but not how a newer schema is handled | A |
| SC-11 | Round trip | Save → load | Equal dataclass (S3 AC) | A |
| SC-12 | Atomic write | Kill the process during a save (fault-inject between the temp write and `os.replace`) | `settings.json` is either the old version or the new one, never partial. No leftover temp files | A + M |
| SC-13 | Debounce | Drag the volume slider for 3 s | One write about 500 ms after the last change (§4) | A (fake clock) |
| SC-14 | Existing `.bak` | Corrupt the file twice | Second corruption: **OQ-10** (overwrite the `.bak` or keep both?) | A |
| SC-15 | Portable mode | Put `settings.json` next to the exe | That file is used instead of APPDATA (§4). Also check `--portable` | M |
| SC-16 | Read-only / locked file | Mark the file read-only, or put the portable exe in a read-only folder | No crash. Warning. Settings still apply in memory. **OQ-11** for user-facing messaging | M |
| SC-17 | Persistence across restart | Change every control, then Quit and relaunch | All persisted (S6 AC) | M |
| SC-18 | Log rotation | Generate > 3 MB of debug logs | Rotates at 3 × 1 MB in `%LOCALAPPDATA%\MouseMusic\logs` (§4) | M |

## 8. Other §9 risks

| ID | Risk | Case | Expected | Type |
|---|---|---|---|---|
| OT-01 | Multiple instances | See SD-12. Also two instances racing on the settings file | Only one runs | M |
| OT-02 | Accessibility / annoyance | Fresh install: launch | No sound until Start (`start_on_launch: false`). Hotkey stops playback. Volume works (§2, §9) | M |
| OT-03 | Close to tray | Close the window | Minimizes to the tray. One-time tooltip shown once only (§2) | M |
| OT-04 | Keyboard access | Tab through every control | All reachable (P2 AC) | M |
| OT-05 | 1-note range / single-row set | `low_note == high_note`, `single_piano` | One column / one row. No divide-by-zero (G2) | A |

## 9. Release-candidate checklist (G3)

Copy this into the release PR for each RC (`vX.Y.Z-rcN`) and tick each item. Any ✗ on a blocking item means no
release. File an issue with repro steps.

**Build and artifacts**
- [ ] `release.yml` green: ruff, pytest, `--self-test` (MD-04)
- [ ] Release contains `MouseMusic-vX.Y.Z-win64.exe`, `MouseMusic-vX.Y.Z-win64-portable.zip`, `SHA256SUMS.txt` (§7)
- [ ] Checksums verified (SD-03). VERSIONINFO matches the tag (SD-02). UPX off (SD-07)
- [ ] Coverage ≥ 90% on `mapping`, `scales`, `config`, `scheduler` (§8)

**Install and security** (clean Win11 VM, E5)
- [ ] SmartScreen flow matches the README (SD-01)
- [ ] Defender realtime + manual scan clean (SD-04, SD-05)
- [ ] VirusTotal results recorded here: exe __/__ · zip __/__ (SD-06)
- [ ] Startup < 3 s, onefile and onedir (LT-09). Portable zip works (SD-10)
- [ ] Single instance (SD-12)

**MIDI**
- [ ] `--list-devices` shows the GS synth (MD-01). Zero devices handled (MD-03)
- [ ] Busy device, missing saved device, loopMIDI routing on ch 0 (MD-05, MD-06, MD-08)
- [ ] Mid-session device loss and endpoint change (MD-09 – MD-11)

**DPI and multi-monitor** (E1–E4)
- [ ] Per-Monitor v2 awareness. Full sweep correct at 100/150/200% (DM-06, DM-07)
- [ ] Negative-X secondary, mixed DPI, hot-plug (DM-08, DM-09, DM-11)

**Stuck notes** (legato on and off)
- [ ] Stop, Quit, hotkey, device change, kill, logoff, sleep (SN-01 – SN-10)

**Performance**
- [ ] CPU ≈ 0 stopped, < 2% playing (LT-06)
- [ ] 30-min soak, CPU and memory flat (LT-08)
- [ ] Latency numbers recorded (LT-03, at least one RC per minor version)

**Settings**
- [ ] Corrupt file → `.bak` + defaults on the real exe (SC-02). Persistence across restart (SC-17). Portable mode (SC-15)

**Docs and UX**
- [ ] README walk-through: download → sound in ≤ 2 min, timed: ___ (P4 AC)
- [ ] Off on launch, close to tray, hotkey works while unfocused (OT-02, OT-03, SN-03)

Sign-off: Grace · date · build SHA · verdict (GO / NO-GO)

## 10. Open questions / spec gaps

For Archimedes to resolve. None of these are guessed in this plan.

1. **OQ-1 Mid-session device loss:** how should the app detect it (an error return from `midiOutShortMsg`? polling?), and what should it do (auto-stop, status message, auto-reconnect)? §9 covers endpoint change via a manual Reconnect only.
2. **OQ-2 Hard-kill silencing on virtual/hardware ports:** §9 relies on "WinMM resets on close". That holds for the GS synth, but a downstream receiver of loopMIDI or external hardware may never see note-off. Is that accepted?
3. **OQ-3 Sleep/resume:** not covered. Should the app stop or silence on `WM_POWERBROADCAST`/suspend and reopen on resume?
4. **OQ-4 VirusTotal threshold:** what detection count blocks a release?
5. **OQ-5 Hotkey registration failure:** what's the UX when Ctrl+Alt+M is already taken? The `hotkey` setting exists, but nothing says whether it can be edited in the UI.
6. **OQ-6 Latency targets:** there's no numeric end-to-end or jitter pass/fail threshold. Only GS's ~30–80 ms is documented. G4 needs an acceptance bar for the "in-process synthesis needed?" call.
7. **OQ-7 Soak "flat":** how much memory or handle growth is acceptable over 30 min?
8. **OQ-8 Validation rules:** min and max for `velocity`, `note_length_ms`, `poll_hz`, the `low_note`/`high_note` bounds, and how `low_note > high_note` is resolved.
9. **OQ-9 Newer `schema`:** what happens on a downgrade or an unknown future schema? Treat it as corrupt, or try a best-effort load?
10. **OQ-10 Repeated corruption:** overwrite the existing `settings.json.bak`, or keep timestamped copies?
11. **OQ-11 Unwritable settings location:** what's the behaviour and message (e.g. portable exe in a read-only folder)?
12. **OQ-12 MIDI device hot-plug:** §9 re-enumerates when the dropdown opens. Should a device that comes back (by saved name) be picked up automatically on Start?
