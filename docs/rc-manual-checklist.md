# RC manual checklist (Windows 11, about 10 min)

For Christopher, on each release candidate. Grace's full plan is in [`test-plan.md`](test-plan.md); IDs in brackets
point there. No VirusTotal, no killing the app or Explorer, and no hunting for instruments: Grace covers those in her
own run (SD-06, SN-07, TB-15/17).

Before you start: download the `.exe` from the release page in Edge. If a step fails, write down what you saw and move on.
At the end, note the Windows build and your display setup.

| # | ~Time | Step | Pass if |
|---|---|---|---|
| 1 | 1 min | **SmartScreen, no console flash.** Double-click the exe, then *More info → Run anyway*. [SD-01] | Window and tray icon appear. **No** black console window flashes. No sound before Start. |
| 2 | 30 s | **Defender.** Right-click the exe → *Scan with Microsoft Defender*. [SD-04] | "No current threats". |
| 3 | 30 s | **Self-test.** In cmd, in the download folder: `MouseMusic-vX.Y.Z-win64.exe --self-test \| more` [MD-04, HW-32.1] | `PASS` lines, including `PASS taskbar … source=uia` with about one app slot per taskbar icon. No traceback. |
| 4 | 1 min | **Preview.** With the app stopped, click **Preview** next to *Instruments*. Pick *Mellow* and click Preview again. Then set it back to *Classic*. [ux 4b] | A short scale plays each time and then stops by itself. Preview is greyed out while it plays. |
| 5 | 1 min | **One note, then silence.** Click **Start** and move the mouse left→right across the screen. Tick **Hold notes**, keep the mouse still so a note keeps sounding, then click **Stop**. [SN-01] | Notes rise left→right. Stop goes silent **immediately**, with no hanging note. |
| 6 | 1.5 min | **Taskbar notes on and off.** Start, tick **Taskbar notes**, and slowly hover your taskbar icons left→right, then the tray icons and the clock. Move back up onto the desktop. Untick it and hover the taskbar again. [HW-33.1/2, TB-22] | **On:** each icon gives its own rising note, the status reads `… · Taskbar k · Xylophone` (or `Tray k` with notes falling from the clock), and back on the desktop the normal instrument returns right away. On your second monitor (if its taskbar is shown) the status says `Taskbar 2/k · Celesta`. **Off:** the taskbar plays like the rest of the screen. Click Stop. |
| 7 | 1 min | **Hotkey fallback (W7).** Ctrl+Alt+M is already taken on your PC, so just Quit from the tray and start the exe again. ✕ to the tray, then press Ctrl+Alt+Shift+M twice. [SD-13] | Amber W7 says the shortcut is Ctrl+Alt+Shift+M. Pressing it starts and stops playback with the window hidden. |
| 8 | 1.5 min | **Both shortcuts taken (W4).** Quit from the tray. In PowerShell (leave this window open):<br>`Add-Type -Name H -Namespace W -MemberDefinition '[DllImport("user32.dll")] public static extern bool RegisterHotKey(IntPtr h,int id,uint m,uint vk);'`<br>`[W.H]::RegisterHotKey([IntPtr]::Zero,1,7,0x4D)` (prints `True`)<br>Start the app again, then close the PowerShell window. [SD-13, HW-30.1] | The W4 text ("…so the shortcut is off. Use the Start button.") is fully readable, wrapped, nothing cut off. The hint reads `(shortcut off)`. |
| 9 | 1.5 min | **DPI + monitors.** Set display scaling to 150 % (Settings → Display). In Task Manager → Details, add the **DPI awareness** column. Drag the window between your monitors. [DM-06, DM-14, HW-33.7] | `Per-Monitor (v2)`. The window is crisp. Row 7 shows both `Hold notes (legato)` and `Taskbar notes` in full. Set scaling back afterwards. |
| 10 | 30 s | **Dark mode.** Pick *Dark* in the **Theme** row, then *System*. [TH-06] | The window and title bar switch to dark and back right away. |
| 11 | 1 min (optional) | **Narrator.** Ctrl+Win+Enter to turn on Narrator. Click Start, then Stop. Ctrl+Win+Enter to turn it off. [SR-04, HW-30.4] | Narrator reads the new status ("Playing…", "Stopped…") once each. |

Total ≈ 10 min (≈ 9 without Narrator).

## Not in this checklist, and why
- VirusTotal, the portable zip, sleep and wake, unplugging MIDI devices, hard kills and Explorer restarts are in Grace's G3 run and the automated tests (SD-06, SD-10, SN-07, SN-09, MD-09/10, TB-15).
- Specific instruments: Preview plays each set's first instrument in one click. To hear any GM program directly, `MouseMusic.exe --play-instrument 105` (Banjo) also works, but it isn't needed for sign-off.
