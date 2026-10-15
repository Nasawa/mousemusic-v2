import io
import types

from mousemusic.platform import console as c


class K32:
    def __init__(self, handles=None, ftype=1, attach=True):
        self.handles = handles or {}
        self.ftype, self.attach = ftype, attach
        self.attached_with = None

    def GetStdHandle(self, n):
        return self.handles.get(n, 0)

    def GetFileType(self, h):
        return self.ftype

    def AttachConsole(self, pid):
        self.attached_with = pid
        return self.attach


def fake_sys(out=None, err=None):
    return types.SimpleNamespace(stdout=out, stderr=err)


def test_wants_console():
    assert c.wants_console(["--self-test"]) and c.wants_console(["-h"])
    assert not c.wants_console([]) and not c.wants_console(["--dry-run"])


def test_non_windows_and_present_streams_skip():
    assert c.attach_console(platform="linux", sys_module=fake_sys()) == "skipped"
    s = fake_sys(io.StringIO(), io.StringIO())
    k = K32()
    assert c.attach_console(platform="win32", sys_module=s, kernel32=k) == "skipped"
    assert k.attached_with is None


def test_inherited_handles_are_wrapped():
    s, k = fake_sys(), K32({c.STD_OUTPUT_HANDLE: 5, c.STD_ERROR_HANDLE: 6})
    wrapped = []
    r = c.attach_console(platform="win32", sys_module=s, kernel32=k,
                         wrap_handle=lambda h: wrapped.append(h) or io.StringIO())  # fmt: skip
    assert r == "inherited" and wrapped == [5, 6] and k.attached_with is None


def test_attach_parent_console_opens_conout():
    s, k = fake_sys(), K32()
    opened = []

    def open_file(name, *a, **kw):
        opened.append(name)
        return io.StringIO()

    assert c.attach_console(platform="win32", sys_module=s, kernel32=k, open_file=open_file) == (
        "attached"
    )
    assert k.attached_with == 0xFFFFFFFF and opened == ["CONOUT$", "CONOUT$"]
    assert s.stdout.getvalue() == "\n"


def test_no_parent_console_does_nothing():
    s, k = fake_sys(), K32(attach=False)
    assert c.attach_console(platform="win32", sys_module=s, kernel32=k) == "none"
    assert s.stdout is None and s.stderr is None


def test_partial_inherit_then_attach_and_errors():
    # stdout redirected (pipe), stderr not: wrap stdout, attach console for stderr.
    s, k = fake_sys(), K32({c.STD_OUTPUT_HANDLE: 5})
    k.GetFileType = lambda h: 1 if h == 5 else 0

    def open_fail(*a, **kw):
        raise OSError("no CONOUT$")

    r = c.attach_console(platform="win32", sys_module=s, kernel32=k,
                         wrap_handle=lambda h: io.StringIO(), open_file=open_fail)  # fmt: skip
    assert r == "attached" and s.stdout is not None and s.stderr is None
    # wrapping fails and no console: nothing changes
    s2, k2 = fake_sys(), K32({c.STD_OUTPUT_HANDLE: 5}, attach=False)

    def wrap_fail(h):
        raise OSError("bad handle")

    assert c.attach_console(platform="win32", sys_module=s2, kernel32=k2,
                            wrap_handle=wrap_fail) == "none"  # fmt: skip
    # stdout inherited, stderr none and no console -> "inherited"
    s3, k3 = fake_sys(), K32({c.STD_OUTPUT_HANDLE: 5}, attach=False)
    k3.GetFileType = lambda h: 1 if h == 5 else 0
    assert c.attach_console(platform="win32", sys_module=s3, kernel32=k3,
                            wrap_handle=lambda h: io.StringIO()) == "inherited"  # fmt: skip


def test_main_attaches_only_for_cli_flags(monkeypatch):
    from mousemusic import __main__ as m

    calls = []
    monkeypatch.setattr(c, "attach_console", lambda: calls.append(1) or "skipped")
    assert m.main(["--list-devices"]) == 0
    monkeypatch.setattr("mousemusic.app.run", lambda opts: 0)
    assert m.main(["--dry-run"]) == 0
    assert calls == [1]


def test_wants_console_play_instrument_forms():
    from mousemusic.platform.console import wants_console

    assert wants_console(["--play-instrument", "5"])
    assert wants_console(["--play-instrument=5"])
    assert not wants_console(["--dry-run"])
