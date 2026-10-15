# Windows 11 taskbar and tray: UI Automation notes (CG-G2)

Owner: Grace · For: `platform/win_taskbar_uia.py` (CG-S2), design `docs/design/cell-granularity.md` §4.2/§4.2a.
**Desk research only.** Nothing here has been checked on a real machine yet. It all comes from public docs and code,
and every claim has a link. Confidence: **High** = Microsoft docs, or the same value in two or more independent sources.
**Medium** = one solid source (code that relies on it). **Low** = a single anecdote, or inferred.

Windhawk sources are pinned at commit `d4ee5f6` of [ramensoftware/windhawk-mods](https://github.com/ramensoftware/windhawk-mods/blob/d4ee5f65a63f19962d025831b57cde6d010d9de9/mods/).

## 1. Window (HWND) layer

| Item | Value | Versions | Confidence | Source |
|---|---|---|---|---|
| Primary taskbar | top-level window class `Shell_TrayWnd` | all Win11 | High | Win32 HWND dump in [SO 79219443](https://stackoverflow.com/questions/79219443/how-to-get-system-tray-information-in-python); [moudey/Shell Main.cpp](https://github.com/moudey/Shell/blob/81ec1a41/src/dll/src/Main.cpp) |
| Secondary taskbars | `Shell_SecondaryTrayWnd`, one per extra monitor with "Show my taskbar on all displays" | all Win11 | High | [Windhawk taskbar styler, L17840](https://github.com/ramensoftware/windhawk-mods/blob/d4ee5f65a63f19962d025831b57cde6d010d9de9/mods/windows-11-taskbar-styler.wh.cpp#L17840); [moudey/Shell `is_secondary`](https://github.com/moudey/Shell/blob/81ec1a41/src/dll/src/Main.cpp) |
| Legacy tray child | `TrayNotifyWnd` child of `Shell_TrayWnd` still exists | 22H2+ (seen in a 2024 dump) | Medium | [SO 79219443](https://stackoverflow.com/questions/79219443/how-to-get-system-tray-information-in-python) |
| XAML host child | `Windows.UI.Composition.DesktopWindowContentBridge` → `Windows.UI.Input.InputSite.WindowClass`. The XAML content (taskbar frame and tray) hangs under these | 22H2+ | Medium | [Windhawk taskbar styler, L20099](https://github.com/ramensoftware/windhawk-mods/blob/d4ee5f65a63f19962d025831b57cde6d010d9de9/mods/windows-11-taskbar-styler.wh.cpp#L20099); [HideTaskbar #5](https://github.com/Lonely-Atom/HideTaskbar/issues/5); [SPlayer uia.rs](https://github.com/imsyy/SPlayer/blob/38491618/native/taskbar-lyric/src/uia.rs) (iterates bridge children, then `FindAll`) |
| Hidden-icons flyout | separate top-level window `TopLevelWindowForOverflowXamlIsland`. It exists/shows only while the chevron is open | Win11 (version not stated) | Low | [HideTaskbar #5](https://github.com/Lonely-Atom/HideTaskbar/issues/5) (a single user report) |
| Explorer restart | Explorer broadcasts the registered message `TaskbarCreated` when the taskbar is recreated. All the HWNDs above are new | documented | High | [Microsoft: The Taskbar → Taskbar Creation Notification](https://learn.microsoft.com/en-us/windows/win32/shell/taskbar) |

## 2. UI Automation layer (ClassName / AutomationId)

| Element | UIA ClassName | AutomationId | Notes | Confidence | Sources |
|---|---|---|---|---|---|
| Taskbar frame (XAML root under the bridge) | `Taskbar.TaskbarFrameAutomationPeer` | `TaskbarFrame` | Parent of the Start/Search/app buttons | High | [moudey/Shell](https://github.com/moudey/Shell/blob/81ec1a41/src/dll/src/Main.cpp) (comment dump, 2023); [SO 79219443](https://stackoverflow.com/questions/79219443/how-to-get-system-tray-information-in-python); [HideTaskbar #5](https://github.com/Lonely-Atom/HideTaskbar/issues/5) |
| App buttons (pinned/running) | `Taskbar.TaskListButtonAutomationPeer` | per-app, described as stable | One element per button. The basis for app slots | High | [SPlayer uia.rs](https://github.com/imsyy/SPlayer/blob/38491618/native/taskbar-lyric/src/uia.rs); [WinGlide README](https://github.com/congchuahiep/WinGlide/blob/main/README.md); TaskbarVolume author ([Reddit](https://www.reddit.com/r/coolgithubprojects/comments/1vp7s9h/c_taskbarvolume_scroll_on_a_windows_11_taskbar/), "Windows 11 22H2+") |
| Start | `ToggleButton` | `StartButton` | | High | [moudey/Shell](https://github.com/moudey/Shell/blob/81ec1a41/src/dll/src/Main.cpp); [SPlayer](https://github.com/imsyy/SPlayer/blob/38491618/native/taskbar-lyric/src/uia.rs) |
| Search | `ToggleButton` (the search **box** variant has a `TextBlock`, id `SearchBoxTextBlock`) | `SearchButton` | The box variant is wider than one slot | High / Medium | same two sources |
| Widgets | ? | `WidgetsButton` | ClassName not given in the sources | Medium | [SPlayer](https://github.com/imsyy/SPlayer/blob/38491618/native/taskbar-lyric/src/uia.rs) |
| Task View | `ToggleButton` (Name "Task View") | not given | | Medium | [SO 79219443](https://stackoverflow.com/questions/79219443/how-to-get-system-tray-information-in-python) |
| Tray icons | `SystemTray.NormalButton` | `SystemTrayIcon` | Shared by **all** tray items, so the AutomationId doesn't distinguish them | High | [SO 79219443](https://stackoverflow.com/questions/79219443/how-to-get-system-tray-information-in-python); [NVDA #18941 log](https://github.com/nvaccess/nvda/issues/18941); [Seelen-UI tray](https://github.com/eythaann/Seelen-UI/blob/9be711b9/src/background/modules/tray/application.rs) |
| Overflow chevron ("Show Hidden Icons") | `SystemTray.NormalButton` | `SystemTrayIcon` | Same class/id as the icons. Only Name (localized) or position tells it apart | High | [NVDA #18941](https://github.com/nvaccess/nvda/issues/18941); [Seelen-UI](https://github.com/eythaann/Seelen-UI/blob/9be711b9/src/background/modules/tray/application.rs); [moudey/Shell](https://github.com/moudey/Shell/blob/81ec1a41/src/dll/src/Main.cpp) |
| Network/volume/battery group | `SystemTray.AccentButton` | `SystemTrayIcon` | Quick Settings group (one element for several glyphs) | Medium | [moudey/Shell](https://github.com/moudey/Shell/blob/81ec1a41/src/dll/src/Main.cpp) |
| Clock | `SystemTray.OmniButton` (2023 dump) / `SystemTray.OmniButtonLeft` (2024 dump) | `SystemTrayIcon` | Varies by build. Match the `SystemTray.OmniButton*` prefix. On **secondary** taskbars the clock is an `OmniButton` too | Medium | [moudey/Shell](https://github.com/moudey/Shell/blob/81ec1a41/src/dll/src/Main.cpp); [SO 79219443](https://stackoverflow.com/questions/79219443/how-to-get-system-tray-information-in-python) |
| Notifications bell | `SystemTray.AccentButton` (2024 dump) | `SystemTrayIcon` | | Low | [SO 79219443](https://stackoverflow.com/questions/79219443/how-to-get-system-tray-information-in-python) |
| Show desktop sliver | `SystemTray.ShowDesktopButton` | `SystemTrayIcon` | A few px wide at the far right. Treat as silent, or merge into the clock slot (decision for Sprite) | Medium | [moudey/Shell](https://github.com/moudey/Shell/blob/81ec1a41/src/dll/src/Main.cpp); [SO 79219443](https://stackoverflow.com/questions/79219443/how-to-get-system-tray-information-in-python) |

**XAML type names aren't UIA class names.** Windhawk mods address the *XAML visual tree*: `Taskbar.TaskListButton`,
`Taskbar.TaskbarFrame`, `SystemTray.NotifyIconView`, `SystemTray.ChevronIconView`, `SystemTray.OmniButton`,
`SystemTray.SystemTrayFrame` (e.g. [taskbar styler](https://github.com/ramensoftware/windhawk-mods/blob/d4ee5f65a63f19962d025831b57cde6d010d9de9/mods/windows-11-taskbar-styler.wh.cpp),
[tray icon spacing](https://github.com/ramensoftware/windhawk-mods/blob/d4ee5f65a63f19962d025831b57cde6d010d9de9/mods/taskbar-notification-icon-spacing.wh.cpp)). UIA reports the **automation peer** class instead
(`…AutomationPeer`, or a generic `SystemTray.NormalButton`), so the chevron vs. icon distinction that XAML has
(`ChevronIconView` vs. `NotifyIconView`) **isn't visible through UIA** in any source found. Confidence: Medium (inferred from the dumps above).

Hierarchy (stock 22H2–24H2, from [SO 79219443](https://stackoverflow.com/questions/79219443/how-to-get-system-tray-information-in-python) and [HideTaskbar #5](https://github.com/Lonely-Atom/HideTaskbar/issues/5)):

```
Shell_TrayWnd (Win32)
├─ TrayNotifyWnd (Win32, legacy)
└─ Windows.UI.Composition.DesktopWindowContentBridge → Windows.UI.Input.InputSite.WindowClass (Win32)
   └─ Taskbar.TaskbarFrameAutomationPeer  [id TaskbarFrame]
      ├─ ToggleButton Start [StartButton] · Search [SearchButton] · Task View · (Widgets [WidgetsButton])
      └─ Taskbar.TaskListButtonAutomationPeer × N
   SystemTray.NormalButton "Show Hidden Icons" [SystemTrayIcon]   ← tray elements are siblings at the same level
   SystemTray.NormalButton × M (tray icons) [SystemTrayIcon]
   SystemTray.AccentButton (network/volume) · SystemTray.OmniButton* (clock) · SystemTray.ShowDesktopButton
```
The exact nesting depth differs between sources (`Level 2` vs. `3`), so the reader should use `TreeScope_Descendants` from
the taskbar HWND and match on ClassName, as the design already says, not on a fixed path. Confidence: Medium.

## 3. Sizes (documented defaults, not measured)

| Metric | Value (DIP at 100 %) | Confidence | Source |
|---|---|---|---|
| Taskbar height | 48 | High (Windhawk mod docs label it "Windows 11 default") | [taskbar-icon-size L37/L60](https://github.com/ramensoftware/windhawk-mods/blob/d4ee5f65a63f19962d025831b57cde6d010d9de9/mods/taskbar-icon-size.wh.cpp#L60) |
| App icon | 24 × 24 | High | [taskbar-icon-size L64](https://github.com/ramensoftware/windhawk-mods/blob/d4ee5f65a63f19962d025831b57cde6d010d9de9/mods/taskbar-icon-size.wh.cpp#L64) |
| **App button width** | **44** | High | [taskbar-icon-size L65–68](https://github.com/ramensoftware/windhawk-mods/blob/d4ee5f65a63f19962d025831b57cde6d010d9de9/mods/taskbar-icon-size.wh.cpp#L68) |
| Small button width / small icon | 32 / 16 | Medium | [taskbar-icon-size L72–79](https://github.com/ramensoftware/windhawk-mods/blob/d4ee5f65a63f19962d025831b57cde6d010d9de9/mods/taskbar-icon-size.wh.cpp#L79) |
| **Tray icon width** | **32** | High (mod doc, plus a screenshot labelled "Windows 11 default") | [tray icon spacing L33–58](https://github.com/ramensoftware/windhawk-mods/blob/d4ee5f65a63f19962d025831b57cde6d010d9de9/mods/taskbar-notification-icon-spacing.wh.cpp#L58) |
| Overflow flyout icon width | 32 | Medium | [tray icon spacing L104](https://github.com/ramensoftware/windhawk-mods/blob/d4ee5f65a63f19962d025831b57cde6d010d9de9/mods/taskbar-notification-icon-spacing.wh.cpp#L104) |

- **Spacing between app buttons** isn't documented anywhere I found. The design's 48 DIP pitch is 44 + an assumed 4. **Unverified.**
- **At 125/150/200 %** the expected values are DIP × scale (44 → 55/66/88; 32 → 40/48/64; 48 → 60/72/96). That's an inference from XAML layout being in effective pixels, **not a measurement**.
- **Microsoft doesn't document** taskbar button or tray widths in any Learn page found.

These can't replace CG-G2's screenshot measurement. With UIA as the primary source, they only matter for the
`fixed` fallback (`taskbar_slot_dip` → suggest **44**, `taskbar_tray_slot_dip` **32**, pending measurement).

## 4. Rectangles and DPI

- `BoundingRectangle` is "expressed in **physical screen coordinates**", and it's NULL/empty when the item isn't showing.
  High. [Microsoft: Automation Element Property Identifiers](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-automation-element-propids).
- Physical vs. virtualized: Windows virtualizes coordinates for DPI-**unaware** processes. MouseMusic is per-monitor-v2 aware
  (manifest + `SetProcessDpiAwarenessContext`), so UIA rects and `GetCursorPos` share one physical space. High.
  [Microsoft: High DPI desktop app development](https://learn.microsoft.com/en-us/windows/win32/hidpi/high-dpi-desktop-application-development-on-windows).
  TB-35 checks this on mixed DPI.
- `IsOffscreen` is the documented way to drop collapsed or scrolled-out items. It isn't affected by occlusion. High. [same propids page](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-automation-element-propids).
- `AutomationId` "is not guaranteed to be stable across different releases or builds", and clients "should make no
  assumptions" about other apps' IDs. That's why matching should prefer ClassName, with AutomationId as a secondary hint. High. [same page](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-automation-element-propids).
- One cross-process round-trip per taskbar via a CacheRequest is the documented pattern. High. [Microsoft: Caching UI Automation properties](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-cachingforclients).
- Stale elements after an Explorer restart: elements of a destroyed provider fail with `UIA_E_ELEMENTNOTAVAILABLE`. Medium
  (stated for providers that destroy elements in the propids page `OptimizeForVisualContent` entry; generalising it to a process exit is an inference).

## 5. Version notes

- **21H2**: the tray was a different implementation. Windhawk tray mods support "22H2 or newer" only. Low-medium. [tray icon spacing L30](https://github.com/ramensoftware/windhawk-mods/blob/d4ee5f65a63f19962d025831b57cde6d010d9de9/mods/taskbar-notification-icon-spacing.wh.cpp#L30).
- **22H2 → 24H2**: the TaskListButton peer is used by tools that claim 22H2+. Clock class differs between dumps (`OmniButton` 2023, `OmniButtonLeft` 2024).
- **24H2**: some internal taskbar symbols are "Gone in Windows 11 version 24H2" (affects mods that hook internals, not UIA). [taskbar-icon-size L2687](https://github.com/ramensoftware/windhawk-mods/blob/d4ee5f65a63f19962d025831b57cde6d010d9de9/mods/taskbar-icon-size.wh.cpp#L2687).
- **Native vertical taskbar** (newer builds): Windhawk notes that tray width becomes tray height there. Axis handling (§CG-4.2) must cover it. Low. [tray icon spacing readme](https://github.com/ramensoftware/windhawk-mods/blob/d4ee5f65a63f19962d025831b57cde6d010d9de9/mods/taskbar-notification-icon-spacing.wh.cpp#L39).

## 6. Gaps and pending

1. **Not verified on hardware.** A UIA dump with Accessibility Insights or Inspect on stock 23H2 **and** 24H2, primary and secondary taskbars, is still needed.
2. **Pending: Christopher's Windhawk setup.** Which mods and versions, and does UIA report the resized rects? Windhawk resizes XAML elements, so the peers' BoundingRectangles *should* follow, but that's unverified. He hasn't been contacted.
3. Chevron vs. icon can't be told apart by ClassName/AutomationId. Use position (left-most `SystemTray.NormalButton`) or Name (localized), or treat it as just another slot (recommended: it's a visible button anyway).
4. Secondary-taskbar tray contents beyond the clock (24H2 can show tray icons on all taskbars, depending on settings): unverified.
5. Widgets ClassName and the search-box variant's width: unverified.
6. App-button spacing (44 vs. 48 pitch): unverified. Only matters for `fixed`.
