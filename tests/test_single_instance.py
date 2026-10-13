from mousemusic.platform import single_instance as si
from mousemusic.platform.single_instance import SingleInstance


class FakeK32:
    def __init__(self, existing=False, fail=False):
        self.existing, self.fail = existing, fail
        self.err = 0
        self.closed = []

    def CreateMutexW(self, attrs, owner, name):
        assert name == "Local\\MouseMusicV2"
        if self.fail:
            self.err = 5
            return 0
        self.err = si.ERROR_ALREADY_EXISTS if self.existing else 0
        return 42

    def CloseHandle(self, h):
        self.closed.append(h)


class FakeU32:
    def __init__(self):
        self.posted = []

    def RegisterWindowMessageW(self, name):
        assert name == si.SHOW_MESSAGE_NAME
        return 0xC0DE

    def PostMessageW(self, hwnd, msg, wp, lp):
        self.posted.append((hwnd, msg))
        return 1


def make(**kw):
    k = FakeK32(**kw)
    u = FakeU32()
    return SingleInstance(k, u, lambda: k.err), k, u


def test_first_instance():
    s, k, _ = make()
    assert s.acquire() is True and s.show_message == 0xC0DE
    s.release()
    s.release()
    assert k.closed == [42]


def test_second_instance_signals_first():
    s, k, u = make(existing=True)
    assert s.acquire() is False and k.closed == [42]
    s.signal_first()
    assert u.posted == [(0xFFFF, 0xC0DE)]


def test_mutex_failure_does_not_block(caplog):
    s, _, _ = make(fail=True)
    assert s.acquire() is True and "CreateMutexW failed" in caplog.text


def test_unavailable_off_windows(monkeypatch):
    monkeypatch.setattr(si.sys, "platform", "linux")
    s = SingleInstance()
    assert s.acquire() is True and s.show_message is None
    s.signal_first()
    s.release()
