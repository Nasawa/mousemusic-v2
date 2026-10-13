"""Window placement on restore (docs/ux.md §1, ARCHITECTURE.md §4): pure, tested.

Positions are physical pixels (Tk coordinates under per-monitor DPI awareness). A saved
position is only reused if the window would overlap a currently visible monitor; it is then
clamped fully onto the monitor it overlaps most. Otherwise the window is centred on the
primary monitor.
"""

from __future__ import annotations

from collections.abc import Sequence

from mousemusic.mapping import Rect


def _overlap(a: Rect, b: Rect) -> int:
    w = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
    h = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
    return w * h if w > 0 and h > 0 else 0


def _clamp(pos: int, size: int, lo: int, extent: int) -> int:
    if size >= extent:
        return lo
    return min(max(pos, lo), lo + extent - size)


def centre(size: tuple[int, int], primary: Rect) -> tuple[int, int]:
    w, h = size
    return primary.x + max(0, (primary.w - w) // 2), primary.y + max(0, (primary.h - h) // 2)


def place_window(
    saved: tuple[int | None, int | None],
    size: tuple[int, int],
    monitors: Sequence[Rect],
    primary: Rect,
) -> tuple[int, int]:
    x, y = saved
    w, h = size
    if x is None or y is None or not monitors:
        return centre(size, primary)
    win = Rect(x, y, max(1, w), max(1, h))
    best = max(monitors, key=lambda m: _overlap(win, m))
    if _overlap(win, best) == 0:
        return centre(size, primary)
    return _clamp(x, w, best.x, best.w), _clamp(y, h, best.y, best.h)
