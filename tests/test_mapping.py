import math
import random

import pytest

from mousemusic.instruments import INSTRUMENT_SETS
from mousemusic.mapping import (
    HYSTERESIS_PX,
    Cell,
    Grid,
    HysteresisMapper,
    Rect,
    build_grid,
    cell_at,
    map_position,
    normalize,
)
from mousemusic.scales import SCALES

FHD = Rect(0, 0, 1920, 1080)
# Secondary 1920x1080 monitor to the left of and slightly above a 1920x1080 primary.
DUAL_NEG = Rect(-1920, -200, 3840, 1280)


def default_grid():
    return build_grid("pentatonic_major", "C", 36, 96, "classic")


def test_build_grid_defaults():
    g = default_grid()
    assert g.cols == 26 and g.rows == 8


def test_normalize_basic_and_clamped():
    assert normalize(0, 0, FHD) == (0.0, 0.0)
    assert normalize(960, 540, FHD) == (0.5, 0.5)
    u, v = normalize(1920, 1080, FHD)
    assert u < 1.0 and v < 1.0
    assert normalize(-50, -50, FHD) == (0.0, 0.0)
    assert normalize(10_000, 10_000, FHD) == (u, v)
    assert normalize(math.nan, math.nan, FHD) == (0.0, 0.0)


def test_normalize_negative_origin():
    assert normalize(-1920, -200, DUAL_NEG) == (0.0, 0.0)
    assert normalize(0, 440, DUAL_NEG) == (0.5, 0.5)
    assert normalize(-3000, -500, DUAL_NEG) == (0.0, 0.0)


def test_corners_map_to_corner_cells():
    g = default_grid()
    for rect in (FHD, DUAL_NEG):
        assert cell_at(rect.x, rect.y, rect, g) == Cell(0, 0)
        assert cell_at(rect.x + rect.w - 1, rect.y + rect.h - 1, rect, g) == Cell(25, 7)
        assert cell_at(rect.x + rect.w + 99, rect.y + rect.h + 99, rect, g) == Cell(
            25, 7
        )


def test_top_row_is_index_0_and_notes_left_to_right():
    g = default_grid()
    assert map_position(0, 0, FHD, g) == (36, 0)
    assert map_position(1919, 1079, FHD, g) == (96, 71)


def test_columns_evenly_sized():
    g = Grid(notes=tuple(range(60, 64)), programs=(0,))
    rect = Rect(0, 0, 400, 100)
    assert [cell_at(x, 0, rect, g).col for x in (0, 99, 100, 199, 200, 299, 300, 399)] == [
        0, 0, 1, 1, 2, 2, 3, 3,
    ]  # fmt: skip


def test_boundary_exact():
    g = Grid(notes=(60, 62), programs=(0, 1))
    rect = Rect(-100, -100, 200, 200)
    assert cell_at(0, 0, rect, g) == Cell(1, 1)
    assert cell_at(-0.001, -0.001, rect, g) == Cell(0, 0)


@pytest.mark.parametrize("rect", [FHD, DUAL_NEG, Rect(-7680, 0, 7680, 2160)])
@pytest.mark.parametrize("scale", sorted(SCALES))
def test_pitch_monotonic_in_x_and_within_range(rect, scale):
    g = build_grid(scale, "E", 36, 96, "classic")
    y = rect.y + rect.h // 2
    prev = -1
    for x in range(rect.x - 10, rect.x + rect.w + 10, 7):
        note, program = map_position(x, y, rect, g)
        assert note >= prev
        assert 36 <= note <= 96
        assert program in g.programs
        prev = note
    assert prev == g.notes[-1]


@pytest.mark.parametrize("set_name", sorted(INSTRUMENT_SETS))
def test_every_set_rows_cover_programs(set_name):
    g = build_grid("chromatic", "C", 60, 72, set_name)
    rect = Rect(0, -5000, 100, 12800)
    seen = [map_position(0, y, rect, g)[1] for y in range(rect.y, rect.y + rect.h)]
    assert tuple(dict.fromkeys(seen)) == INSTRUMENT_SETS[set_name].programs


def test_single_row_set_y_does_nothing():
    g = build_grid("chromatic", "C", 60, 72, "single_piano")
    assert {map_position(5, y, FHD, g)[1] for y in range(-10, 1100, 13)} == {0}


def test_deterministic_random_points():
    rng = random.Random(1234)
    g = default_grid()
    pts = [(rng.uniform(-5000, 5000), rng.uniform(-3000, 3000)) for _ in range(500)]
    first = [cell_at(x, y, DUAL_NEG, g) for x, y in pts]
    second = [cell_at(x, y, DUAL_NEG, build_grid("pentatonic_major", "C", 36, 96, "classic"))
              for x, y in pts]  # fmt: skip
    assert first == second
    for c in first:
        assert 0 <= c.col < g.cols and 0 <= c.row < g.rows


def test_invalid_rect_and_grid():
    with pytest.raises(ValueError):
        Rect(0, 0, 0, 100)
    with pytest.raises(ValueError):
        Rect(0, 0, 100, -1)
    with pytest.raises(ValueError):
        Grid(notes=(), programs=(0,))
    with pytest.raises(ValueError):
        Grid(notes=(60,), programs=())
    with pytest.raises(ValueError):
        build_grid("pentatonic_major", "C", 61, 61, "classic")


# --- hysteresis ---------------------------------------------------------------

TWO = Grid(notes=(60, 62), programs=(0, 1))
SQ = Rect(0, 0, 200, 200)  # boundary at 100 on both axes


def test_hysteresis_default_is_2px():
    assert HYSTERESIS_PX == 2
    assert HysteresisMapper(TWO, SQ).margin_px == 2


def test_hysteresis_first_update_is_raw():
    h = HysteresisMapper(TWO, SQ)
    assert h.update(150, 150) == Cell(1, 1)


def test_hysteresis_rightward():
    h = HysteresisMapper(TWO, SQ)
    h.update(50, 50)
    assert h.update(100, 50).col == 0  # on boundary
    assert h.update(101, 50).col == 0  # 1 px past
    assert h.update(102, 50).col == 1  # 2 px past
    assert h.update(99, 50).col == 1  # back 1 px: stays
    assert (
        h.update(98, 50).col == 1
    )  # 2 px inside old cell: still within margin of new cell
    assert h.update(97, 50).col == 1
    assert h.update(98 - 1, 50).col == 1
    # new cell [100,200): left boundary 100, must be <= 98
    h2 = HysteresisMapper(TWO, SQ)
    h2.update(150, 50)
    assert h2.update(99, 50).col == 1
    assert h2.update(98, 50).col == 0


def test_hysteresis_jitter_on_boundary_does_not_flutter():
    h = HysteresisMapper(TWO, SQ)
    h.update(100, 100)
    start = h.cell
    for x, y in [(99, 99), (100, 100), (101, 101), (99, 101), (101, 99)] * 20:
        assert h.update(x, y) == start


def test_hysteresis_axes_independent():
    h = HysteresisMapper(TWO, SQ)
    h.update(50, 50)
    assert h.update(150, 101) == Cell(1, 0)
    assert h.update(150, 102) == Cell(1, 1)


def test_hysteresis_negative_origin():
    rect = Rect(-200, -200, 400, 400)  # boundary at 0
    h = HysteresisMapper(TWO, rect)
    h.update(-50, -50)
    assert h.update(1, 1) == Cell(0, 0)
    assert h.update(2, 2) == Cell(1, 1)


def test_hysteresis_reset_and_zero_margin():
    h = HysteresisMapper(TWO, SQ, margin_px=0)
    h.update(50, 50)
    assert h.update(100, 50) == Cell(1, 0)
    h.reset(grid=Grid(notes=(60,), programs=(0,)), rect=Rect(0, 0, 10, 10))
    assert h.cell is None
    assert h.update(500, 500) == Cell(0, 0)
    with pytest.raises(ValueError):
        HysteresisMapper(TWO, SQ, margin_px=-1)


def test_hysteresis_jump_across_many_cells():
    g = default_grid()
    h = HysteresisMapper(g, FHD)
    h.update(0, 0)
    assert h.update(1919, 1079) == Cell(25, 7)
