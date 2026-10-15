# MouseMusic v2 — Test Plan (G1)

Owner: Grace (QA) · Spec: [`ARCHITECTURE.md`](../ARCHITECTURE.md) (v1 of the doc) · Target: Windows 11 x64 (23H2 / 24H2)

This plan covers the manual matrix from §8, risk-based cases for **every** risk in §9, and the release-candidate (RC)
checklist that G3 uses. Spec references are written `§n`. The 12 open questions raised in the first draft were answered in **§11** (binding, and it wins over earlier sections).
Every threshold below that comes from there cites `§11 OQ-n` or `§11 UX-Qn`. What's still ambiguous is listed in
[§10](#10-remaining-ambiguities).

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
| MD-06 | Saved device missing | Set `midi_device` to a name that doesn't exist and launch | Falls back to device 0, logs it, plays sound (§9). W1 shown on **every** launch while it's missing. The fallback is **never** written to `midi_device`; check the file afterwards (§11 UX-Q4) | A + M |
| MD-06b | Explicit pick persists | Pick a device in the dropdown | Written to `midi_device` (§11 UX-Q4) | A |
| MD-07 | Re-enumerate on dropdown open | With the app running, start loopMIDI and create a port, then open the dropdown | The new port appears without a restart (§9) | M |
| MD-08 | loopMIDI routing | Select the loopMIDI port and route it to MIDI-OX or a DAW. Sweep the cursor | Note-on/off and program changes arrive on channel 0 only, **never channel 9** (§5). Program change comes before note-on on a row change | M |
| MD-09 | Virtual port removed mid-session | While playing through loopMIDI, delete the port | Next `midiOutShortMsg` returns non-zero → silence (best effort), close, stop, E4 in the status line, plus a balloon if the window is hidden. **No** auto-reconnect and no polling. The next Start reopens (§11 OQ-1/UX-Q8) | M |
| MD-09a | Device-loss rule (unit) | Fake `short_msg` returns an error mid-note (on note-on, note-off, program change and CC7) | Silence attempted, close, engine state = stopped, E4 posted. No retry loop. No exception escapes | A |
| MD-10 | USB MIDI unplugged mid-session | Play to a USB synth or interface and unplug it | Same as MD-09. After replug, Start (or Reconnect) re-enumerates and opens the **saved** `midi_device` by name, even if a fallback was used earlier in the session. W1 clears. No background hot-plug watching (§11 OQ-12) | M |
| MD-10a | Saved device returns (unit) | Fake enumeration: saved name absent → fallback → name present on the next Start | Second Start opens the saved device and clears W1 (§11 OQ-12) | A |
| MD-11 | Audio endpoint change | GS synth playing to speakers. Unplug the headphones / switch the default output / connect and disconnect Bluetooth | A silent endpoint change produces no error and isn't detected. Manual **Reconnect** (W6) restores sound (§11 UX-Q8). Stop→Start also reopens (§9) | M (G4) |
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
| DM-14 | UI crispness | E2 @100/150/200% | Window isn't blurry. Minimum 340 × 360 logical px, with the status line allowed to grow past that (§11 Q-D1). See TH-10 | M |

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
| SN-07 | Hard kill | Hold a legato note and run `taskkill /F /IM MouseMusic.exe` | The note stops. WinMM resets when the process closes the handle (§9). Also run it on loopMIDI→DAW. A downstream stuck note there is an **accepted limitation**: record it, don't block on it. The README `#no-sound` must describe the workaround (§11 OQ-2) | M (non-blocking) |
| SN-08 | Logoff / shutdown | Hold a note and sign out | `WM_ENDSESSION` path silences the output (§9) | M |
| SN-09 | Sleep while playing | Playing (legato on, note held). Start → Sleep, then wake | On suspend: full silence path (note-off → CC123 → reset) and device closed. On resume: device reopened and playback **resumes** (§11 OQ-3). No drone at any point | M |
| SN-09a | Sleep while stopped | Stopped. Sleep, then wake | The device stays **closed** until Start (MIDI-OX or loopMIDI shows no open). Playback does not start. No sound on wake (§11 A-1, S-2) | A + M |
| SN-09b | Resume reopen fails | Playing via loopMIDI. Sleep, delete the port (or unplug the USB device) while asleep, wake | E4 shown. App stopped. No crash (§11 OQ-3) | M |
| SN-09c | Suspend/resume commands (unit) | Post `suspend`/`resume` commands to the engine with a fake MIDI device, both playing and stopped. Also resume with open failing | Exact silence sequence plus close on suspend. Was-playing flag honoured. E4 on failure. Commands handled on the engine thread (§6, §11 OQ-3) | A |
| SN-09d | Broadcast plumbing | Send `WM_POWERBROADCAST`/`PBT_APMSUSPEND` and `PBT_APMRESUMEAUTOMATIC` to the hotkey thread's message window (e.g. with a `PostMessage` test harness, or `pwrtest /sleep` from the WDK) | Commands posted to the engine. Both `PBT_APMRESUMEAUTOMATIC` and `PBT_APMRESUMESUSPEND` mean resume, and repeats are idempotent (§11 A-1) | A-win / M |
| SN-09g | Message window with no hotkey | Set `hotkey` to `Off`, **and** separately make both Ctrl+Alt+M and Ctrl+Alt+Shift+M fail (W4). Then send the suspend/resume, `WM_ENDSESSION` and `WM_SETTINGCHANGE` (theme) messages | The message window and its thread exist anyway. Power, session and theme handling still work. Required test (§11 A-2) | A-win + M |
| SN-09e | Repeated sleep cycles | Run 5 sleep/wake cycles while playing, then check handles | Handle and thread counts stable (ties to the §11 OQ-7 limits) | M |
| SN-09f | Modern Standby / hibernate | Repeat SN-09 on a Modern Standby (S0) laptop and with Hibernate | Hibernate takes the same path as sleep. On S0, no suspend may arrive at all, which is acceptable: the engine keeps running and if a send fails, E4 applies. Record the behaviour, non-blocking (§11 A-1) | M (non-blocking) |
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
| SD-06 | VirusTotal | Upload the exe and the zip | Record the detection count and vendor names in the release PR. **Gate:** ≤ 3 detections **and** zero from Microsoft Defender, for the exe and the zip separately. The zip's count is what VirusTotal reports for the zip itself. A Defender hit on **any file inside** the zip also blocks (§11 A-8). Otherwise it blocks until a false-positive submission clears it or the build changes (§11 OQ-4) | M (blocking) |
| SD-07 | UPX disabled | Inspect the spec (`upx=False`). Check the exe for UPX section names | No UPX (§7) | M (review) |
| SD-08 | Onefile extraction | Launch the onefile exe and watch `%TEMP%\_MEI*` | Extracted on launch and removed after a clean Quit. Startup < 3 s on a clean VM (S7 AC) | M |
| SD-09 | `_MEI` cleanup after a kill | `taskkill /F`, then check `%TEMP%` | Record whether a `_MEI*` dir is left behind (known PyInstaller behaviour). Not blocking unless it grows on every run | M |
| SD-10 | Portable zip fallback | Unzip the onedir zip and run it | Works the same. This is the documented fallback if AV objects (§7) | M |
| SD-11 | No hooks | Review: no `SetWindowsHookEx`/pynput imports. Only `GetCursorPos` + `RegisterHotKey` (§1, §9) | Passes | M (code review) + A (optional grep test) |
| SD-12 | Single instance | Launch the exe twice | Second launch focuses the first window and exits. Named mutex `Local\MouseMusicV2` (§9) | M |
| SD-13 | Hotkey conflict | Another app already owns Ctrl+Alt+M (e.g. a tiny `RegisterHotKey` helper script). Launch | App runs. `Ctrl+Alt+Shift+M` is used instead: W7 for 15 s, hint/status/tray tooltip show it. With the fallback also taken: W4 for 15 s and the hint reads `(shortcut off)` (§11 OQ-5) | M |
| SD-14 | Hotkey parsing | Table tests: `Ctrl+Alt+M`, `Shift+Win+F12`, `Ctrl+0`, then invalid values (`Ctrl+Alt`, `Hyper+M`, `Ctrl+F13`, `Ctrl+MM`, `""`, `123`) | Valid ones parse (modifiers Ctrl/Alt/Shift/Win + one A–Z/0–9/F1–F12) and are normalised in settings (`alt+ctrl+m` → `Ctrl+Alt+M`). `Off`/`""`/`none` → Off. Any other invalid value in settings.json → reset to `Ctrl+Alt+M` with W3 (§11 OQ-5, revised) | A |
| SD-15 | Hotkey picker | Change the `Shortcut` combobox, including to `Off` | Re-registers immediately (works with the window hidden), persists across restart. Editing the file + restart also works (§11 OQ-5, revised) | M |

## 6. Latency, timing and CPU (§1, §6, §9 "GS Wavetable Synth latency", "Timer resolution / CPU", G4)

Targets come from §1/§5/§6/§9, the S5/S7 acceptance criteria, and **§11 OQ-6/OQ-7**.

| Spec number | Source |
|---|---|
| Poll rate 125 Hz (8 ms tick) | §1, §4 `poll_hz`, §6 |
| Note-off resolution 8 ms at 125 Hz | §6 |
| Rate limit ≤ 1 note-on / 30 ms, latest wins | §5 |
| CPU ≈ 0 when stopped, < 2% playing | §9, S5 AC |
| Startup < 3 s on clean VM | S7 AC |
| Hysteresis 2 physical px | §5 |
| Internal cell change → `short_msg` ≤ 1 tick (8 ms) outside rate limiting, **blocking** | §11 OQ-6 |
| Tick jitter p95 ≤ 4 ms, max ≤ 20 ms over 60 s, **blocking** | §11 OQ-6 |
| End-to-end on GS, wired: median ≤ 100 ms, p95 ≤ 150 ms, **informational** | §11 OQ-6 |
| Soak: working set ≤ +10 MB vs the 2-min value, handles ≤ +50, threads constant, CPU < 2 %, **blocking** | §11 OQ-7 |

| ID | Case | Method | Expected | Type |
|---|---|---|---|---|
| LT-01 | Internal latency (cell change → `short_msg`) | Engine test with fake clock + fake cursor. Assert the note-on goes out in the same tick as the cell change, with no queueing | ≤ 1 tick (8 ms), except when the 30 ms rate limit applies. Blocking (§11 OQ-6) | A |
| LT-02 | Loop timing on real Windows | `--dry-run --log-level debug` on E1: log tick timestamps for 60 s while playing | Ticks ≈ 8 ms with `timeBeginPeriod(1)` active. Jitter p95 ≤ 4 ms **and** max ≤ 20 ms. Blocking (§11 OQ-6) | M |
| LT-03 | End-to-end perceived latency, GS synth | Slow-motion video (240 fps) of a hand moving the mouse across a marked cell boundary plus the speaker audio. Count frames from crossing to audio onset. Repeat ≥ 20 times | Target median ≤ 100 ms, p95 ≤ 150 ms on wired output. Informational, not blocking. If the median is > 100 ms on most machines, G4 recommends in-process synthesis (§11 OQ-6) | M (G4) |
| LT-04 | End-to-end, alternative synth | Same as LT-03 with VirtualMIDISynth (and loopMIDI → DAW at a low buffer) | Report the delta versus GS. Feeds the G4 recommendation | M (G4) |
| LT-05 | Bluetooth output | LT-03 on a Bluetooth headset | Record it. Expected to be worse (§9) | M (G4) |
| LT-06 | CPU idle and playing | Process Explorer, 5 min stopped and 5 min continuous sweeping | ≈ 0% stopped. < 2% playing (S5 AC) | M |
| LT-07 | Timer period released | `powercfg /energy` (or check the timer resolution) after Stop | 1 ms period not held while stopped (§6) | M |
| LT-08 | 30-min soak | Scripted or manual continuous movement for 30 min | Sample the working set, handles, threads and CPU at 2 min (baseline) and at 30 min: WS ≤ baseline + 10 MB, handles ≤ baseline + 50, long-lived thread count (main/Tk, engine, tray, message window) unchanged, CPU < 2 %. Transient threads (balloons, save debounce) are excluded but must exit: after 10 s idle at the end, the total thread count equals the 2-min baseline. Blocking (§11 OQ-7, A-7) | M |
| LT-09 | Startup time | E5, cold and warm, onefile and onedir | < 3 s (S7 AC) | M |

## 7. Settings corruption and persistence (§4, S3)

| ID | Case | Steps | Expected | Type |
|---|---|---|---|---|
| SC-01 | Missing file | Delete `%APPDATA%\MouseMusic\settings.json` | Defaults per §4 (note `velocity` 100, `volume` 80). File created on the first save | A + M |
| SC-02 | Malformed JSON | Write `{"schema": 1,` | Renamed to `settings.json.bak`, defaults used, no crash, warning logged (§4) | A + M |
| SC-03 | Empty / zero-byte file | Write a 0-byte file | Treated as corrupt (same as SC-02) | A |
| SC-04 | Partial (truncated) file | Truncate a valid file halfway | Same as SC-02 | A |
| SC-05 | Wrong types | `"velocity": "loud"`, `"poll_hz": null` | That key is reset to its default, with warning W3. Other keys are kept (§11 OQ-8) | A |
| SC-06 | Out-of-range clamping | Each key independently, below and above its bounds: `velocity` (1–127), `note_length_ms` (50–2000), `poll_hz` (30–250), `low_note`/`high_note` (0–127), `volume` (0–100). Also each exact boundary | Clamped to the bound, independently per key (§11 OQ-8) | A |
| SC-06a | Narrow / inverted range | `(60,65)` → `(60,72)`. `(120,100)` → `(120,127)` → then `low=115`. `(127,127)` → `(115,127)`. `(0,0)` → `(0,12)`. `(-5,300)` → `(0,127)` | Matches the §11 OQ-8 rule: keep low, `high=min(127,low+12)`, then `low=high-12` if still < 12 | A |
| SC-07 | Unknown keys | Add `"foo": 1` | Ignored (§4) | A |
| SC-08 | Unknown enum | `scale: "lydian"`, `instrument_set: "x"`, `screen_mode: "y"`, `theme: "blue"`, `theme: 1` | Reset to the default with W3; `theme` → `system` (§11 OQ-8, Q-D2) | A |
| SC-09 | Wrong top-level type / BOM / non-UTF-8 | `[]`, a UTF-8 BOM, Latin-1 bytes | No crash. Corrupt path or parsed tolerantly; record which | A |
| SC-10 | Future schema | `"schema": 99` with known and unknown keys | Known keys loaded and validated. File **not rewritten** (byte-identical after launch and Quit with no changes). Warning in the log, no UI message. After a user change, the save writes the current schema (§11 OQ-9) | A + M |
| SC-10a | Old / missing schema | Remove `schema`, or set it lower than current | Migrations run in order (§11 OQ-9) | A |
| SC-11 | Round trip | Save → load | Equal dataclass (S3 AC) | A |
| SC-12 | Atomic write | Kill the process during a save (fault-inject between the temp write and `os.replace`) | `settings.json` is either the old version or the new one, never partial. No leftover temp files | A + M |
| SC-13 | Debounce | Drag the volume slider for 3 s | One write about 500 ms after the last change (§4) | A (fake clock) |
| SC-14 | Existing `.bak` | Corrupt the file twice | Single `settings.json.bak` overwritten with the latest corrupt file. No accumulation. Overwrite logged (§11 OQ-10) | A |
| SC-15 | Portable mode | Put `settings.json` next to the exe | That file is used instead of APPDATA (§4). Also check `--portable` | M |
| SC-16 | Read-only / locked file | Mark the file read-only, or put the portable exe in a read-only folder | W5 shown **once per session**. Settings stay in memory. Each later change retries the save. Path and error logged. **No** fallback to APPDATA (§11 OQ-11) | A + M |
| SC-17 | Persistence across restart | Change every control, then Quit and relaunch | All persisted (S6 AC) | M |
| SC-17a | Window position | Move the window, restart. Then edit `window_x`/`window_y` to a point that's off-screen, and also try `null` | Restored. An off-screen point → centred, and the file isn't overwritten until the user moves the window. `null` → centred on primary (§11 UX-Q1) | A + M |
| SC-17b | Tray hint | Close to tray twice, restart | Balloon once only. `tray_hint_shown` true, independent of `first_run_done` (§11 UX-Q2) | M |
| SC-18 | Log rotation | Generate > 3 MB of debug logs | Rotates at 3 × 1 MB in `%LOCALAPPDATA%\MouseMusic\logs` (§4) | M |

## 7a. Volume setting (§2, §4, §11 UX-Q5, OQ-8)

Spec: the `volume` key is 0–100 % (default 80) and drives the UI Volume slider. It's sent as **CC7 Channel Volume** =
`round(volume * 127 / 100)` on device open, on Start, and on every change. `velocity` (1–127, default 100) is
file-only and fixed for every note-on.

| ID | Case | Steps | Expected | Type |
|---|---|---|---|---|
| VO-01 | Default | No settings file | `volume` = 80. First CC7 value = 102 | A |
| VO-02 | Scaling formula | Table: 0→0, 1→1, 50→64, 79→100, 80→102, 99→126, 100→127 | `round(v*127/100)`. Half-up is the intent. For integers 0–100 the only .5 case is 50 → 64 under either rule, so no code change (§11 A-3) | A |
| VO-03 | Range validation | `-1`, `101`, `1000`, `0`, `100` | Clamped to 0–100 (§11 OQ-8) | A |
| VO-04 | Wrong type | `"loud"`, `null`, `[]`, `true`, `55.5` | `bool`, string, null, list → 80 + W3. A finite float is rounded, then clamped (55.5 → 56). NaN/inf → 80 + W3. The same rule applies to every integer setting (§11 A-4) | A |
| VO-05 | Missing key only | Valid file without `volume` | 80, and other keys kept | A |
| VO-06 | Corruption fallback | Malformed file | `.bak` + defaults → volume 80 (§4, §11 OQ-10) | A |
| VO-07 | When CC7 is sent | Fake MIDI: open, Start, slider change while stopped, slider change while playing, device change, Reconnect, resume from sleep | CC7 on channel 0 at open, at Start and on each change. Never on channel 9. Sent through the engine thread (§6) | A |
| VO-08 | Velocity independence | Change the volume | Note-on velocity stays at `velocity` (100). Only CC7 changes | A |
| VO-09 | Audible effect | GS synth: 100 → 50 → 0 while playing | Audibly quieter. 0 = silent but notes still sent (check with MIDI-OX) | M |
| VO-10 | Effect on a virtual port | loopMIDI → MIDI-OX | CC7 `B0 07 xx` values match VO-02 | M |
| VO-11 | Persistence | Set 37, wait > 500 ms, Quit, relaunch | `volume: 37` in the file. Slider shows 37. First CC7 = 47 | A + M |
| VO-12 | Debounced writes | Drag the slider quickly | CC7 sent live. One file write about 500 ms after the last change (§4) | A |
| VO-13 | Rate of CC7 while dragging | Drag the slider fast while playing | No audible glitch or stall. At most one CC7 per tick (≤ 125/s), latest value wins. File save still debounced at 500 ms (§11 A-5, S-1) | A + M |
| VO-14 | Keyboard access | Arrow keys on the slider | Changes the volume (P2) | M |

## 7b. Theme / dark mode (§4 `theme`, §11 Q-D1–Q-D4, docs/ux.md §11 via PR #22)

Status: the spec is accepted (§4, §11), but on `main` at 54ba2fe **there's no `theme` in the code yet** (no setting, no Theme row, window minimum 340×330). These cases are written against the spec and PR #22's ux §11, and become runnable when it's implemented.

| ID | Case | Steps | Expected | Type |
|---|---|---|---|---|
| TH-01 | Default | No settings file | `theme` = `system`. No schema bump (`schema` stays 1) (§4, Q-D2) | A |
| TH-02 | Validation (case-insensitive) | `"light"`, `"DARK"`, `" Dark "`, `"System\t"` | Stripped and lowercased → `light`/`dark`/`system`, **no** W3 (§11 B-1, ux §1) | A |
| TH-02a | Invalid values | `"blue"`, `""`, `"   "`, `"dark mode"`, `1`, `null`, `true`, `["dark"]` | → `system` + W3 (§11 B-1) | A |
| TH-02b | Canonical write-back | Load `" Dark "`, then change any setting so it saves | File now has `"theme": "dark"`. Without a change the file isn't rewritten (§11 B-1, OQ-9 no-rewrite rule) | A |
| TH-03 | Older build ignores the key | Load a file with `theme` in an older build (or `validate` with an unknown key) | Ignored, no W3 (§4 unknown keys) | A |
| TH-04 | System resolution | Windows Settings → Personalization → Colors: Light, then Dark, with `theme: system` | App palette follows `AppsUseLightTheme` | M |
| TH-05 | Live follow | Switch Windows Light↔Dark with the app open (window visible and hidden) | Repaints without a restart (`WM_SETTINGCHANGE` "ImmersiveColorSet", with `<FocusIn>` as a backup, per PR #22). Title bar turns dark too (DWM attribute 20/19) | M |
| TH-06 | Override | Pick Dark in the Theme row while Windows is Light, and the reverse | Override wins, applies live, and persists across a restart | A (controller) + M |
| TH-07 | High contrast | Turn on a contrast theme (Settings → Accessibility → Contrast themes) | High contrast overrides `theme`: system colours are used and the palette is off (§4) | M |
| TH-08 | Combobox popdowns | Dark mode: open each dropdown | Popdown list is dark and readable, including after a live switch (PR #22) | M |
| TH-09 | Tray menu | Dark mode: right-click the tray icon | Menu stays the light system default. That's expected, not a bug (§11 Q-D3) | M |
| TH-10 | Contrast | Run `tools/contrast.py` if present, or inspect palette tokens | Text ≥ 4.5:1, UI/focus ≥ 3:1, disabled controls exempt (PR #22) | A |
| TH-11 | Status colours in dark | Trigger W3/W4/E4 in dark mode | Amber/red dots and text legible | M |
| TH-12 | No new dependency | Check `requirements.txt` | No `sv-ttk`. Stays on stdlib `clam` (§11 Q-D4) | A (review) |
| TH-13 | Theme broadcast without a hotkey | Covered by SN-09g | Theme change still followed with the hotkey `Off` or after W4 (§11 A-2) | A-win + M |

### Minimum window size (§11 Q-D1)

| ID | Case | Steps | Expected | Type |
|---|---|---|---|---|
| WS-01 | Minimum at 100 % | Launch with short status text | Client area 340 × 360 logical px (Shortcut + Theme rows). Width fixed at 340. Code check: `ui/window.py` minimum `HEIGHT` is 360, not the old 330 (§11 B-4, ux §1) | A (window test) + M |
| WS-02 | Grows for long warnings | Trigger the two-key W4 (both shortcuts taken) | Height > 360 so every wrapped line is visible. Shrinks back to 360 once it clears | A + M |
| WS-03 | DPI scaling | 150 % and 200 % | Size scales (≈ 510 × 540 and 680 × 720 physical). Nothing clipped | M |
| WS-04 | Height cap = work area | Unit: fake work area shorter than the required height (e.g. 400 px) with a 5-line status | Height = work-area height of the **current monitor** (`rcWork`, taskbar never covered). Never taller (§11 B-2) | A |
| WS-04a | Truncation | Same as WS-04 | Status shows only the whole lines that fit; the last ends in `…`. No scrollbar. The full text is in the status tooltip **and** the log (§11 B-2, ux §1/row 9) | A + M |
| WS-04b | Truncation clears | Shorten the message (warning expires) or move to a taller monitor | Full text visible again, no `…`. Window shrinks back toward 360 (§11 B-2) | A |
| WS-04c | Real small screen | 1366 × 768 @ 200 % (or 1280 × 720 @ 200 %), trigger the two-key W4. Hover the status | Window bottom stays above the taskbar. If it's truncated, `…` shows and the tooltip has the full W4 text | M |
| WS-05 | Re-clamp after growth | Unit: window placed with its bottom 20 px above the work-area bottom, then status grows by 3 lines | `place_window((x,y),(w,h_capped),work_areas,primary)` runs after each height change: window moves **up** only as far as needed to stay inside the work area. It grows downward when there's room (§11 B-3) | A |
| WS-05a | Taller than the area | Height capped to the area (WS-04) | Window pinned to the work area's top (`_clamp`) (§11 B-3) | A |
| WS-05b | Temporary position not saved | After WS-05's automatic move, let the debounce pass, then check settings | `window_x`/`window_y` unchanged. Only a user drag saves a new position. After the status shrinks, the window doesn't jump back by itself unless spec says so (see C-1) | A + M |
| WS-05c | Manual edge case | Drag the window near the bottom of a monitor, trigger W4 | Window moves up to stay on screen. Quit + relaunch: opens at the dragged position, not the moved one | M |

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
- [ ] VirusTotal: exe __/__ · zip __/__. Each ≤ 3 **and** 0 from Microsoft Defender (SD-06, §11 OQ-4) — **blocking**
- [ ] Startup < 3 s, onefile and onedir (LT-09). Portable zip works (SD-10)
- [ ] Single instance (SD-12)

**MIDI**
- [ ] `--list-devices` shows the GS synth (MD-01). Zero devices handled (MD-03)
- [ ] Busy device, missing saved device, loopMIDI routing on ch 0 (MD-05, MD-06, MD-08)
- [ ] Mid-session device loss → E4, saved device reopened on Start, Reconnect after an endpoint change (MD-09 – MD-11, §11 OQ-1/OQ-12)
- [ ] Volume: CC7 values, persistence, audible effect (VO-07, VO-09, VO-11)

**DPI and multi-monitor** (E1–E4)
- [ ] Per-Monitor v2 awareness. Full sweep correct at 100/150/200% (DM-06, DM-07)
- [ ] Negative-X secondary, mixed DPI, hot-plug (DM-08, DM-09, DM-11)

**Stuck notes** (legato on and off)
- [ ] Stop, Quit, hotkey, device change, logoff, sleep/resume both ways (SN-01 – SN-10)
- [ ] Hard kill: result recorded, non-blocking (SN-07, §11 OQ-2)

**Performance**
- [ ] CPU ≈ 0 stopped, < 2% playing (LT-06)
- [ ] Tick jitter p95 ≤ 4 ms, max ≤ 20 ms (LT-02) — **blocking**
- [ ] 30-min soak: WS ≤ +10 MB, handles ≤ +50, threads constant, CPU < 2 % (LT-08) — **blocking**
- [ ] End-to-end GS latency recorded: median __ ms / p95 __ ms vs 100/150 targets (LT-03, informational)

**Settings**
- [ ] Corrupt file → `.bak` + defaults on the real exe (SC-02). Persistence across restart (SC-17). Portable mode (SC-15). Unwritable → W5 (SC-16)
- [ ] Hotkey conflict → W7 fallback, then W4 + `(shortcut off)` when both are taken (SD-13)
- [ ] Dark mode and minimum window size (TH-04–TH-09, WS-01–WS-02)
- [ ] Christopher's quick pass: [`rc-manual-checklist.md`](rc-manual-checklist.md)

**Docs and UX**
- [ ] README walk-through: download → sound in ≤ 2 min, timed: ___ (P4 AC)
- [ ] Off on launch, close to tray, hotkey works while unfocused (OT-02, OT-03, SN-03)

Sign-off: Grace · date · build SHA · verdict (GO / NO-GO)

## 10. Resolved and remaining ambiguities

A-1 – A-8 were answered in **§11** (commit 5ef93d1) and are applied in the cases above: A-1 → SN-09a/09d/09f; A-2 → SN-09g/TH-13; A-3 → VO-02; A-4 → VO-04; A-5 → VO-13; A-6 → see below; A-7 → LT-08; A-8 → SD-06.

**A-6 (§11):** user-facing W/E codes and copy are owned by `docs/ux.md`. ARCHITECTURE only defines when they trigger. Test cases reference codes by ID (W1, W3, W4, W7, E2, E4, …). Copy changes go through a ux.md PR that updates the tests in the same PR.

B-1 – B-4 were answered in **§11** (commit 35c01d7) and docs/ux.md §1: B-1 → TH-02/02a/02b; B-2 → WS-04/04a/04b/04c; B-3 → WS-05/05a/05b/05c; B-4 → WS-01 (minimum 340 × 360, grows to fit; code `HEIGHT` must move from 330 to 360).

Still open:
- **B-5 Instrument audition:** there's no CLI flag or preset to play one GM program directly. A `--play-instrument N` (or similar) flag would make the RC listen check one click.
- **C-1 Restoring after a temporary move:** B-3 says the moved position isn't saved, but not whether the window should return to its pre-growth position on screen once the status shrinks again.
- **C-2 Truncation and screen readers:** the tooltip and log carry the full text (B-2). Is the status label's accessible name the full or the truncated text?

### Pending: cell granularity (CG-G1)
On hold until Archimedes revises #23 (slots from UI Automation button/tray rects, `taskbar_slot_source: auto|uia|fixed`, every taskbar on any monitor). The TB-xx cases will be written against that revision.
