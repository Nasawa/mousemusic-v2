# RC manual checklist (Windows 11, under 10 min)

For Christopher, run on each release candidate. Grace's full plan is in [`test-plan.md`](test-plan.md); IDs in brackets
point there. VirusTotal is **not** part of this checklist (Grace runs SD-06 separately).

Before you start: download the `.exe` and the portable `.zip` from the release page in Edge. Have a PowerShell window open.
Record Windows build + display setup at the end. If a step fails, note what you saw and move on.

| # | ~Time | Step | Pass if |
|---|---|---|---|
| 1 | 1 min | **SmartScreen + no console flash.** Double-click the exe. *More info → Run anyway*. [SD-01] | SmartScreen dialog has *Run anyway*; window + tray icon appear; **no** black console window flashes; no sound before Start. |
| 2 | 30 s | **Defender.** Right-click the exe → *Scan with Microsoft Defender*; same for the zip. [SD-04/05, §11 A-8] | "No current threats" for both. |
| 3 | 30 s | **Self-test.** In cmd, in the download folder: `MouseMusic-vX.Y.Z-win64.exe --self-test \| more` [MD-04] | `PASS` for bundle, settings, mapping, midi (≥ 1 device). No traceback, no window. |
| 4 | 2 min | **The one audio step.** Click **Start** with the default *Classic* set. Move left→right across the top: notes rise. Move to the **bottom edge**: status reads `… · Banjo` — listen 2 s. Pick **Mellow** in *Instrument*, stay at the bottom edge: `… · Pad 1 (new age)` — listen 2 s. Tick **Legato**, hold still (note sustains), click **Stop**. [SN-01, P3 listen test] | Clear notes; pitch rises left→right; Banjo and New Age Pad are acceptable (if not, say which one is harsh); **silence immediately** on Stop (no hanging note). |
| 5 | 1 min | **Hotkey, fallback (W7).** Ctrl+Alt+M is already taken on your PC, so just relaunch the app (tray → Quit, then start the exe again). [SD-13, PR #19 check 1] | Amber W7: *"Ctrl+Alt+M is in use by another app, so the shortcut is Ctrl+Alt+Shift+M instead."* Hint and stopped status show `Ctrl+Alt+Shift+M`; pressing it toggles Start/Stop with the window **hidden** (✕ to tray first). |
| 6 | 1.5 min | **Hotkey, both taken (W4).** Quit the app. In PowerShell, take the fallback too and leave the window open:<br>`Add-Type -Name H -Namespace W -MemberDefinition '[DllImport("user32.dll")] public static extern bool RegisterHotKey(IntPtr h,int id,uint m,uint vk);'`<br>`[W.H]::RegisterHotKey([IntPtr]::Zero,1,7,0x4D)` (prints `True`).<br>Start the app. Then set Windows scaling to 150 % (Settings → Display) and look again. Close PowerShell afterwards. [SD-13, PR #19 check 2] | W4 *"Ctrl+Alt+M and Ctrl+Alt+Shift+M are in use by other apps, so the shortcut is off. Use the Start button."* is **fully visible, wrapped, nothing cut off** at 100 % and 150 %; hint reads `(shortcut off)`; app otherwise works. |
| 7 | 1 min | **Shortcut picker.** Pick `Ctrl+Alt+P` in *Shortcut*. ✕ to tray, press Ctrl+Alt+P. Quit, relaunch. [SD-15, PR #19 check 3] | Works immediately while hidden; still `Ctrl+Alt+P` after restart. Set it back afterwards if you want. |
| 8 | 1.5 min | **DPI + monitors** (still at 150 %). Task Manager → Details → right-click a column header → *Select columns* → **DPI awareness**. With the app stopped, use `--dry-run` only if you want silence; otherwise glance at the status line while sweeping the mouse across **all** monitors. If you have a 2nd monitor, place it **left** of the main one in Display settings. Drag the window between monitors. [DM-06/07/09, DM-14] | `Per-Monitor (v2)`; window crisp and not clipped; status note goes lowest at the far left of the leftmost monitor and highest at the far right; no dead strip. Set scaling back to normal after. |
| 9 | 1 min | **Dark mode.** Settings → Personalization → Colors → *Dark*, with the app open; then back to *Light*. If the build has a **Theme** row: also pick *Dark* there while Windows is Light, and relaunch. [TH-04/05/06/08/09] | App window (and title bar) follows Windows live without a restart; dropdown lists readable in dark; the Theme override wins and persists; tray menu staying light is expected. *If the build has no Theme row and doesn't follow Windows, record "dark mode not in this build".* |
| 10 | 30 s | **Window size.** With a short status, look at the window; then trigger W4 again or recall step 6. [WS-01/02] | Window is about 340 wide and tall enough for all rows (Shortcut and Theme visible); grows for the long warning and shrinks back after it clears. |

Total ≈ 9.5 min.

## Dropped from the rc2 list, and why
- VirusTotal: Grace runs it (SD-06).
- Separate stuck-note kill/quit, E2/E4 device, sleep, single-instance, persistence, and portable-zip steps: steps 1–4 and 15 passed on rc2, and these are covered by automated tests (SN-01/05/11, MD-09a, SN-09c) or Grace's G3 run. Run them only if the build changes that area.

## Known limitation
There's no `--play-instrument N` flag, preset or demo mode in the app (main at 54ba2fe: CLI flags are `--version`,
`--self-test`, `--dry-run`, `--list-devices`, `--portable`, `--log-level`). Step 4 therefore uses the real mechanism:
both instruments are the **bottom row** of a curated set (Banjo 105 = Classic, Pad 1 (new age) 88 = Mellow), so it's one
dropdown pick and a move to the bottom edge. A one-click audition flag would need to be added (test-plan B-5).
