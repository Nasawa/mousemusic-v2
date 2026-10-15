"""Window height fitting, status truncation and the home position (ARCHITECTURE §11
B-2, B-3, C-1; docs/ux.md §1). Pure: Tk measurements come in as numbers/callables."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from mousemusic.mapping import Rect
from mousemusic.ui.placement import _overlap, place_window

ELLIPSIS = "…"


def work_area_for(pos: tuple[int, int], size: tuple[int, int], areas: Sequence[Rect],
                  primary: Rect) -> Rect:  # fmt: skip
    """The work area the window is (mostly) on; the primary one if it's on none."""
    win = Rect(pos[0], pos[1], max(1, size[0]), max(1, size[1]))
    best = max(areas, key=lambda a: _overlap(win, a), default=primary)
    return best if _overlap(win, best) > 0 else primary


def fit_height(required: int, minimum: int, cap: int) -> int:
    """B-2: follow the content, at least ``minimum``, at most the work-area height."""
    return max(min(required, cap), min(minimum, cap))


def wrap(text: str, width: int, measure: Callable[[str], int]) -> list[str]:
    """Greedy word wrap like Tk's ``wraplength`` (words longer than a line are kept whole)."""
    lines: list[str] = []
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            trial = f"{line} {word}" if line else word
            if line and measure(trial) > width:
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
    return lines


def truncate(text: str, width: int, max_lines: int, measure: Callable[[str], int]) -> str:
    """B-2: the whole lines that fit, the last one ending in an ellipsis. ``text`` itself
    when it fits."""
    lines = wrap(text, width, measure)
    if len(lines) <= max(1, max_lines):
        return text
    keep = lines[: max(1, max_lines)]
    last = keep[-1].rstrip()
    while last and measure(last + ELLIPSIS) > width:
        last = last[:-1].rstrip()
    keep[-1] = last + ELLIPSIS
    return "\n".join(keep)


class HomePosition:
    """C-1: the user's position ("home") versus where clamping put the window now.

    ``position(size, areas, primary)`` is where the window goes for a given size: home,
    clamped onto its work area (B-3). Because the clamp always starts from home, the window
    returns home as soon as it fits there again. ``user_moved`` makes the user's spot the
    new home; only those moves are saved (``window_x``/``window_y``)."""

    def __init__(self, home: tuple[int, int]) -> None:
        self.home = home
        self.current = home

    @property
    def clamped(self) -> bool:
        return self.current != self.home

    def position(self, size: tuple[int, int], areas: Sequence[Rect],
                 primary: Rect) -> tuple[int, int]:  # fmt: skip
        self.current = place_window(self.home, size, list(areas) or [primary], primary)
        return self.current

    def user_moved(self, pos: tuple[int, int]) -> bool:
        """A move we didn't make. Returns True when it should be saved."""
        if pos == self.current:
            return False
        self.home = self.current = pos
        return True
