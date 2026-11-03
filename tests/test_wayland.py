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


def test_paste_sends_ctrl_v_in_its_own_session_and_stops_it():
    bus = Bus()
    keys = MutterKeys(call=bus, sleep=lambda s: None)
    keys.paste()
    keys.paste()
    methods = [c[0] for c in bus.calls]
    assert methods.count("CreateSession") == 2 and methods.count("Start") == 2 and methods.count("Stop") == 2
    first = [c[1] for c in bus.calls if c[0] == "NotifyKeyboardKeycode"][:4]
    assert first == [(KEY_LEFTCTRL, True), (KEY_V, True), (KEY_V, False), (KEY_LEFTCTRL, False)]


def test_type_text_copies_then_pastes():
    bus, ran = Bus(), []
    keys = MutterKeys(call=bus, run=lambda cmd, **kw: ran.append(cmd), sleep=lambda s: None)
    keys.type_text("-hello")
    assert ran == [["wl-copy", "--", "-hello"]] and any(c[0] == "NotifyKeyboardKeycode" for c in bus.calls)


def test_failed_start_still_tries_to_stop_and_the_next_paste_works():
    state = {"fail": True}
    calls = []

    def call(service, path, interface, method, signature="", args=()):
        calls.append(method)
        if method == "Start" and state["fail"]:
            raise RuntimeError("denied")
        return "/s"
    keys = MutterKeys(call=call, sleep=lambda s: None)
    with pytest.raises(RuntimeError):
        keys.paste()
    assert calls[-1] == "Stop"
    state["fail"] = False
    keys.paste()


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


def test_portal_paths_and_uris():
    from gguf_dictate.platform.portal import ScreenshotError, request_path, uri_to_path
    assert request_path(":1.42", "tok") == "/org/freedesktop/portal/desktop/request/1_42/tok"
    assert uri_to_path("file:///home/me/Pictures/Screen%20shot.png") == "/home/me/Pictures/Screen shot.png"
    with pytest.raises(ScreenshotError):
        uri_to_path("https://example.com/x.png")


def test_read_and_remove_deletes_the_file(tmp_path):
    from gguf_dictate.platform.portal import read_and_remove
    f = tmp_path / "s.png"
    f.write_bytes(b"png")
    assert read_and_remove(str(f)) == b"png" and not f.exists()


def test_crop_rect_picks_the_monitor_out_of_the_desktop_image():
    from PySide6.QtCore import QRect

    from gguf_dictate.ui.snip import crop_rect
    desktop = QRect(0, 0, 3840, 1080)
    assert crop_rect(desktop, QRect(1920, 0, 1920, 1080), 3840) == QRect(1920, 0, 1920, 1080)
    assert crop_rect(desktop, QRect(1920, 0, 1920, 1080), 7680) == QRect(3840, 0, 3840, 2160)      # image at 2x
