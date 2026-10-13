import itertools

import pytest

from mousemusic.midi import DeviceLostError, MidiOutput
from mousemusic.midi.fake import FakeMidiOut
from mousemusic.scheduler import RATE_LIMIT_S, NoteParams, Scheduler

ON, OFF, PC, CC = 0x90, 0x80, 0xC0, 0xB0


@pytest.fixture
def rig():
    fake = FakeMidiOut()
    out = MidiOutput(fake)
    out.open("Microsoft GS Wavetable Synth", 80)
    fake.messages.clear()
    return fake, Scheduler(out, NoteParams(velocity=100, note_length_ms=250))


def test_first_note_program_then_note_on(rig):
    fake, s = rig
    assert s.request(60, 11, 0.0) is True
    assert fake.messages == [(PC, 11, 0), (ON, 60, 100)]


def test_column_change_note_off_before_note_on_no_repeat_pc(rig):
    fake, s = rig
    s.request(60, 11, 0.0)
    s.request(62, 11, 0.1)
    assert fake.messages[2:] == [(OFF, 60, 0), (ON, 62, 100)]


def test_row_change_retriggers_same_pitch_with_pc_first(rig):  # SN-14
    fake, s = rig
    s.request(60, 11, 0.0)
    s.request(60, 12, 0.1)
    assert fake.messages[2:] == [(OFF, 60, 0), (PC, 12, 0), (ON, 60, 100)]


def test_note_length_expiry_within_one_tick(rig):  # SN-12
    fake, s = rig
    s.request(60, 0, 0.0)
    tick = 1 / 125
    t = 0.0
    while not any(m[0] == OFF for m in fake.messages):
        t += tick
        s.tick(t)
    assert 0.250 <= t < 0.250 + tick + 1e-9
    assert s.active_note is None and s.next_deadline() is None


def test_rate_limit_latest_wins_no_queue(rig):  # SN-13
    fake, s = rig
    s.request(60, 0, 0.000)
    for i, t in enumerate((0.005, 0.010, 0.015, 0.020, 0.025)):
        assert s.request(62 + i, 0, t) is False
    assert s.next_deadline() == pytest.approx(RATE_LIMIT_S)
    s.tick(0.029)
    assert [m for m in fake.messages if m[0] == ON] == [(ON, 60, 100)]
    s.tick(0.030)
    ons = [m for m in fake.messages if m[0] == ON]
    assert ons == [(ON, 60, 100), (ON, 66, 100)]  # only the latest of the 5
    s.tick(0.1)
    assert len([m for m in fake.messages if m[0] == ON]) == 2  # nothing queued


@pytest.mark.parametrize("hz", [30, 125, 250])
def test_never_more_than_one_note_on_per_30ms(rig, hz):
    _fake, s = rig
    times = []
    t, note = 0.0, 40
    for _ in range(2000):
        t += 1 / hz
        note = 40 + (note - 39) % 40
        if s.request(note, 0, t):
            times.append(t)
        s.tick(t)
    gaps = [b - a for a, b in itertools.pairwise(times)]
    assert min(gaps) >= RATE_LIMIT_S - 1e-9
    assert s.note_ons == len(times)


def test_legato_holds_until_next_note(rig):
    fake, s = rig
    s.set_params(NoteParams(legato=True), 0.0)
    s.request(60, 0, 0.0)
    s.tick(10.0)
    assert s.active_note == 60 and not any(m[0] == OFF for m in fake.messages)
    s.request(62, 0, 10.1)
    assert (OFF, 60, 0) in fake.messages


def test_legato_toggle_schedules_from_now(rig):
    _fake, s = rig
    s.set_params(NoteParams(legato=True, note_length_ms=100), 0.0)
    s.request(60, 0, 0.0)
    s.set_params(NoteParams(legato=False, note_length_ms=100), 5.0)
    assert s.off_at == pytest.approx(5.1)
    s.set_params(NoteParams(legato=True, note_length_ms=100), 5.05)
    assert s.off_at is None
    s.set_params(NoteParams(legato=True), 6.0)  # still legato: stays held
    assert s.off_at is None


def test_set_params_without_note(rig):
    _, s = rig
    s.set_params(NoteParams(velocity=5), 0.0)
    s.request(60, 0, 0.0)
    assert s.output.backend.messages[-1] == (ON, 60, 5)


def test_silence_sequence(rig):  # SN-01
    fake, s = rig
    s.request(64, 0, 0.0)
    fake.messages.clear()
    fake.log.clear()
    s.silence()
    assert fake.messages == [(OFF, 64, 0), (CC, 123, 0)]
    assert fake.log[-1] == "reset"
    assert s.active_note is None and s.program is None and s.pending is None


def test_program_resent_after_silence(rig):
    fake, s = rig
    s.request(60, 5, 0.0)
    s.silence()
    fake.messages.clear()
    s.request(60, 5, 1.0)
    assert fake.messages == [(PC, 5, 0), (ON, 60, 100)]


@pytest.mark.parametrize("fail_after", [0, 1, 2, 3])
def test_device_loss_on_any_message_resets_state_and_raises(fail_after):  # MD-09a
    fake = FakeMidiOut(fail_after=None)
    out = MidiOutput(fake)
    out.open("Microsoft GS Wavetable Synth", 80)
    s = Scheduler(out)
    s.request(60, 0, 0.0)  # CC7, PC, ON = 3 messages
    fake.fail_after = len(fake.messages) + fail_after
    with pytest.raises(DeviceLostError):
        s.request(62, 1, 1.0)  # OFF, PC, ON
        s.tick(5.0)
        s.request(63, 1, 6.0)
        s.request(64, 1, 7.0)
    assert s.active_note is None and s.pending is None and not out.is_open


def test_no_pending_flush_noop(rig):
    _, s = rig
    s.tick(1.0)
    assert s.next_deadline() is None
