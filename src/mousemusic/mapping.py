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


def build_grid(
    scale: str, root: str, low_note: int, high_note: int, instrument_set: str
) -> Grid:
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


def _past_boundary(
    pos: float, origin: int, size: int, n: int, idx: int, margin: float
) -> bool:
    """True if ``pos`` is at least ``margin`` px outside cell ``idx`` along one axis."""
    lo = origin + idx * size / n
    hi = origin + (idx + 1) * size / n
    return pos >= hi + margin or pos <= lo - margin


class HysteresisMapper:
    """Wraps :func:`cell_at` so a cell change only registers once the cursor is at least
    ``margin_px`` past the boundary. Each axis is handled independently."""

    def __init__(
        self, grid: Grid, rect: Rect, margin_px: float = HYSTERESIS_PX
    ) -> None:
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
