"""Cursor position -> cell -> (note, program). PURE: no I/O, no platform imports.

See ARCHITECTURE.md §5. Columns are notes, rows are instruments, both evenly sized across the
screen rect (normally the virtual desktop, which may have a negative origin).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from mousemusic.instruments import get_instrument_set
from mousemusic.scales import scale_notes

#: Physical pixels the cursor must travel past a cell boundary before the cell changes.
HYSTERESIS_PX = 2


@dataclass(frozen=True)
class Rect:
    """Screen rectangle in physical pixels: origin (x, y), size (w, h). Origin may be negative."""

    x: int
    y: int
    w: int
    h: int

    def __post_init__(self) -> None:
        if self.w <= 0 or self.h <= 0:
            raise ValueError(f"rect must have positive size, got {self.w}x{self.h}")


@dataclass(frozen=True)
class Cell:
    col: int
    row: int


@dataclass(frozen=True)
class Grid:
    """The allowed notes (columns, left -> right) and programs (rows, top -> bottom)."""

    notes: tuple[int, ...]
    programs: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.notes:
            raise ValueError("grid needs at least one note (empty scale/range)")
        if not self.programs:
            raise ValueError("grid needs at least one program")

    @property
    def cols(self) -> int:
        return len(self.notes)

    @property
    def rows(self) -> int:
        return len(self.programs)

    def sound(self, cell: Cell) -> tuple[int, int]:
        """``(note, program)`` for a cell."""
        return self.notes[cell.col], self.programs[cell.row]


def build_grid(scale: str, root: str, low_note: int, high_note: int, instrument_set: str) -> Grid:
    return Grid(
        notes=scale_notes(scale, root, low_note, high_note),
        programs=get_instrument_set(instrument_set).programs,
    )


def _unit(value: float) -> float:
    """Clamp to [0, 1)."""
    if value < 0.0 or math.isnan(value):
        return 0.0
    if value >= 1.0:
        return math.nextafter(1.0, 0.0)
    return value


def normalize(x: float, y: float, rect: Rect) -> tuple[float, float]:
    """``(u, v)`` in [0, 1) relative to ``rect``; positions outside it are clamped."""
    return _unit((x - rect.x) / rect.w), _unit((y - rect.y) / rect.h)


def _index(t: float, n: int) -> int:
    return min(int(t * n), n - 1)


def cell_at(x: float, y: float, rect: Rect, grid: Grid) -> Cell:
    """The cell under ``(x, y)``. Same inputs always give the same cell."""
    u, v = normalize(x, y, rect)
    return Cell(_index(u, grid.cols), _index(v, grid.rows))


def map_position(x: float, y: float, rect: Rect, grid: Grid) -> tuple[int, int]:
    """``(note, program)`` for a cursor position, without hysteresis."""
    return grid.sound(cell_at(x, y, rect, grid))


def _past_boundary(pos: float, origin: int, size: int, n: int, idx: int, margin: float) -> bool:
    """True if ``pos`` is at least ``margin`` px outside cell ``idx`` along one axis."""
    lo = origin + idx * size / n
    hi = origin + (idx + 1) * size / n
    return pos >= hi + margin or pos <= lo - margin


class HysteresisMapper:
    """Wraps :func:`cell_at` so a cell change only registers once the cursor is at least
    ``margin_px`` past the boundary. Each axis is handled independently."""

    def __init__(self, grid: Grid, rect: Rect, margin_px: float = HYSTERESIS_PX) -> None:
        if margin_px < 0:
            raise ValueError("margin_px must be >= 0")
        self.grid = grid
        self.rect = rect
        self.margin_px = margin_px
        self.cell: Cell | None = None

    def reset(self, grid: Grid | None = None, rect: Rect | None = None) -> None:
        """Forget the current cell, optionally switching grid (settings) or rect (display)."""
        if grid is not None:
            self.grid = grid
        if rect is not None:
            self.rect = rect
        self.cell = None

    def update(self, x: float, y: float) -> Cell:
        raw = cell_at(x, y, self.rect, self.grid)
        prev = self.cell
        if prev is None:
            self.cell = raw
            return raw
        r, g, m = self.rect, self.grid, self.margin_px
        cx = min(max(x, r.x), r.x + r.w)
        cy = min(max(y, r.y), r.y + r.h)
        col = prev.col
        if raw.col != prev.col and _past_boundary(cx, r.x, r.w, g.cols, prev.col, m):
            col = raw.col
        row = prev.row
        if raw.row != prev.row and _past_boundary(cy, r.y, r.h, g.rows, prev.row, m):
            row = raw.row
        self.cell = Cell(col, row)
        return self.cell


# --- taskbar zones (docs/design/cell-granularity.md §4.2-§4.3, CG-S1) ----------------------
#
# Pure data: CG-S2 builds zones from Win32/UI Automation, CG-S3 wires them into the engine.
# Positions are physical px (the same space as GetCursorPos). Slots are half-open intervals
# ``(start, end)`` along the bar's axis.

APPS, TRAY = "apps", "tray"
WRAP_VELOCITY_FACTOR = 0.7
Interval = tuple[int, int]


def _contains(r: Rect, x: float, y: float) -> bool:
    return r.x <= x < r.x + r.w and r.y <= y < r.y + r.h


def slot_px(dip: int, scale: float) -> int:
    """Physical slot width for a DIP pitch on a monitor at ``scale`` (DPI / 96)."""
    return max(1, round(dip * scale))


def fixed_slots(
    start: int, end: int, width: int, *, from_end: bool = False
) -> tuple[Interval, ...]:
    """Equal slots of ``width`` filling ``[start, end)``, a partial last slot included.
    ``from_end`` anchors them at ``end`` (tray). Always sorted ascending."""
    if width <= 0 or end <= start:
        return ()
    out: list[Interval] = []
    if from_end:
        hi = end
        while hi > start:
            out.append((max(start, hi - width), hi))
            hi -= width
        return tuple(reversed(out))
    lo = start
    while lo < end:
        out.append((lo, min(end, lo + width)))
        lo += width
    return tuple(out)


@dataclass(frozen=True)
class TaskbarZone:
    """One taskbar. ``order`` 0 = primary, 1.. = secondaries sorted by monitor (left, top);
    ``monitor`` is the Windows display number shown to the user. ``axis`` is ``"x"`` for
    bottom/top bars, ``"y"`` for left/right ones."""

    rect: Rect
    axis: str = "x"
    order: int = 0
    monitor: int = 1
    app_slots: tuple[Interval, ...] = ()
    tray: Rect | None = None
    tray_slots: tuple[Interval, ...] = ()

    def along(self, x: float, y: float) -> float:
        return x if self.axis == "x" else y

    def span(self, r: Rect) -> Interval:
        return (r.x, r.x + r.w) if self.axis == "x" else (r.y, r.y + r.h)


def zone_fixed(
    rect: Rect,
    scale: float,
    *,
    slot_dip: int,
    offset_dip: int = 0,
    tray: Rect | None = None,
    tray_slot_dip: int = 32,
    axis: str = "x",
    order: int = 0,
    monitor: int = 1,
) -> TaskbarZone:
    """Fixed-width fallback (§4.2): app slots from the bar's start + offset up to the tray
    (or the bar's end), tray slots anchored at the tray's far end."""
    z = TaskbarZone(rect, axis, order, monitor)
    lo, hi = z.span(rect)
    start = lo + slot_px(offset_dip, scale) if offset_dip else lo
    end = z.span(tray)[0] if tray is not None else hi
    apps = fixed_slots(start, end, slot_px(slot_dip, scale))
    tslots = (
        fixed_slots(*z.span(tray), slot_px(tray_slot_dip, scale), from_end=True) if tray else ()
    )
    return TaskbarZone(rect, axis, order, monitor, apps, tray, tslots)


def zone_from_rects(
    rect: Rect,
    app_rects: list[Rect],
    tray_rects: list[Rect],
    *,
    axis: str = "x",
    order: int = 0,
    monitor: int = 1,
) -> TaskbarZone:
    """UI Automation snapshot (§4.2a): every rect is its own slot whatever its size; gaps are
    silent. The tray part is the hull of the tray rects."""
    z = TaskbarZone(rect, axis, order, monitor)
    apps = tuple(sorted(z.span(r) for r in app_rects))
    tslots = tuple(sorted(z.span(r) for r in tray_rects))
    tray = None
    if tray_rects:
        x0 = min(r.x for r in tray_rects)
        y0 = min(r.y for r in tray_rects)
        x1 = max(r.x + r.w for r in tray_rects)
        y1 = max(r.y + r.h for r in tray_rects)
        tray = Rect(x0, y0, x1 - x0, y1 - y0)
    return TaskbarZone(rect, axis, order, monitor, apps, tray, tslots)


@dataclass(frozen=True)
class ZoneCell:
    """A taskbar cell. ``slot`` is 0-based (apps: left→right, tray: from the clock end);
    -1 is a silent cell (offset area or a gap between icons)."""

    order: int
    monitor: int
    part: str
    slot: int


def _slot_index(slots: tuple[Interval, ...], pos: float) -> int:
    for i, (a, b) in enumerate(slots):
        if a <= pos < b:
            return i
    return -1


def zone_cell(x: float, y: float, zones: tuple[TaskbarZone, ...]) -> ZoneCell | None:
    """The taskbar cell under ``(x, y)``, or None when it isn't on any taskbar. The tray rect
    is checked first, so it wins where it overlaps app slots (§4.3 step 3a)."""
    for z in zones:
        if not _contains(z.rect, x, y):
            continue
        pos = z.along(x, y)
        if z.tray is not None and _contains(z.tray, x, y):
            i = _slot_index(z.tray_slots, pos)
            slot = len(z.tray_slots) - 1 - i if i >= 0 else -1  # right-anchored
            return ZoneCell(z.order, z.monitor, TRAY, slot)
        return ZoneCell(z.order, z.monitor, APPS, _slot_index(z.app_slots, pos))
    return None


def slot_interval(zone: TaskbarZone, cell: ZoneCell) -> Interval | None:
    if cell.slot < 0:
        return None
    if cell.part == TRAY:
        return zone.tray_slots[len(zone.tray_slots) - 1 - cell.slot]
    return zone.app_slots[cell.slot]


@dataclass(frozen=True)
class TaskbarSound:
    """Settings that turn zone cells into sound (design §4.3)."""

    notes: tuple[int, ...]  # in-range scale notes from taskbar_low_note to taskbar_high_note
    program: int
    secondary_programs: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.notes:
            raise ValueError("taskbar zone needs at least one note")

    def program_for(self, order: int) -> int:
        if order == 0 or not self.secondary_programs:
            return self.program
        return self.secondary_programs[(order - 1) % len(self.secondary_programs)]

    def sound(self, cell: ZoneCell) -> tuple[int, int, float] | None:
        """``(note, program, velocity_factor)``; None for a silent cell. Apps ascend from the
        low note, the tray descends from the high note; past the range they wrap and play
        at :data:`WRAP_VELOCITY_FACTOR` so the wrap is audible."""
        if cell.slot < 0:
            return None
        seq = self.notes if cell.part == APPS else self.notes[::-1]
        n = len(seq)
        factor = 1.0 if cell.slot < n else WRAP_VELOCITY_FACTOR
        return seq[cell.slot % n], self.program_for(cell.order), factor


def build_taskbar_sound(
    scale: str, root: str, low: int, high: int, program: int, secondary: tuple[int, ...]
) -> TaskbarSound:
    return TaskbarSound(scale_notes(scale, root, low, high), program, tuple(secondary))


class ZoneMapper:
    """Desktop :class:`HysteresisMapper` plus taskbar zones. ``update`` returns a
    :class:`Cell` or a :class:`ZoneCell`. With no zones (taskbar mode off, or none found) it
    is exactly the desktop mapper. Entering or leaving a zone, or moving between zones/parts,
    is always a cell change; inside one part the same 2 px hysteresis applies along the
    bar's axis."""

    def __init__(self, desktop: HysteresisMapper, zones: tuple[TaskbarZone, ...] = ()) -> None:
        self.desktop = desktop
        self.zones = tuple(zones)
        self.cell: Cell | ZoneCell | None = None

    def set_zones(self, zones: tuple[TaskbarZone, ...]) -> None:
        self.zones = tuple(zones)
        self.cell = None
        self.desktop.reset()

    def _zone(self, cell: ZoneCell) -> TaskbarZone:
        return next(z for z in self.zones if z.order == cell.order)

    def update(self, x: float, y: float) -> Cell | ZoneCell:
        raw = zone_cell(x, y, self.zones) if self.zones else None
        prev = self.cell
        if raw is None:
            if isinstance(prev, ZoneCell):
                self.desktop.reset()  # its last cell is stale after a zone visit
            self.cell = self.desktop.update(x, y)
            return self.cell
        if (
            isinstance(prev, ZoneCell)
            and (prev.order, prev.part) == (raw.order, raw.part)
            and raw.slot != prev.slot
        ):
            zone = self._zone(prev)
            span = slot_interval(zone, prev)
            pos = zone.along(x, y)
            m = self.desktop.margin_px
            if span is not None and span[0] - m < pos < span[1] + m:
                return prev  # within the margin of the previous slot: no retrigger
        self.cell = raw
        return raw
