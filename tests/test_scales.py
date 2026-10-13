import pytest

from mousemusic.scales import (
    NOTE_NAMES,
    SCALE_LABELS,
    SCALES,
    note_name,
    root_pitch_class,
    scale_notes,
)


@pytest.mark.parametrize(
    ("scale", "expected"),
    [
        ("chromatic", list(range(60, 72))),
        ("major", [60, 62, 64, 65, 67, 69, 71]),
        ("minor", [60, 62, 63, 65, 67, 68, 70]),
        ("pentatonic_major", [60, 62, 64, 67, 69]),
        ("pentatonic_minor", [60, 63, 65, 67, 70]),
        ("blues", [60, 63, 65, 66, 67, 70]),
    ],
)
def test_every_scale_one_octave_from_c4(scale, expected):
    assert list(scale_notes(scale, "C", 60, 71)) == expected


def test_all_scales_tested_and_labelled():
    assert set(SCALES) == set(SCALE_LABELS) == {
        "chromatic", "major", "minor", "pentatonic_major", "pentatonic_minor", "blues",
    }  # fmt: skip


def test_spec_example_c_pentatonic_36_to_96_has_26_notes():
    notes = scale_notes("pentatonic_major", "C", 36, 96)
    assert len(notes) == 26
    assert notes[0] == 36 and notes[-1] == 96


@pytest.mark.parametrize("scale", sorted(SCALES))
@pytest.mark.parametrize("root", NOTE_NAMES)
def test_scale_properties(scale, root):
    notes = scale_notes(scale, root, 36, 96)
    assert list(notes) == sorted(set(notes))  # strictly ascending
    assert all(36 <= n <= 96 for n in notes)
    rpc = root_pitch_class(root)
    assert {(n - rpc) % 12 for n in notes} == set(SCALES[scale])
    assert scale_notes(scale, root, 36, 96) == notes  # deterministic


def test_root_transposes():
    assert scale_notes("major", "D", 62, 73) == (62, 64, 66, 67, 69, 71, 73)


@pytest.mark.parametrize(("name", "pc"), [("C", 0), ("c#", 1), ("Db", 1), (" Bb ", 10), ("B", 11)])
def test_root_pitch_class(name, pc):
    assert root_pitch_class(name) == pc


def test_root_pitch_class_unknown():
    with pytest.raises(ValueError):
        root_pitch_class("H")


@pytest.mark.parametrize(
    ("n", "name"), [(0, "C-1"), (60, "C4"), (64, "E4"), (69, "A4"), (127, "G9")]
)
def test_note_name(n, name):
    assert note_name(n) == name


@pytest.mark.parametrize("n", [-1, 128])
def test_note_name_out_of_range(n):
    with pytest.raises(ValueError):
        note_name(n)


def test_single_note_range():
    assert scale_notes("chromatic", "C", 61, 61) == (61,)
    assert scale_notes("pentatonic_major", "C", 61, 61) == ()


@pytest.mark.parametrize(
    ("args"),
    [
        ("nope", "C", 36, 96),
        ("major", "C", 96, 36),
        ("major", "C", -1, 60),
        ("major", "C", 0, 128),
    ],
)
def test_scale_notes_invalid(args):
    with pytest.raises(ValueError):
        scale_notes(*args)
