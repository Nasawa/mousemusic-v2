import pytest

from mousemusic.instruments import (
    DEFAULT_INSTRUMENT_SET,
    GM_PROGRAM_NAMES,
    INSTRUMENT_SETS,
    InstrumentSet,
    get_instrument_set,
    program_name,
)

SPEC_SETS = {
    "classic": (0, 11, 24, 40, 42, 56, 73, 71),
    "mellow": (4, 11, 12, 46, 48, 52, 89),
    "percussive": (8, 9, 12, 13, 14, 108, 114),
    "single_piano": (0,),
    "full_gm": tuple(range(128)),
}


def test_gm_has_128_unique_names():
    assert len(GM_PROGRAM_NAMES) == 128
    assert len(set(GM_PROGRAM_NAMES)) == 128


@pytest.mark.parametrize(("name", "programs"), sorted(SPEC_SETS.items()))
def test_every_set_matches_spec(name, programs):
    s = get_instrument_set(name)
    assert s.name == name
    assert s.programs == programs
    assert s.label


def test_no_extra_sets_and_default():
    assert set(INSTRUMENT_SETS) == set(SPEC_SETS)
    assert DEFAULT_INSTRUMENT_SET == "classic"


@pytest.mark.parametrize(
    ("p", "name"),
    [(0, "Acoustic Grand Piano"), (11, "Vibraphone"), (24, "Acoustic Guitar (nylon)"),
     (40, "Violin"), (42, "Cello"), (56, "Trumpet"), (71, "Clarinet"), (73, "Flute"),
     (89, "Pad 2 (warm)"), (108, "Kalimba"), (114, "Steel Drums"), (127, "Gunshot")],
)  # fmt: skip
def test_program_names(p, name):
    assert program_name(p) == name


@pytest.mark.parametrize("p", [-1, 128])
def test_program_name_out_of_range(p):
    with pytest.raises(ValueError):
        program_name(p)


def test_unknown_set():
    with pytest.raises(ValueError):
        get_instrument_set("kazoo")


@pytest.mark.parametrize("programs", [(), (128,), (-1,)])
def test_invalid_set(programs):
    with pytest.raises(ValueError):
        InstrumentSet("bad", "Bad", programs)
