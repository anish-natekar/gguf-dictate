"""pynput key injection and Qt toast adapters (fakes, no display), plus per-OS selection."""
import pytest

from gguf_dictate.platform import PynputKeys, QtNotifier, default_keys, default_notifier
from gguf_dictate.platform.linux import NotifySend, XdotoolKeys


class FakeController:
    def __init__(self):
        self.log = []

    def pressed(self, key):
        ctl = self

        class Ctx:
            def __enter__(self):
                ctl.log.append(("down", key))

            def __exit__(self, *a):
                ctl.log.append(("up", key))
        return Ctx()

    def press(self, k):
        self.log.append(("press", k))

    def release(self, k):
        self.log.append(("release", k))

    def type(self, text):
        self.log.append(("type", text))


def test_paste_holds_modifier_while_tapping_v():
    c = FakeController()
    PynputKeys(c, modifier="CTRL").paste()
    assert c.log == [("down", "CTRL"), ("press", "v"), ("release", "v"), ("up", "CTRL")]


def test_type_text_passes_unicode_through():
    c = FakeController()
    PynputKeys(c, modifier="CTRL").type_text("héllo → 例")
    assert c.log == [("type", "héllo → 例")]


def test_qt_notifier_calls_tray_message():
    got = []

    class Icon:
        def showMessage(self, title, body, *a):
            got.append((title, body))
    QtNotifier(Icon()).toast("Snip saved", "2 in queue")
    assert got == [("Snip saved", "2 in queue")]


def test_linux_defaults_are_xdotool_and_notify_send():
    assert isinstance(default_keys("linux"), XdotoolKeys)
    assert isinstance(default_notifier("linux", icon=None), NotifySend)


@pytest.mark.parametrize("osname", ["win32", "darwin"])
def test_other_platforms_use_pynput_and_qt(osname, monkeypatch):
    import gguf_dictate.platform as p
    monkeypatch.setattr(p, "PynputKeys", lambda *a, **k: "keys")
    assert default_keys(osname) == "keys"
    assert isinstance(default_notifier(osname, icon=object()), QtNotifier)


def test_session_warning_only_on_wayland_linux():
    from gguf_dictate.platform import session_warning
    assert "X11" in session_warning("linux", {"XDG_SESSION_TYPE": "wayland"})
    assert session_warning("linux", {"XDG_SESSION_TYPE": "x11"}) is None
    assert session_warning("linux", {}) is None
    assert session_warning("win32", {"XDG_SESSION_TYPE": "wayland"}) is None
