"""CG-S4: phase 2 ``cell_width_dip`` (design §2 A with B wrapping)."""

import random

import pytest

from mousemusic import config
from mousemusic.config import DEFAULTS
from mousemusic.mapping import (
    WRAP_FACTOR,
    Cell,
    HysteresisMapper,
    Rect,
    build_grid,
    cell_width_px,
    fixed_width_grid,
)
from test_engine import ON, TICK, make


def grid():
    return build_grid("pentatonic_major", "C", 36, 96, "classic")


@pytest.mark.parametrize(("dip", "scale", "px"), [(48, 1.0, 48), (48, 1.5, 72), (16, 2.0, 32)])
def test_cell_width_px(dip, scale, px):
    assert cell_width_px(dip, scale) == px


def test_fixed_width_grid_walks_scale_and_wraps_softer():
    g = grid()
    n = len(g.notes)
    fg = fixed_width_grid(g, 3840, 48)
    assert fg.cols == 80 and fg.programs == g.programs
    assert fg.notes[:n] == g.notes and fg.notes[n] == g.notes[0]
    assert fg.factor(Cell(0, 0)) == 1.0 and fg.factor(Cell(n - 1, 0)) == 1.0
    assert fg.factor(Cell(n, 0)) == WRAP_FACTOR
    assert g.factor(Cell(0, 0)) == 1.0  # normal grid: no factors
    assert fixed_width_grid(g, 10, 400).cols == 1
    assert fixed_width_grid(g, 100, 0).cols == 100


def test_columns_about_requested_width_and_hysteresis():
    rect = Rect(-1920, 0, 3840, 1080)
    fg = fixed_width_grid(grid(), rect.w, 48)
    m = HysteresisMapper(fg, rect)
    assert m.update(-1920 + 48 * 10 + 5, 500).col == 10
    assert m.update(-1920 + 48 * 11 + 1, 500).col == 10  # 1 px past: kept
    assert m.update(-1920 + 48 * 11 + 3, 500).col == 11


def test_config_cell_width():
    assert DEFAULTS.cell_width_dip == 0
    cases = [
        (0, 0, False), (48, 48, False), (5, 16, True), (999, 400, True),
        ("wide", 0, True), (True, 0, True),
    ]  # fmt: skip
    assert config.validate({})[0].cell_width_dip == 0
    for v, want, warn in cases:
        raw = {"cell_width_dip": v}
        s, issues = config.validate(raw)
        assert s.cell_width_dip == want and bool(issues) == warn, raw


class ScaledCursor:
    def __init__(self, cur, scale):
        self.__dict__.update(cur=cur, s=scale)

    def __getattr__(self, name):
        return getattr(self.cur, name)

    def dpi_scale(self):
        return self.s


def test_engine_off_unchanged_property():
    a, fa, ca, _, _ = make()
    b, fb, cb, _, _ = make(DEFAULTS.replace(cell_width_dip=0))
    for e in (a, b):
        e.post("start")
    rnd = random.Random(4)
    t = 0.0
    for _ in range(300):
        p = (rnd.randint(-1920, 1919), rnd.randint(-200, 1079))
        ca.pos = cb.pos = p
        a.step(t)
        b.step(t)
        t += TICK * 5
    assert fa.messages == fb.messages


def test_engine_fixed_width_sweep_and_wrap_velocity():
    e, fake, cur, _events, _ = make(DEFAULTS.replace(cell_width_dip=48, legato=False))
    e.cursor = ScaledCursor(cur, 1.0)
    e.post("start")
    t = 0.0
    n = len(e.grid.notes)
    for c in range(n + 2):  # slow sweep, one note per 48 px column, past the range
        cur.pos = (-1920 + c * 48 + 24, 500)
        e.step(t)
        t += 1.0
    ons = [m for m in fake.messages if m[0] == ON]
    assert [m[1] for m in ons[:n]] == list(e.grid.notes)
    assert ons[n][1] == e.grid.notes[0] and ons[n][2] == round(DEFAULTS.velocity * WRAP_FACTOR)
    assert ons[0][2] == DEFAULTS.velocity
    e.post("set_settings", e.settings.replace(cell_width_dip=0))  # live back to v1 mapping
    cur.pos = (-1920 + 5, 500)
    e.step(t + 1)
    assert e.mapper.desktop.grid.cols == n


def test_engine_scale_from_cursor_and_default():
    e, *_ = make(DEFAULTS.replace(cell_width_dip=48))
    assert e._desktop_grid(Rect(0, 0, 960, 10)).cols == 20  # no dpi_scale(): 1.0
    e.cursor = ScaledCursor(e.cursor, 2.0)
    assert e._desktop_grid(Rect(0, 0, 960, 10)).cols == 10


def test_win_cursor_dpi_scale():
    from mousemusic.platform.win_cursor import WinCursor

    class U:
        def __init__(self, v):
            self.v = v

        def GetDpiForSystem(self):
            if isinstance(self.v, Exception):
                raise self.v
            return self.v

    assert WinCursor(U(144)).dpi_scale() == 1.5
    assert WinCursor(U(0)).dpi_scale() == 1.0
    assert WinCursor(U(OSError())).dpi_scale() == 1.0
    assert WinCursor(object()).dpi_scale() == 1.0
