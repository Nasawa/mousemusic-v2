# MouseMusic v2 — Architecture

Status: **Accepted (v1 of this doc)** · Owner: Archimedes (architecture) · Target: Windows 11 x64

MouseMusic v2 is a rewrite of [Nasawa/mousemusic](https://github.com/Nasawa/mousemusic): the global cursor position
drives MIDI output, with **X → pitch** and **Y → instrument (GM program)**. The original was a *sensory-substitution*
experiment: if the mapping is consistent, you eventually learn where the cursor is by ear. That goal drives one rule
in this design: **the mapping must be deterministic and stable**. The same screen position always gives the same sound,
across sessions and monitor setups, unless the user changes a setting.

Problems in v1 that v2 fixes:

| v1 behaviour | Problem | v2 fix |
|---|---|---|
| `x % 128`, `y % 128` on raw pixels | Wraps every 128 px, so the same note shows up ~15× across a 1080p screen and pitch can't be learned spatially | Normalize position to the virtual desktop, then quantize into a grid of cells |
| Busy loop, blocking `Thread.sleep(50)` per note | 100% CPU, notes queue up behind the cursor | Fixed-rate poller (~125 Hz) plus a non-blocking note scheduler |
| Notes on every pixel moved | Machine-gun noise | A new note only when the cursor enters a new cell |
| Program change on every move | Clicks, cut-off notes | Program change only when the Y row changes |
| 50×50 window as the only UI | Not user-friendly | Small control window plus tray icon |
| Needs a JDK and javac | Hard to install | One downloadable `.exe` |

---

## 1. Stack decision

**Decision: Python 3.12 + Tkinter (window) + pystray (tray) + direct WinMM MIDI via `ctypes`, packaged with PyInstaller
in GitHub Actions and attached to a GitHub Release.**

I'm keeping the coordinator's proposal with two changes (the MIDI layer and packaging) and a few refinements.

### Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Python + PyInstaller** (proposed) | Fast to build, tiny codebase, easy for the team to test, Tk ships with CPython | PyInstaller exe sizes (~10–15 MB), well-known antivirus false positives, Python startup ~1 s | **Chosen**, with AV mitigations (§9) |
| C# / .NET 8 single-file (WinForms + NAudio or winmm P/Invoke) | Native look, best Windows integration, fewer AV heuristics, signing story is the same | Self-contained single file is ~60–150 MB (trimming and WinForms don't mix well); framework-dependent needs the .NET runtime installed, which hurts "simple to install"; heavier CI and toolchain | Rejected. Not *clearly* better for an app this small, and the install story is worse unless we trim aggressively |
| Rust / Go native | Tiny exe, no AV issues | Higher dev cost for the GUI and tray; slower iteration | Overkill |
| Java (keep v1 stack) | Existing code | JRE install or jlink bundle, Gervill's software synth latency | No |

### MIDI library (challenge to the proposal)

| Library | Notes | Verdict |
|---|---|---|
| `mido` + `python-rtmidi` | Good API, but rtmidi is a compiled C++ extension: one more wheel to pin, a bigger binary, another thing AV can flag. It's also cross-platform machinery we don't need | Rejected |
| `pygame.midi` (PortMidi) | Pulls in all of SDL/pygame (~10+ MB) just for MIDI out | Rejected |
| **WinMM via `ctypes`** (`midiOutGetNumDevs`, `midiOutGetDevCapsW`, `midiOutOpen`, `midiOutShortMsg`, `midiOutReset`, `midiOutClose`) | Zero dependencies and exactly the API the GS synth sits behind. About 80 lines of code, and it's easy to fake in tests | **Chosen** |

Note-on, note-off, program change and CC are all 3-byte *short messages*, so `midiOutShortMsg` covers everything we need.
The `MidiOut` interface is abstract (§3), so the backend can be swapped (for example rtmidi for macOS/Linux) later without
touching the core.

### Other libraries

- **Cursor position:** `ctypes` → `user32.GetCursorPos` (physical pixels once per-monitor DPI aware) and
  `GetSystemMetrics(SM_XVIRTUALSCREEN/SM_YVIRTUALSCREEN/SM_CXVIRTUALSCREEN/SM_CYVIRTUALSCREEN)` (76–79).
  No `pynput` and no global hooks. Polling avoids keylogger-like hook heuristics in AV software.
- **UI:** Tkinter/ttk (stdlib).
- **Tray:** `pystray` (+ `Pillow` for the icon image). Tray icon menu: Start/Stop, Show window, Quit.
- **Settings:** stdlib `json` + `dataclasses`. No extra dependencies.

### Version pinning

- Python **3.12.x** (pinned in `.python-version` and in the workflow's `actions/setup-python`).
- Runtime deps in `requirements.txt` with exact pins (`pystray==0.19.x`, `Pillow==11.x.y`). Sprite picks the
  current latest patch at implementation time and pins `==` exactly.
- Dev and build deps in `requirements-dev.txt`: `pyinstaller==6.x.y`, `pytest`, `pytest-cov`, `ruff`. All `==` pinned.
- Dependabot (pip + github-actions, monthly) proposes bumps. CI must pass before any bump is merged.

---

## 2. User experience (summary — Pragma owns details)

1. Download `MouseMusic-vX.Y.Z-win64.exe` from Releases and double-click it. There's no installer.
2. A small window (~320×260) opens, plus a tray icon. Playback is **off** until the user clicks **Start**, so it never
   blasts sound on launch.
3. Controls: Start/Stop (also the global hotkey **Ctrl+Alt+M**, registered with `RegisterHotKey`, so no hook is needed),
   **Scale** (Chromatic, Major, Minor, Pentatonic major, Pentatonic minor, Blues), **Key/root** (C…B),
   **Pitch range** (low/high octave, default C2–C7), **Instrument set**, **Volume**, **Note length**,
   and a **MIDI output device** dropdown (default: Microsoft GS Wavetable Synth).
4. Closing the window minimizes to the tray (one-time tooltip explains this). Tray → Quit exits, sends All Notes Off,
   and closes the device.
5. A status line shows the current note name, instrument name and device, e.g. "E4 · Vibraphone".

---

## 3. Module layout

```
mousemusic-v2/
├─ ARCHITECTURE.md
├─ README.md                    # Pragma
├─ LICENSE
├─ pyproject.toml               # metadata, ruff + pytest config
├─ requirements.txt             # runtime pins
├─ requirements-dev.txt         # build/test pins
├─ .python-version
├─ mousemusic.spec              # PyInstaller spec (checked in, not generated)
├─ assets/
│  ├─ icon.ico                  # multi-size 16–256
│  └─ version_info.txt          # Windows VERSIONINFO resource (template filled by CI)
├─ src/mousemusic/
│  ├─ __init__.py               # __version__
│  ├─ __main__.py               # entry: DPI awareness, single-instance mutex, logging, start App
│  ├─ app.py                    # wiring/lifecycle: builds Engine, UI, Tray; clean shutdown
│  ├─ config.py                 # Settings dataclass, load/save/validate/migrate JSON
│  ├─ mapping.py                # PURE: (x,y,screen rect,settings) -> Cell -> (note, program)
│  ├─ scales.py                 # PURE: scale interval tables, note naming
│  ├─ instruments.py            # PURE: GM program names + instrument sets
│  ├─ engine.py                 # poll thread: cursor -> cell change -> scheduler
│  ├─ scheduler.py              # note-on/off timing, monophonic voice, program changes
│  ├─ platform/
│  │  ├─ __init__.py
│  │  ├─ win_cursor.py          # GetCursorPos, virtual screen metrics, DPI awareness
│  │  ├─ win_hotkey.py          # RegisterHotKey message loop thread
│  │  └─ single_instance.py     # named mutex
│  ├─ midi/
│  │  ├─ __init__.py            # MidiOut protocol: list_devices/open/short_msg/reset/close
│  │  ├─ winmm.py               # ctypes WinMM backend
│  │  └─ fake.py                # records messages; used by tests and --dry-run
│  └─ ui/
│     ├─ window.py              # Tk/ttk control window
│     └─ tray.py                # pystray icon + menu
├─ tests/
│  ├─ test_mapping.py  test_scales.py  test_config.py  test_scheduler.py  test_engine.py
│  └─ smoke/test_winmm_smoke.py # Windows-only, opens device, sends one note (marked)
└─ .github/
   ├─ workflows/ci.yml          # push/PR: ruff + pytest on windows-latest (+ ubuntu for pure modules)
   ├─ workflows/release.yml     # tag v*: build, smoke-run, attach to Release
   └─ dependabot.yml
```

Dependency rule: `mapping`, `scales`, `instruments`, `config` and `scheduler` import **nothing** from `platform/`,
`midi/winmm` or `ui/`. That keeps the core testable on any OS, with the clock and MIDI injected.

---

## 4. Configuration

- **Format:** JSON, human-readable and indented. Includes a `"schema": 1` field for migrations.
- **Location:** `%APPDATA%\MouseMusic\settings.json` (via `os.environ["APPDATA"]`). Logs go to
  `%LOCALAPPDATA%\MouseMusic\logs\mousemusic.log` (rotating, 3 × 1 MB).
- **Portable mode:** if `settings.json` sits next to the exe, it's used instead. Easy to explain, and handy for USB sticks.
- **Robustness:** unknown keys are ignored. Invalid values are clamped or reset to defaults with a log warning. A corrupt
  file is renamed `settings.json.bak` and replaced with defaults, so the app never crashes on bad settings. Writes are
  atomic (temp file + `os.replace`) and debounced 500 ms after the last UI change.

Defaults:

```json
{
  "schema": 1,
  "midi_device": "Microsoft GS Wavetable Synth",
  "scale": "pentatonic_major",
  "root": "C",
  "low_note": 36,
  "high_note": 96,
  "instrument_set": "classic",
  "velocity": 90,
  "note_length_ms": 250,
  "legato": false,
  "poll_hz": 125,
  "screen_mode": "virtual_desktop",
  "start_on_launch": false,
  "hotkey": "Ctrl+Alt+M",
  "first_run_done": false
}
```

Pentatonic is the default because every note sounds consonant with every other, which makes the best first impression.
Chromatic is available as a setting.

---

## 5. Core mapping logic (`mapping.py`, `scales.py`, `instruments.py`)

1. **Normalize.** Get the virtual-desktop rect `(vx, vy, vw, vh)`, which can have negative origins with monitors left of
   or above the primary. `u = (x - vx) / vw`, `v = (y - vy) / vh`, clamped to `[0, 1)`.
   `screen_mode: "primary"` uses the primary monitor rect instead and clamps the cursor to it.
2. **Columns = notes.** Build the allowed note list from `scale`, `root`, `low_note..high_note` (for example C pentatonic
   from 36 to 96 gives 26 notes). `col = floor(u * len(notes))` and `note = notes[col]`. The number of columns equals the
   number of notes, so cells are evenly sized and each column is one note. That's learnable, unlike `x % 128`.
3. **Rows = instruments.** `row = floor(v * len(set.programs))` and `program = set.programs[row]`. Top row is index 0.
4. **Cell** = `(col, row)`. Mapping is a pure function. Same inputs, same cell, always.
5. **Hysteresis:** a cell change only registers once the cursor is ≥ 2 physical px past the boundary. This stops
   flutter when the hand rests on an edge. The value is configurable in code, not in the UI.

**Instrument sets** (GM program numbers 0-based, names in `instruments.py`):

| Set | Programs (rows top → bottom) |
|---|---|
| `classic` (default) | 0 Piano, 11 Vibraphone, 24 Nylon Guitar, 40 Violin, 42 Cello, 56 Trumpet, 73 Flute, 71 Clarinet |
| `mellow` | 4 E.Piano, 11 Vibraphone, 12 Marimba, 46 Harp, 48 Strings, 52 Choir Aahs, 89 Warm Pad |
| `percussive` | 8 Celesta, 9 Glockenspiel, 12 Marimba, 13 Xylophone, 14 Tubular Bells, 108 Kalimba, 114 Steel Drums |
| `single_piano` | 0 (one row, so Y does nothing and only pitch is heard) |
| `full_gm` | 0..127 (v1 behaviour: 128 rows) |

**Note triggering and note-off (`scheduler.py`):**

- Monophonic on MIDI channel 0 (channel 9 is never used, since it's drums in GM).
- On **column change** (new cell): send note-off for the sounding note, then note-on for the new note, and schedule
  note-off at `now + note_length_ms`. If `legato` is on, the note holds until the next cell or until Stop.
- On **row change**: send a program change *before* the next note-on. A row change with no column change re-triggers the
  same pitch on the new instrument, so the user hears the instrument boundary. That's needed for spatial learning.
- **Rate limit:** at most 1 note-on per 30 ms (≈33 notes/s). If the cursor crosses several cells inside that window,
  only the most recent cell is played when the window ends (latest wins, never a queue). This fixes v1's backlog.
- **Stop / Quit / device change / exception:** send note-off for the active note, then CC123 All Notes Off, then
  `midiOutReset`. No stuck notes, ever.

---

## 6. Threading model

| Thread | Responsibility |
|---|---|
| **Main (Tk)** | UI event loop. The only thread that touches Tk widgets. Receives engine status through a `queue.Queue` drained by `root.after(50, …)` |
| **Engine** (daemon) | Loop at `poll_hz` using `time.perf_counter()` deadlines (no busy-spin). Calls `GetCursorPos`, runs mapping and hysteresis, calls the scheduler. Due note-offs are checked every tick (8 ms resolution at 125 Hz, which is fine for 250 ms notes) |
| **Tray** | `pystray.Icon.run_detached()`. Menu callbacks only post commands to the engine/UI queues |
| **Hotkey** | `RegisterHotKey` + `GetMessageW` loop. Posts a toggle command |

- All MIDI calls happen on the engine thread, so the device handle has a single owner. Commands from other threads
  (`start`, `stop`, `set_settings`, `set_device`, `quit`) go through a thread-safe command queue that the engine drains
  every tick.
- Settings are immutable dataclass snapshots replaced atomically. The engine never reads half-updated settings.
- Shutdown: the UI posts `quit`, the engine silences and closes MIDI and exits, the main thread joins it (1 s timeout),
  then the tray and hotkey threads stop.
- `timeBeginPeriod(1)` while playing (`timeEndPeriod` on stop) so the 8 ms sleeps are accurate on Windows. The default
  15.6 ms timer granularity would jitter.

---

## 7. Packaging and release

- **Primary artifact:** PyInstaller **onefile**, `--windowed`, with icon and VERSIONINFO, built from `mousemusic.spec`:
  `MouseMusic-vX.Y.Z-win64.exe`. This matches "simple to run".
- **Secondary artifact (challenge/addition):** **onedir** zipped, `MouseMusic-vX.Y.Z-win64-portable.zip`. Onefile
  unpacks itself to `%TEMP%` on every launch, which is the main trigger for AV heuristics and adds ~1 s to startup. The zip
  is the documented fallback if Defender or another AV objects. Shipping both costs one extra CI step.
- `SHA256SUMS.txt` is attached alongside.
- **UPX disabled** (`upx=False`). UPX packing sharply raises false-positive rates.
- **Workflow `release.yml`**, triggered on `push` of tags `v*.*.*`, `runs-on: windows-latest`:
  1. checkout → setup-python 3.12 (pip cache) → `pip install -r requirements-dev.txt -r requirements.txt`
  2. `ruff check` + `pytest` (fail = no release)
  3. Stamp version from the tag into `__init__.py` and `version_info.txt`
  4. `pyinstaller mousemusic.spec` (onefile) and `pyinstaller mousemusic.spec --onedir-variant` (or a second spec), then zip
  5. **Smoke test:** run `MouseMusic.exe --self-test`. It initializes WinMM enumeration, mapping and config in a temp
     dir, exits 0, and needs no audio device (it tolerates 0 devices on the runner)
  6. Generate SHA256SUMS → `softprops/action-gh-release` (pinned by commit SHA) creates the Release with auto-generated notes
- **`ci.yml`:** on push/PR to main, runs ruff + pytest on `windows-latest` and `ubuntu-latest` (pure modules only on
  ubuntu), then builds the exe and uploads it as a workflow artifact (7-day retention) so Grace can test PRs.
- Versioning: SemVer, starting at `v0.1.0`. `main` is always releasable. A release happens by pushing a tag.
- **Signing:** none in v0.x (cost). The workflow keeps a placeholder step that signs with `signtool` when the
  `SIGNING_CERT` secret exists, ready for Azure Trusted Signing later.

CLI flags (for support and testing): `--self-test`, `--dry-run` (fake MIDI, prints messages), `--list-devices`,
`--portable`, `--log-level`.

---

## 8. Testing strategy

| Layer | How | Where |
|---|---|---|
| Pure logic (mapping, scales, instruments, config) | pytest, table-driven. Property tests: monotonic pitch in X, every cell is within range, determinism, negative virtual origins | ubuntu + windows CI |
| Scheduler | Injected fake clock + `FakeMidiOut`. Asserts exact message sequences (note-off before note-on, program change before note, rate limit, All Notes Off on stop) | CI |
| Engine | Fake cursor source fed scripted paths (sweep, jitter at a boundary, multi-monitor negative coords) → asserted MIDI log | CI |
| WinMM backend | `@pytest.mark.windows_audio`, opens the GS synth and sends one note. Skipped when no device exists (CI runners) | Grace's machine |
| Packaged exe | `--self-test` in CI. Manual test matrix (below) per release candidate | CI + Grace |

Coverage target: ≥ 90% on `mapping`, `scales`, `config`, `scheduler`. No target for UI.

**Manual matrix (Grace):** Windows 11 23H2/24H2 × {single 1080p @100%, laptop 4K @150%/200%, dual monitor with secondary
on the left (negative X), mixed DPI}. Defender on, plus SmartScreen first-run, plus Bluetooth/USB audio switching.

---

## 9. Windows 11 risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **GS Wavetable Synth latency** (~30–80 ms+, worse on some drivers/Bluetooth) | The mapping feels laggy | Short attack instruments in the default sets. Document the latency. Device dropdown lets users choose a lower-latency output (VirtualMIDISynth, loopMIDI → a DAW, a hardware synth). We never add latency ourselves (no queueing). Investigate in-process synthesis (e.g. FluidSynth + a small SF2) only if testers say it's unusable — **out of scope for v0.1** |
| **MIDI device missing or unavailable** (GS synth removed in N/KN editions, held by another app, `midiOutGetNumDevs()==0`) | No sound, possible crash | Enumerate at startup. If no devices, show a clear message with a link to the README troubleshooting section and keep the app running. Open errors (`MMSYSERR_ALLOCATED` etc.) are shown in the status line, never thrown. Re-enumerate when the dropdown opens. Fall back to device 0 if the saved name is gone |
| **Audio endpoint change** (headphones unplugged) | GS synth may go silent | "Reconnect" action: close and reopen the device. Auto-reopen on Start |
| **SmartScreen "Windows protected your PC"** on an unsigned exe | Users think it's malware | README shows a screenshot of *More info → Run anyway*. Publish SHA256SUMS. Consistent publisher metadata in VERSIONINFO. Signing via Azure Trusted Signing is the path once there's budget |
| **AV false positives on PyInstaller onefile** | Exe quarantined | UPX off. Build the bootloader from the pinned PyInstaller version, never a random fork. No global hooks or keylogging APIs (polling `GetCursorPos` + `RegisterHotKey` only). Portable onedir zip as fallback. Submit each release to Microsoft's false-positive portal. Grace scans each RC with VirusTotal and records results in the release PR |
| **DPI scaling** (125–200% common on laptops) | With an unaware process `GetCursorPos` returns scaled coordinates, so the mapping is inconsistent across monitors and the Tk window is blurry | First thing in `__main__`: `SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)` with a fallback to `SetProcessDpiAwareness(2)`. Also set in the PyInstaller manifest. Then all coordinates and virtual-screen metrics are in physical pixels |
| **Multi-monitor coordinates** (negative origins, mixed sizes, gaps) | Clamping bugs, dead zones | Normalize against `SM_*VIRTUALSCREEN` (handles negatives). Clamp. Optional `primary` mode. Re-read metrics every 2 s and on `WM_DISPLAYCHANGE` so hot-plugging is handled. Gaps in the virtual rect just map to cells the cursor can't reach, which is acceptable and documented |
| **Stuck notes** after a crash or kill | Drone keeps playing | Silence on every exit path (`atexit`, top-level exception handler, `WM_ENDSESSION`). Killing the process closes the handle, and WinMM resets on close |
| **Multiple instances** | Doubled sound, settings races | Named mutex `Local\MouseMusicV2`. A second launch focuses the existing window (via a registered window message) and exits |
| **Timer resolution / CPU** | Jitter or battery drain | `timeBeginPeriod(1)` only while playing. Poll thread sleeps when stopped. Target < 2% CPU while playing |
| **Accessibility/annoyance** | Unexpected sound | Off by default. Global hotkey to stop. Volume control |

---

## 10. Task breakdown

Work order: S1–S3 → (S4, P1) → S5–S7 → P2–P4 → G1–G4. Each task is one PR to `main` with CI green.

### Sprite — dev & CI
- **S1 Scaffold & CI.** Repo layout per §3, `pyproject.toml`, pinned requirements, `.python-version`, ruff config,
  `ci.yml` (ruff + pytest on windows-latest and ubuntu-latest), dependabot.
  *AC:* `pytest` runs (even with 0 tests) and CI is green on both OSes. `python -m mousemusic --version` prints the version.
- **S2 Pure core.** `scales.py`, `instruments.py`, `mapping.py` (normalize, columns=notes, rows=programs, hysteresis).
  *AC:* unit tests for every scale and set; determinism; negative virtual origin; clamping; ≥ 90% coverage.
- **S3 Config.** `config.py`: dataclass, defaults per §4, APPDATA/portable resolution, validation and clamping, corrupt
  file → `.bak`, atomic debounced save.
  *AC:* tests for missing, corrupt, out-of-range and unknown keys; file round-trip equality.
- **S4 MIDI layer.** `MidiOut` protocol, `winmm.py` (enumerate/open/short_msg/reset/close, error mapping), `fake.py`,
  `--list-devices`.
  *AC:* on Windows, `--list-devices` shows "Microsoft GS Wavetable Synth" and the smoke test plays a note. Zero devices
  gives a friendly error, not a traceback.
- **S5 Scheduler + engine.** Note-on/off timing, program change ordering, 30 ms latest-wins rate limit, legato, silence
  paths, `timeBeginPeriod`, command queue, cursor and virtual-screen polling, DPI awareness.
  *AC:* fake-clock tests for every rule in §5. Idle CPU ≈ 0 when stopped, < 2% when playing. No stuck notes after
  Stop/Quit/device change.
- **S6 App shell.** Tk window (functional, unstyled), pystray tray, close-to-tray, single instance, global hotkey,
  logging, `--self-test`, `--dry-run`.
  *AC:* every control in §2 changes behaviour live and persists across restarts. A second instance focuses the first.
  Ctrl+Alt+M toggles playback while the app is unfocused.
- **S7 Packaging & release.** `mousemusic.spec` (onefile, windowed, icon, version info, DPI manifest, UPX off), onedir
  zip, `release.yml` on `v*.*.*`, self-test step, SHA256SUMS, optional signing placeholder.
  *AC:* pushing `v0.1.0-rc1` produces a Release with the exe, portable zip and checksums. The exe runs on a clean Win11
  VM with no Python installed and starts in < 3 s.

### Pragma — UX & README
- **P1 UX spec.** Wireframe of the window (≤ 360×300), labels, control order, tray menu, first-run tooltip, status line
  format, error messages (no device, device busy).
  *AC:* a `docs/ux.md` that Sprite can build S6 from without questions. Every error state has user-facing copy.
- **P2 Visual polish.** Icon (`assets/icon.ico`, 16–256 px, legible at 16 px), ttk theme/spacing, sensible tab order,
  keyboard access to every control.
  *AC:* looks crisp at 100%, 150% and 200% scaling. All controls reachable by keyboard.
- **P3 Instrument set & scale curation.** Listen-test the sets in §5 on the GS synth. Swap programs with slow attacks
  or bad loops for better ones. Confirm the default is pleasant.
  *AC:* `instruments.py` changes PR'd with a short rationale for each swap.
- **P4 README.** What it is (keep the sensory-substitution story), a GIF, download link, SmartScreen "Run anyway" steps
  with a screenshot, portable zip fallback, controls and hotkey, settings file location, troubleshooting (no sound, AV
  quarantine, latency → alternative synths), build-from-source, credits to v1.
  *AC:* a first-time user on Win11 gets from the README to sound in ≤ 2 minutes (verified by Grace in G3).

### Grace — QA
- **G1 Test plan.** `docs/test-plan.md`: the manual matrix (§8), risk-based cases from §9, release checklist.
  *AC:* reviewed by Archimedes. Every risk in §9 has at least one test case.
- **G2 Automated test review.** Review S2–S5 tests. Add missing edge cases (cursor exactly on boundary, 1-note range,
  single-row set, display hot-plug, rapid start/stop).
  *AC:* coverage targets met. At least 5 new edge-case tests merged.
- **G3 RC validation.** For each release candidate: clean Win11 VM install, SmartScreen flow, Defender scan +
  VirusTotal (record detections), DPI/multi-monitor matrix, stuck-note checks, 30-minute soak (CPU and memory flat),
  README walk-through timing.
  *AC:* signed-off checklist posted on the release PR. Blocking bugs filed as issues with repro steps.
- **G4 Latency & device report.** Measure perceived latency on the GS synth versus one alternative (e.g. VirtualMIDISynth).
  Test headphone unplug/replug and Bluetooth output.
  *AC:* short findings in an issue, with a recommendation on whether in-process synthesis is needed after v0.1.
