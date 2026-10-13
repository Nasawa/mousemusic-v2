import pytest

from mousemusic import midi
from mousemusic.midi import (
    DeviceBusyError,
    DeviceChoice,
    DeviceLostError,
    DeviceOpenError,
    MidiOut,
    MidiOutput,
    NoDevicesError,
    all_notes_off,
    choose_device,
    control_change,
    default_backend,
    note_off,
    note_on,
    pack_short_msg,
    program_change,
    volume_cc,
    volume_to_cc7,
)
from mousemusic.midi.fake import FakeMidiOut

GS = "Microsoft GS Wavetable Synth"


# --- builders --------------------------------------------------------------------


def test_builders():
    assert note_on(60, 100) == (0x90, 60, 100)
    assert note_off(60) == (0x80, 60, 0)
    assert program_change(11) == (0xC0, 11, 0)
    assert control_change(7, 101) == (0xB0, 7, 101)
    assert all_notes_off() == (0xB0, 123, 0)
    assert note_on(60, 1, channel=3) == (0x93, 60, 1)


@pytest.mark.parametrize(
    ("volume", "cc"), [(0, 0), (1, 1), (50, 64), (80, 102), (100, 127), (-5, 0), (150, 127)]
)
def test_volume_cc7(volume, cc):
    assert volume_to_cc7(volume) == cc
    assert volume_cc(volume) == (0xB0, 7, cc)


def test_cc7_formula_matches_spec_for_all_values():
    assert all(volume_to_cc7(v) == round(v * 127 / 100) for v in range(101))


@pytest.mark.parametrize(
    "call",
    [
        lambda: note_on(60, 100, channel=9),
        lambda: note_on(128, 100),
        lambda: note_on(60, -1),
        lambda: note_on(True, 1),
        lambda: program_change(128),
        lambda: control_change(7, 200),
        lambda: note_off(60, channel=16),
    ],
)
def test_builders_reject_bad_values(call):
    with pytest.raises(ValueError):
        call()


def test_pack_short_msg():
    assert pack_short_msg(0x90, 60, 100) == 0x90 | (60 << 8) | (100 << 16)
    assert pack_short_msg(0xC0, 11) == 0x0BC0


# --- device choice ---------------------------------------------------------------


def test_choose_saved_device():
    assert choose_device(["A", GS], GS) == DeviceChoice(1, GS, fallback=False)


def test_choose_fallback_to_zero(caplog):
    assert choose_device(["A", "B"], GS) == DeviceChoice(0, "A", fallback=True)
    assert "not found" in caplog.text


def test_choose_no_devices():
    with pytest.raises(NoDevicesError):
        choose_device([], GS)


# --- MidiOutput ------------------------------------------------------------------


def test_fake_satisfies_protocol():
    assert isinstance(FakeMidiOut(), MidiOut)


def test_open_sends_cc7_and_reenumerates():
    fake = FakeMidiOut(["A", GS])
    out = MidiOutput(fake)
    choice = out.open(GS, volume=80)
    assert choice == DeviceChoice(1, GS, False)
    assert out.is_open
    assert fake.messages == [(0xB0, 7, 102)]
    out.close()
    out.open(GS, volume=80)
    assert fake.enumerations == 2


def test_open_fallback_reports_w1_choice():
    out = MidiOutput(FakeMidiOut(["Other"]))
    assert out.open(GS, 80).fallback is True


def test_open_no_devices_e1():
    out = MidiOutput(FakeMidiOut([]))
    with pytest.raises(NoDevicesError):
        out.open(GS, 80)
    assert not out.is_open


def test_open_busy_e2():
    out = MidiOutput(FakeMidiOut([GS], open_errors={0: 4}))
    with pytest.raises(DeviceBusyError) as exc:
        out.open(GS, 80)
    assert exc.value.device == GS and exc.value.code == 4
    assert not out.is_open


def test_open_other_failure_e3_gets_device_name():
    fake = FakeMidiOut([GS])

    def fail(index):
        raise DeviceOpenError("nope", code=6)

    fake.open = fail
    out = MidiOutput(fake)
    with pytest.raises(DeviceOpenError) as exc:
        out.open(GS, 80)
    assert exc.value.device == GS and exc.value.code == 6


def test_send_and_volume_change():
    fake = FakeMidiOut()
    out = MidiOutput(fake)
    out.open(GS, 0)
    out.send(*program_change(11))
    out.send(*note_on(64, 100))
    out.set_volume(100)
    assert fake.messages == [(0xB0, 7, 0), (0xC0, 11, 0), (0x90, 64, 100), (0xB0, 7, 127)]


def test_send_when_closed_raises_lost():
    with pytest.raises(DeviceLostError):
        MidiOutput(FakeMidiOut()).send(*note_on(60, 1))


def test_device_loss_on_send_error_silences_closes_and_raises():
    fake = FakeMidiOut(fail_after=2, fail_code=6)
    out = MidiOutput(fake)
    out.open(GS, 80)
    out.send(*note_on(60, 100))
    with pytest.raises(DeviceLostError) as exc:
        out.send(*note_on(62, 100))
    assert exc.value.device == GS and exc.value.code == 6
    assert not out.is_open and not fake.is_open
    assert fake.log[-2:] == ["reset", "close"]  # best-effort silence ran, then close


def test_open_fails_if_cc7_send_fails():
    fake = FakeMidiOut(fail_after=0)
    out = MidiOutput(fake)
    with pytest.raises(DeviceLostError):
        out.open(GS, 80)
    assert not fake.is_open


def test_silence_order_and_close():
    fake = FakeMidiOut()
    out = MidiOutput(fake)
    out.open(GS, 80)
    fake.messages.clear()
    out.close(sounding_note=64)
    assert fake.messages == [(0x80, 64, 0), (0xB0, 123, 0)]
    assert fake.log[-2:] == ["reset", "close"]
    assert not out.is_open
    out.close()  # idempotent
    out.silence()  # no-op when closed


def test_silence_without_sounding_note():
    fake = FakeMidiOut()
    out = MidiOutput(fake)
    out.open(GS, 80)
    fake.messages.clear()
    out.silence()
    assert fake.messages == [(0xB0, 123, 0)]
    assert out.is_open


def test_close_swallows_backend_errors(caplog):
    fake = FakeMidiOut()
    out = MidiOutput(fake)
    out.open(GS, 80)

    def boom():
        raise OSError("driver gone")

    fake.close = boom
    out.close()
    assert not out.is_open and "closing MIDI device failed" in caplog.text


def test_reopen_closes_previous():
    fake = FakeMidiOut(["A", "B"])
    out = MidiOutput(fake)
    out.open("A", 80)
    out.open("B", 80)
    assert out.device.name == "B" and fake.opened == 1


def test_default_backend_off_windows(monkeypatch):
    monkeypatch.setattr(midi.sys, "platform", "linux")
    b = default_backend()
    assert isinstance(b, FakeMidiOut) and b.list_devices() == []


# --- fake backend itself ---------------------------------------------------------


def test_fake_backend_behaviour():
    lines = []
    fake = FakeMidiOut(["X"], echo=lines.append)
    assert fake.short_msg(0x90, 1, 1) == 5 and fake.reset() == 5
    with pytest.raises(DeviceOpenError):
        fake.open(3)
    fake.open(0)
    with pytest.raises(DeviceOpenError):
        fake.open(0)
    assert fake.short_msg(0x90, 0x3C, 0x64) == 0
    fake.close()
    fake.close()
    assert lines == ["open 0: X", "msg 90 3C 64", "close"]
