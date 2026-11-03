import subprocess
from types import SimpleNamespace

import pytest

from gguf_dictate.platform import default_keys, default_listener, is_wayland
from gguf_dictate.platform.keys import start_listener
from gguf_dictate.platform.linux import XdotoolKeys
from gguf_dictate.platform.wayland import KEY_LEFTCTRL, KEY_V, SESSION, EvdevListener, MutterKeys, find_keyboards, key_name

NAMES = {1: "KEY_ESC", 30: "KEY_A", 31: "KEY_S", 67: "KEY_F9", 29: "KEY_LEFTCTRL", 100: "KEY_RIGHTALT", 57: "KEY_SPACE", 48: ["KEY_B", "BTN_MISC"],
         999: "BTN_LEFT"}


def test_key_names_follow_pynput_conventions():
    assert [key_name(c, NAMES) for c in (67, 31, 29, 100, 1, 57, 48)] == ["f9", "s", "ctrl_l", "alt_gr", "esc", "space", "b"]
    assert key_name(999, NAMES) is None and key_name(12345, NAMES) is None


class Router:
    def __init__(self):
        self.log = []

    def press(self, name):
        self.log.append(("down", name))

    def release(self, name):
        self.log.append(("up", name))


def ev(code, value, type=1):
    return SimpleNamespace(type=type, code=code, value=value)


def test_events_become_press_and_release_and_repeat_is_ignored():
    router = Router()
    listener = EvdevListener(router, devices=[], names=NAMES)
    for e in (ev(67, 1), ev(67, 2), ev(67, 0), ev(31, 1, type=4), ev(999, 1)):
        listener.handle(e)
    assert router.log == [("down", "f9"), ("up", "f9")]


class FakeDevice:
    def __init__(self, batches):
        self.batches, self.closed = list(batches), False

    def fileno(self):
        return 7

    def read(self):
        return self.batches.pop(0) if self.batches else []

    def close(self):
        self.closed = True


def test_listener_thread_reads_devices_until_stopped():
    router, dev = Router(), FakeDevice([[ev(67, 1)], [ev(67, 0)]])
    listener = EvdevListener(router, devices=[dev], names=NAMES, wait=lambda r, w, x, t: (r, [], []))
    listener.start()
    for _ in range(200):
        if len(router.log) == 2:
            break
        listener.thread.join(0.01)
    listener.stop()
    assert router.log == [("down", "f9"), ("up", "f9")] and dev.closed


def test_unplugged_device_ends_the_thread():
    class Gone(FakeDevice):
        def read(self):
            raise OSError("gone")
    listener = EvdevListener(Router(), devices=[Gone([])], names=NAMES, wait=lambda r, w, x, t: (r, [], []))
    listener.run()      # returns instead of spinning


def test_find_keyboards_explains_the_input_group(monkeypatch):
    evdev = pytest.importorskip("evdev")
    monkeypatch.setattr(evdev, "list_devices", lambda: ["/dev/input/event0"])
    monkeypatch.setattr(evdev, "InputDevice", lambda path: (_ for _ in ()).throw(PermissionError(path)))
    with pytest.raises(RuntimeError, match="input"):
        find_keyboards()


class Bus:
    def __init__(self):
        self.calls = []

    def __call__(self, service, path, interface, method, signature="", args=()):
        self.calls.append((method, tuple(args)))
        return "/org/gnome/Mutter/RemoteDesktop/Session/u1" if method == "CreateSession" else None


def test_paste_sends_ctrl_v_through_one_session():
    bus = Bus()
    keys = MutterKeys(call=bus)
    keys.paste()
    keys.paste()
    assert [c[0] for c in bus.calls].count("CreateSession") == 1 and [c[0] for c in bus.calls].count("Start") == 1
    presses = [c[1] for c in bus.calls if c[0] == "NotifyKeyboardKeycode"][:4]
    assert presses == [(KEY_LEFTCTRL, True), (KEY_V, True), (KEY_V, False), (KEY_LEFTCTRL, False)]


def test_type_text_copies_then_pastes():
    bus, ran = Bus(), []
    keys = MutterKeys(call=bus, run=lambda cmd, **kw: ran.append(cmd), sleep=lambda s: None)
    keys.type_text("-hello")
    assert ran == [["wl-copy", "--", "-hello"]] and any(c[0] == "NotifyKeyboardKeycode" for c in bus.calls)


def test_session_start_failure_propagates_and_retries():
    state = {"fail": True}

    def call(service, path, interface, method, signature="", args=()):
        if method == "Start" and state["fail"]:
            raise RuntimeError("denied")
        return "/s"
    keys = MutterKeys(call=call)
    with pytest.raises(RuntimeError):
        keys.paste()
    state["fail"] = False
    keys.paste()      # a failed Start must not be cached as a live session


def test_session_selection():
    assert is_wayland("linux", {"XDG_SESSION_TYPE": "wayland"}) and not is_wayland("linux", {"XDG_SESSION_TYPE": "x11"})
    assert not is_wayland("win32", {"XDG_SESSION_TYPE": "wayland"})
    assert isinstance(default_keys("linux", wayland=False), XdotoolKeys) and isinstance(default_keys("linux", wayland=True), MutterKeys)
    assert default_listener("linux", wayland=False) is start_listener
    assert default_listener("linux", wayland=True) is not start_listener


def test_constants_match_mutter_api():
    assert SESSION.endswith("Session") and subprocess  # keycodes are evdev: Ctrl=29, V=47
    assert (KEY_LEFTCTRL, KEY_V) == (29, 47)


def test_prefer_xwayland_only_on_wayland_and_never_overrides():
    from gguf_dictate.platform import prefer_xwayland
    for env, want in (({"XDG_SESSION_TYPE": "wayland"}, "xcb"), ({"XDG_SESSION_TYPE": "x11"}, None),
                      ({"XDG_SESSION_TYPE": "wayland", "QT_QPA_PLATFORM": "wayland"}, "wayland")):
        prefer_xwayland(env)
        assert env.get("QT_QPA_PLATFORM") == want
