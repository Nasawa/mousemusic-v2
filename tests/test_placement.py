from mousemusic.mapping import Rect
from mousemusic.ui.placement import centre, place_window

PRIMARY = Rect(0, 0, 1920, 1080)
LEFT = Rect(-2560, -200, 2560, 1400)  # secondary on the left, negative coords
SIZE = (340, 300)


def test_no_saved_position_centres_on_primary():
    assert place_window((None, None), SIZE, [PRIMARY], PRIMARY) == (790, 390)
    assert place_window((5, None), SIZE, [PRIMARY], PRIMARY) == (790, 390)


def test_saved_inside_is_kept():
    assert place_window((100, 200), SIZE, [PRIMARY, LEFT], PRIMARY) == (100, 200)
    assert place_window((-1000, -100), SIZE, [PRIMARY, LEFT], PRIMARY) == (-1000, -100)


def test_partly_off_screen_is_clamped_onto_best_monitor():
    assert place_window((1800, 1000), SIZE, [PRIMARY], PRIMARY) == (1580, 780)
    assert place_window((-50, -50), SIZE, [PRIMARY], PRIMARY) == (0, 0)
    # straddles both monitors, mostly on LEFT -> clamped into LEFT
    assert place_window((-300, 100), SIZE, [PRIMARY, LEFT], PRIMARY) == (-340, 100)


def test_monitor_gone_centres_on_primary():
    assert place_window((-1000, 100), SIZE, [PRIMARY], PRIMARY) == (790, 390)
    assert place_window((10, 10), SIZE, [], PRIMARY) == (790, 390)


def test_window_bigger_than_monitor_pins_to_origin():
    small = Rect(0, 0, 300, 200)
    assert place_window((10, 10), SIZE, [small], small) == (0, 0)
    assert centre((400, 400), small) == (0, 0)
