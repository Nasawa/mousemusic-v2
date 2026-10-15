import random

import pytest

from mousemusic import config
from mousemusic.mapping import (
    APPS,
    TRAY,
    WRAP_VELOCITY_FACTOR,
    Cell,
    HysteresisMapper,
    Rect,
    TaskbarZone,
    ZoneCell,
    ZoneMapper,
    build_grid,
    build_taskbar_sound,
    fixed_slots,
    slot_px,
    zone_cell,
    zone_fixed,
    zone_from_rects,
)

DESK = Rect(0, 0, 1920, 1080)
BAR = Rect(0, 1032, 1920, 48)


def snd(**kw):
    a = dict(scale="pentatonic_major", root="C", low=48, high=96, program=13,
             secondary=(8, 108, 9))  # fmt: skip
    a.update(kw)
    return build_taskbar_sound(**a)


@pytest.mark.parametrize(("scale", "px"), [(1.0, 44), (1.25, 55), (1.5, 66), (2.0, 88)])
def test_slot_width_per_dpi(scale, px):
    assert slot_px(44, scale) == px
    z = zone_fixed(Rect(0, 0, 2000, 60), scale, slot_dip=44)
    assert z.app_slots[1] == (px, 2 * px)
    assert zone_cell(px * 3 + 1, 10, (z,)) == ZoneCell(0, 1, APPS, 3)
    assert zone_cell(px * 3 - 1, 10, (z,)).slot == 2  # exact boundary


def test_fixed_slots_edges():
    assert fixed_slots(0, 10, 4) == ((0, 4), (4, 8), (8, 10))
    assert fixed_slots(0, 10, 4, from_end=True) == ((0, 2), (2, 6), (6, 10))
    assert fixed_slots(5, 5, 4) == () and fixed_slots(0, 5, 0) == ()


def test_offset_is_silent_and_outside_is_none():
    z = zone_fixed(BAR, 1.0, slot_dip=44, offset_dip=100)
    assert zone_cell(50, 1050, (z,)) == ZoneCell(0, 1, APPS, -1)
    assert zone_cell(100, 1050, (z,)).slot == 0
    assert zone_cell(50, 500, (z,)) is None
    assert snd().sound(ZoneCell(0, 1, APPS, -1)) is None


def test_notes_ascend_wrap_and_velocity():
    s = snd()
    n = len(s.notes)
    assert s.notes[0] == 48 and s.notes[-1] == 96
    assert [s.sound(ZoneCell(0, 1, APPS, k))[0] for k in range(3)] == list(s.notes[:3])
    assert s.sound(ZoneCell(0, 1, APPS, 0))[2] == 1.0
    assert s.sound(ZoneCell(0, 1, APPS, n)) == (48, 13, WRAP_VELOCITY_FACTOR)


def test_tray_right_anchored_descending_and_wins():
    tray = Rect(1700, 1032, 220, 48)
    z = zone_fixed(BAR, 1.0, slot_dip=44, tray=tray, tray_slot_dip=32)
    assert z.app_slots[-1][1] == 1700  # apps stop at the tray
    c = zone_cell(1919, 1050, (z,))
    assert c == ZoneCell(0, 1, TRAY, 0)
    assert zone_cell(1919 - 32, 1050, (z,)).slot == 1
    s = snd()
    assert s.sound(c)[0] == 96 and s.sound(ZoneCell(0, 1, TRAY, 1))[0] == s.notes[-2]
    # more app slots (narrower apps) don't move tray notes
    z2 = zone_fixed(BAR, 1.0, slot_dip=24, tray=tray, tray_slot_dip=32)
    assert zone_cell(1919, 1050, (z2,)) == c
    # tray rect wins where it overlaps app slots (UIA snapshot overlapping)
    z3 = zone_from_rects(BAR, [Rect(1690, 1032, 44, 48)], [Rect(1700, 1032, 32, 48)])
    assert zone_cell(1710, 1050, (z3,)).part == TRAY


def test_missing_tray_apps_cover_bar():
    z = zone_fixed(BAR, 1.0, slot_dip=48)
    assert z.tray is None and z.app_slots[-1][1] == 1920
    assert zone_cell(1919, 1050, (z,)).part == APPS


def test_vertical_bars_and_negative_monitor():
    left = zone_fixed(Rect(-1920, 0, 48, 1080), 1.0, slot_dip=44, axis="y", order=1, monitor=2)
    assert zone_cell(-1900, 45, (left,)) == ZoneCell(1, 2, APPS, 1)
    right = zone_fixed(Rect(1872, 0, 48, 1080), 1.0, slot_dip=44, axis="y")
    assert zone_cell(1900, 0, (right,)).slot == 0
    top = zone_fixed(Rect(-1920, 0, 1920, 48), 1.0, slot_dip=44, order=1, monitor=2)
    assert zone_cell(-1920 + 44, 10, (top,)).slot == 1


def test_two_taskbars_mixed_dpi_same_pitch_different_program():
    p = zone_fixed(BAR, 1.0, slot_dip=44)
    sec = zone_fixed(Rect(1920, 1068, 2880, 72), 1.5, slot_dip=44, order=1, monitor=2)
    zones = (p, sec)
    c1 = zone_cell(44 * 4 + 5, 1050, zones)
    c2 = zone_cell(1920 + 66 * 4 + 5, 1100, zones)
    s = snd()
    assert c1.slot == c2.slot == 4
    a, b = s.sound(c1), s.sound(c2)
    assert a[0] == b[0] and (a[1], b[1]) == (13, 8)


@pytest.mark.parametrize(("n", "want"), [(1, [13]), (2, [13, 8]), (4, [13, 8, 108, 9]),
                                         (6, [13, 8, 108, 9, 8, 108])])  # fmt: skip
def test_n_taskbars_programs(n, want):
    s = snd()
    assert [s.program_for(k) for k in range(n)] == want
    assert snd(secondary=()).program_for(3) == 13


def test_uia_snapshot_cells_gaps_and_mixed_widths():
    # Christopher-like: custom-size icons with gaps, tray + clock on the right.
    apps = [Rect(10 + i * 40, 1032, 36, 48) for i in range(20)]  # 4 px gaps
    tray = [Rect(1600 + i * 28, 1032, 28, 48) for i in range(8)] + [Rect(1830, 1032, 90, 48)]
    z = zone_from_rects(BAR, list(reversed(apps)), tray)
    assert len(z.app_slots) == 20 and len(z.tray_slots) == 9
    cells = [zone_cell(10 + i * 40 + 18, 1050, (z,)) for i in range(20)]
    assert [c.slot for c in cells] == list(range(20))
    assert zone_cell(10 + 36 + 1, 1050, (z,)).slot == -1  # gap: silent
    s = snd()
    notes = [s.sound(c)[0] for c in cells]
    assert notes == sorted(notes) and len(set(notes[:17])) == 17
    clock = zone_cell(1900, 1050, (z,))
    assert clock == ZoneCell(0, 1, TRAY, 0) and s.sound(clock)[0] == 96
    empty = zone_from_rects(BAR, [], [])
    assert zone_cell(5, 1050, (empty,)) == ZoneCell(0, 1, APPS, -1)


def mapper(zones=()):
    grid = build_grid("pentatonic_major", "C", 36, 96, "classic")
    return ZoneMapper(HysteresisMapper(grid, DESK), zones)


def test_zone_mapper_transitions_and_hysteresis():
    z = zone_fixed(BAR, 1.0, slot_dip=44)
    m = mapper((z,))
    assert isinstance(m.update(500, 500), Cell)
    c = m.update(44 * 3 + 20, 1050)
    assert c == ZoneCell(0, 1, APPS, 3)
    assert m.update(44 * 4, 1050) == c  # 0 px past the edge
    assert m.update(44 * 4 + 1, 1050) == c  # 1 px of jitter: no retrigger
    assert m.update(44 * 4 + 2, 1050).slot == 4  # 2 px: change
    assert m.update(44 * 4 - 1, 1050).slot == 4  # back by 1 px: kept
    assert m.update(44 * 4 - 3, 1050).slot == 3
    d = m.update(500, 1000)  # leaving the zone is always a change
    assert isinstance(d, Cell)
    m.set_zones(())
    assert isinstance(m.update(10, 1050), Cell)


def test_zone_mapper_slow_sweep_20_distinct_ascending():
    z = zone_fixed(Rect(0, 1032, 20 * 44, 48), 1.0, slot_dip=44)
    m = mapper((z,))
    s = snd()
    seen = []
    for x in range(0, 20 * 44):
        c = m.update(x, 1050)
        n = s.sound(c)[0]
        if not seen or seen[-1] != n:
            seen.append(n)
    assert len(seen) == 20 and seen == sorted(seen)


def test_taskbar_off_identical_to_desktop_property():
    grid = build_grid("pentatonic_major", "C", 36, 96, "classic")
    plain = HysteresisMapper(grid, DESK)
    zm = ZoneMapper(HysteresisMapper(grid, DESK))
    rnd = random.Random(16)
    for _ in range(5000):
        x, y = rnd.uniform(-50, 1970), rnd.uniform(-50, 1130)
        assert zm.update(x, y) == plain.update(x, y)


def test_zone_tray_part_change_and_silent_prev():
    tray = Rect(1700, 1032, 220, 48)
    z = zone_fixed(BAR, 1.0, slot_dip=44, offset_dip=40, tray=tray)
    m = mapper((z,))
    assert m.update(10, 1050).slot == -1
    assert m.update(41, 1050).slot == 0  # from silent: immediate
    assert m.update(1699, 1050).part == APPS
    assert m.update(1700, 1050).part == TRAY  # part change: immediate


def test_taskbar_zone_defaults():
    z = TaskbarZone(BAR)
    assert z.axis == "x" and z.order == 0 and z.app_slots == ()


# --- settings ------------------------------------------------------------------------------


def test_taskbar_defaults():
    d = config.DEFAULTS
    assert (d.taskbar_mode, d.taskbar_slot_dip, d.taskbar_tray_slot_dip) == (False, 44, 32)
    assert (d.taskbar_program, d.taskbar_secondary_programs) == (13, (8, 108, 9))
    assert (d.taskbar_low_note, d.taskbar_high_note, d.taskbar_offset_dip) == (48, 96, 0)
    assert (d.taskbar_monitors, d.taskbar_slot_source, d.taskbar_tray) == ("all", "auto", True)


@pytest.mark.parametrize(
    ("raw", "key", "want"),
    [
        ({"taskbar_mode": "yes"}, "taskbar_mode", False),
        ({"taskbar_slot_dip": 5}, "taskbar_slot_dip", 24),
        ({"taskbar_slot_dip": 500}, "taskbar_slot_dip", 128),
        ({"taskbar_tray_slot_dip": 200}, "taskbar_tray_slot_dip", 96),
        ({"taskbar_offset_dip": -3}, "taskbar_offset_dip", 0),
        ({"taskbar_program": "marimba"}, "taskbar_program", 13),
        ({"taskbar_program": 300}, "taskbar_program", 127),
        ({"taskbar_monitors": "some"}, "taskbar_monitors", "all"),
        ({"taskbar_slot_source": "magic"}, "taskbar_slot_source", "auto"),
        ({"taskbar_secondary_programs": []}, "taskbar_secondary_programs", (8, 108, 9)),
        ({"taskbar_secondary_programs": [1] * 9}, "taskbar_secondary_programs", (8, 108, 9)),
        ({"taskbar_secondary_programs": [1, 200]}, "taskbar_secondary_programs", (8, 108, 9)),
        ({"taskbar_secondary_programs": [1, 2.5]}, "taskbar_secondary_programs", (8, 108, 9)),
        ({"taskbar_secondary_programs": "8"}, "taskbar_secondary_programs", (8, 108, 9)),
        ({"taskbar_tray": 1}, "taskbar_tray", True),
    ],
)
def test_invalid_taskbar_keys_default_plus_w3(raw, key, want):
    s, issues = config.validate(raw)
    assert getattr(s, key) == want and issues


def test_taskbar_note_range_octave_rule_and_round_trip(tmp_path):
    s, issues = config.validate({"taskbar_low_note": 60, "taskbar_high_note": 62})
    assert (s.taskbar_low_note, s.taskbar_high_note) == (60, 72) and issues
    s, issues = config.validate({"taskbar_secondary_programs": [40, 41], "taskbar_mode": True})
    assert s.taskbar_secondary_programs == (40, 41) and not issues
    path = tmp_path / "settings.json"
    config.save(s, path)
    assert config.load_report(path).settings == s
    import json

    assert json.loads(path.read_text())["taskbar_secondary_programs"] == [40, 41]
