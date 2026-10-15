"""Taskbar snapshot pipeline (docs/design/cell-granularity.md §4.2, §4.2a; CG-S2). PURE.

Win32 geometry (``platform/win_taskbar.py``) and the UI Automation reader
(``platform/win_taskbar_uia.py``) feed raw data in; this module classifies UIA elements,
picks the slot source per taskbar, builds :class:`~mousemusic.mapping.TaskbarZone` s, and runs
the scan schedule (interval, backoff, timeout, failure fallback) with an injected clock.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from mousemusic.mapping import Rect, TaskbarZone, zone_fixed, zone_from_rects

log = logging.getLogger(__name__)

BOTTOM, TOP, LEFT, RIGHT = "bottom", "top", "left", "right"

# UIA class names (docs/taskbar-uia-notes.md §2). Matched on ClassName, AutomationId only as
# a hint (it isn't guaranteed stable across builds).
APP_CLASSES = frozenset({"Taskbar.TaskListButtonAutomationPeer"})
APP_IDS = frozenset({"StartButton", "SearchButton", "WidgetsButton", "TaskViewButton"})
APP_GENERIC_CLASSES = frozenset({"ToggleButton"})  # Start/Search/Task View on the frame
TRAY_PREFIX = "SystemTray."
#: A few px at the far right; silent rather than a slot (notes §2, decision for Sprite).
TRAY_SILENT_CLASSES = frozenset({"SystemTray.ShowDesktopButton"})

SOURCE_UIA, SOURCE_FIXED, SOURCE_NONE = "uia", "fixed", "none"


@dataclass(frozen=True)
class TaskbarInfo:
    """One taskbar window from Win32. ``monitor`` is the Windows display number."""

    hwnd: int
    rect: Rect
    edge: str
    monitor_rect: Rect
    scale: float
    primary: bool
    monitor: int = 1
    tray: Rect | None = None

    @property
    def axis(self) -> str:
        return "x" if self.edge in (BOTTOM, TOP) else "y"


@dataclass(frozen=True)
class Element:
    """A cached UIA element: ClassName, AutomationId, BoundingRectangle (physical px)."""

    class_name: str
    automation_id: str
    rect: Rect | None


def infer_edge(bar: Rect, monitor: Rect) -> str:
    """Which monitor edge a (secondary) taskbar touches; wide bars are bottom/top."""
    if bar.w >= bar.h:
        top_gap = abs(bar.y - monitor.y)
        bottom_gap = abs(monitor.y + monitor.h - (bar.y + bar.h))
        return TOP if top_gap < bottom_gap else BOTTOM
    left_gap = abs(bar.x - monitor.x)
    right_gap = abs(monitor.x + monitor.w - (bar.x + bar.w))
    return LEFT if left_gap <= right_gap else RIGHT


def _inside(r: Rect, bar: Rect) -> bool:
    cx, cy = r.x + r.w / 2, r.y + r.h / 2
    return bar.x <= cx < bar.x + bar.w and bar.y <= cy < bar.y + bar.h


def classify(elements: Sequence[Element], bar: Rect) -> tuple[list[Rect], list[Rect]]:
    """``(app_rects, tray_rects)``: visible, non-empty rects inside the bar, de-duplicated."""
    apps: list[Rect] = []
    tray: list[Rect] = []
    for e in elements:
        r = e.rect
        if r is None or not _inside(r, bar):
            continue
        name = e.class_name or ""
        if name.startswith(TRAY_PREFIX):
            if name not in TRAY_SILENT_CLASSES and r not in tray:
                tray.append(r)
        elif (
            name in APP_CLASSES or e.automation_id in APP_IDS or name in APP_GENERIC_CLASSES
        ) and r not in apps:
            apps.append(r)
    return apps, tray


@dataclass(frozen=True)
class ZoneOptions:
    slot_source: str = "auto"
    monitors: str = "all"
    tray: bool = True
    slot_dip: int = 44
    tray_slot_dip: int = 32
    offset_dip: int = 0

    @classmethod
    def from_settings(cls, s: object) -> ZoneOptions:
        return cls(
            slot_source=s.taskbar_slot_source, monitors=s.taskbar_monitors,  # type: ignore[attr-defined]
            tray=s.taskbar_tray, slot_dip=s.taskbar_slot_dip,  # type: ignore[attr-defined]
            tray_slot_dip=s.taskbar_tray_slot_dip, offset_dip=s.taskbar_offset_dip,  # type: ignore[attr-defined]
        )  # fmt: skip


def ordered(bars: Sequence[TaskbarInfo], monitors: str = "all") -> list[TaskbarInfo]:
    """Primary first, then secondaries by their monitor's (left, top) (§4.2a)."""
    prim = [b for b in bars if b.primary]
    if monitors == "primary":
        return prim[:1]
    rest = sorted(
        (b for b in bars if not b.primary), key=lambda b: (b.monitor_rect.x, b.monitor_rect.y)
    )
    return prim[:1] + rest


def zone_for(
    bar: TaskbarInfo, order: int, elements: Sequence[Element] | None, opts: ZoneOptions
) -> tuple[TaskbarZone | None, str]:
    """One taskbar's zone and the source used. ``elements`` None = UIA failed/not read."""
    tray = bar.tray if opts.tray else None
    if opts.slot_source != "fixed" and elements is not None:
        apps, trays = classify(elements, bar.rect)
        if apps or trays:
            return zone_from_rects(
                bar.rect, apps, trays if opts.tray else [], axis=bar.axis, order=order,
                monitor=bar.monitor,
            ), SOURCE_UIA  # fmt: skip
    if opts.slot_source == "uia":
        return None, SOURCE_NONE
    return zone_fixed(
        bar.rect, bar.scale, slot_dip=opts.slot_dip, offset_dip=opts.offset_dip, tray=tray,
        tray_slot_dip=opts.tray_slot_dip, axis=bar.axis, order=order, monitor=bar.monitor,
    ), SOURCE_FIXED  # fmt: skip


@dataclass(frozen=True)
class TaskbarSnapshot:
    """Immutable result of one scan; the engine swaps it in atomically (CG-S3)."""

    zones: tuple[TaskbarZone, ...] = ()
    sources: tuple[str, ...] = ()
    taken_at: float = 0.0
    duration_s: float = 0.0

    def describe(self) -> list[str]:
        """Lines for ``--self-test`` and the log: one per taskbar."""
        out = []
        for z, src in zip(self.zones, self.sources, strict=True):
            out.append(
                f"taskbar {z.monitor} ({'primary' if z.order == 0 else 'secondary'}): "
                f"source={src}, {len(z.app_slots)} app slot(s), {len(z.tray_slots)} tray slot(s)"
            )
        return out or ["no taskbar zone"]


# --- schedule -------------------------------------------------------------------------------

BASE_INTERVAL_S = 2.0
MAX_INTERVAL_S = 30.0
SLOW_SCAN_S = 0.150
TIMEOUT_S = 1.0
FAST_SCANS_TO_RECOVER = 3
FAILURES_TO_FALLBACK = 2
DEBOUNCE_S = 0.250


@dataclass
class ScanPolicy:
    """Interval with backoff: a scan over 150 ms doubles it (max 30 s); three fast scans in a
    row return it to 2 s."""

    interval: float = BASE_INTERVAL_S
    fast: int = 0

    def record(self, duration: float) -> float:
        if duration > SLOW_SCAN_S:
            self.interval = min(self.interval * 2, MAX_INTERVAL_S)
            self.fast = 0
        else:
            self.fast += 1
            if self.fast >= FAST_SCANS_TO_RECOVER:
                self.interval = BASE_INTERVAL_S
        return self.interval


@dataclass
class _BarState:
    failures: int = 0
    last: tuple[TaskbarZone | None, str] | None = None


Geometry = Callable[[], list[TaskbarInfo]]
Reader = Callable[[int], list[Element]]


@dataclass
class Scanner:
    """One scan = Win32 geometry + a UIA read per taskbar → :class:`TaskbarSnapshot`.

    Per taskbar, a UIA error or a read slower than :data:`TIMEOUT_S` keeps the previous zone;
    after :data:`FAILURES_TO_FALLBACK` in a row it uses the fixed slots (``auto``) or drops
    the zone (``uia``). ``fixed`` never calls the reader. Never raises."""

    geometry: Geometry
    reader: Reader | None
    clock: Callable[[], float] = time.monotonic
    opts: ZoneOptions = field(default_factory=ZoneOptions)
    policy: ScanPolicy = field(default_factory=ScanPolicy)
    snapshot: TaskbarSnapshot = field(default_factory=TaskbarSnapshot)
    _state: dict[int, _BarState] = field(default_factory=dict)

    def scan(self) -> TaskbarSnapshot:
        start = self.clock()
        try:
            bars = ordered(self.geometry(), self.opts.monitors)
        except Exception:
            log.debug("taskbar geometry failed", exc_info=True)
            bars = []
        zones: list[TaskbarZone] = []
        sources: list[str] = []
        seen: set[int] = set()
        for order, bar in enumerate(bars):
            seen.add(bar.hwnd)
            st = self._state.setdefault(bar.hwnd, _BarState())
            zone, src = self._one(bar, order, st)
            if zone is not None:
                zones.append(zone)
                sources.append(src)
        for hwnd in list(self._state):
            if hwnd not in seen:  # Explorer restart / taskbar gone
                del self._state[hwnd]
        duration = self.clock() - start
        self.policy.record(duration)
        log.debug("taskbar scan: %d zone(s) in %.1f ms", len(zones), duration * 1000)
        self.snapshot = TaskbarSnapshot(tuple(zones), tuple(sources), start, duration)
        return self.snapshot

    def _one(self, bar: TaskbarInfo, order: int, st: _BarState) -> tuple[TaskbarZone | None, str]:
        if self.opts.slot_source == "fixed" or self.reader is None:
            return zone_for(bar, order, None, self.opts)  # auto → fixed, uia → none
        t0 = self.clock()
        try:
            elements = self.reader(bar.hwnd)
            ok = self.clock() - t0 <= TIMEOUT_S
            if not ok:
                log.debug("UIA read of taskbar %s timed out", bar.monitor)
        except Exception:
            log.debug("UIA read of taskbar %s failed", bar.monitor, exc_info=True)
            ok, elements = False, []
        if ok:
            result = zone_for(bar, order, elements, self.opts)
            if result[1] == SOURCE_UIA:
                st.failures = 0
                st.last = result
                return result
        st.failures += 1
        if st.failures < FAILURES_TO_FALLBACK and st.last is not None:
            return st.last  # keep the previous snapshot for this taskbar
        return zone_for(bar, order, None, self.opts)


class ScanThread:
    """The long-lived ``taskbar-scan`` thread (§4.2a). Scans on :meth:`activate` (Start),
    every :attr:`ScanPolicy.interval` while active, and :data:`DEBOUNCE_S` after
    :meth:`refresh` (display/setting/DPI change, ``TaskbarCreated``). Never while inactive.
    ``on_snapshot`` receives each new :class:`TaskbarSnapshot`. ``setup`` runs on the thread
    first (COM MTA init on Windows)."""

    def __init__(
        self,
        scanner: Scanner,
        on_snapshot: Callable[[TaskbarSnapshot], None],
        *,
        setup: Callable[[], object] | None = None,
    ) -> None:
        self.scanner = scanner
        self.on_snapshot = on_snapshot
        self.setup = setup
        self._cond = threading.Condition()
        self._active = False
        self._due: float | None = None
        self._stop = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="taskbar-scan", daemon=True)
        self._thread.start()

    def activate(self, on: bool) -> None:
        with self._cond:
            self._active = on
            self._due = self.scanner.clock() if on else None
            self._cond.notify()

    def refresh(self) -> None:
        with self._cond:
            if self._active:
                self._due = self.scanner.clock() + DEBOUNCE_S
                self._cond.notify()

    def set_options(self, opts: ZoneOptions) -> None:
        with self._cond:
            self.scanner.opts = opts
        self.refresh()

    def stop(self, timeout: float = 2.0) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify()
        if self._thread is not None:
            self._thread.join(timeout)

    def next_wait(self) -> float | None:
        """Seconds until the next scan; None = wait for a notify. Caller holds the lock."""
        if not self._active or self._due is None:
            return None
        return max(0.0, self._due - self.scanner.clock())

    def step(self) -> bool:
        """Scan if due (called with the lock released). Returns True if it scanned."""
        with self._cond:
            wait = self.next_wait()
            if wait is None or wait > 0:
                return False
            self._due = None
        snap = self.scanner.scan()
        with self._cond:
            if self._active and self._due is None:
                self._due = self.scanner.clock() + self.scanner.policy.interval
        try:
            self.on_snapshot(snap)
        except Exception:
            log.exception("taskbar snapshot callback failed")
        return True

    def _run(self) -> None:
        if self.setup is not None:
            try:
                self.setup()
            except Exception:
                log.exception("taskbar-scan setup failed")
        while True:
            with self._cond:
                if self._stop:
                    return
                wait = self.next_wait()
                if wait is None or wait > 0:
                    self._cond.wait(wait)
                    continue
            self.step()
