"""App wiring: one process, model loading, tray state, commands from the overlay, restart on settings. Everything external is faked."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

pytest.importorskip("PySide6")
from gguf_dictate import config  # noqa: E402
from gguf_dictate.app import App  # noqa: E402
from gguf_dictate.core.state import RATE  # noqa: E402


class Source:
    callback = None

    def open(self, cb):
        self.callback = cb

    def close(self):
        self.callback = None


class Model:
    def run(self, audio):
        return type("R", (), {"text": " hi there "})()


class Keys:
    def __init__(self):
        self.typed = []

    def type_text(self, t):
        self.typed.append(t)


class Listener:
    def __init__(self, router):
        self.router, self.stopped = router, False

    def stop(self):
        self.stopped = True


class Overlay:
    def __init__(self):
        self.msgs = []

    def post(self, m):
        self.msgs.append(m)


class Tray:
    def __init__(self):
        self.states = []

    def set_state(self, s):
        self.states.append(s)

    def refresh(self):
        pass


class Snip:
    def __init__(self):
        self.log, self.open = [], False

    def editor_open(self):
        return self.open

    def count(self):
        return 0

    def __getattr__(self, name):
        return lambda *a: self.log.append((name, *a))


class Rig:
    def __init__(self, tmp_path, monkeypatch, loader=None, with_model=True):
        monkeypatch.setattr(config, "config_file", lambda: tmp_path / "config.json")
        self.model_file = tmp_path / "m.gguf"
        self.model_file.write_bytes(b"x")
        if with_model:
            config.save_config({"model": str(self.model_file), "hotkey": "f8"}, tmp_path / "config.json")
        self.source, self.keys, self.overlay, self.tray, self.snip = Source(), Keys(), Overlay(), Tray(), Snip()
        self.listeners, self.errors, self.opened_settings, self.quit = [], [], [], []
        self.loads = []

        def load(path):
            self.loads.append(path)
            return loader(path) if loader else Model()
        self.app = App(load_model=load, source=lambda: self.source, keys=self.keys, snip=self.snip, overlay=self.overlay, tray=self.tray,
                       start_listener=lambda router: self.listeners.append(Listener(router)) or self.listeners[-1],
                       show_error=lambda t, m: self.errors.append((t, m)), open_settings=lambda: self.opened_settings.append(1),
                       quit_app=lambda: self.quit.append(1), log=lambda m: None)


@pytest.fixture
def rig(tmp_path, monkeypatch, qtbot):
    return Rig(tmp_path, monkeypatch)


def test_no_model_configured_opens_settings_and_stays_stopped(tmp_path, monkeypatch, qtbot):
    r = Rig(tmp_path, monkeypatch, with_model=False)
    r.app.start()
    assert r.opened_settings and r.app.state == "stopped" and not r.loads


def test_start_loads_model_then_runs_with_listener_on_configured_hotkey(rig, qtbot):
    rig.app.start()
    assert rig.app.state == "loading" and rig.tray.states[-1] == "loading"
    qtbot.waitUntil(lambda: rig.app.state == "running", timeout=3000)
    assert rig.tray.states[-2:] == ["loading", "running"] and len(rig.listeners) == 1
    assert rig.listeners[0].router.state is rig.app.dictation.state
    assert rig.loads == [str(rig.model_file)]


def test_load_failure_returns_to_stopped_and_reports(tmp_path, monkeypatch, qtbot):
    def boom(_):
        raise RuntimeError("bad gguf")
    r = Rig(tmp_path, monkeypatch, loader=boom)
    r.app.start()
    qtbot.waitUntil(lambda: bool(r.errors), timeout=3000)
    assert r.app.state == "stopped" and "bad gguf" in r.errors[0][1] and not r.listeners


def test_dictation_flows_through_single_process(rig, qtbot):
    rig.app.start()
    qtbot.waitUntil(lambda: rig.app.state == "running", timeout=3000)
    rig.app.speak("start")
    for _ in range(50):
        rig.source.callback(np.full(RATE // 50, 0.3, np.float32))
    rig.app.speak("stop")
    qtbot.waitUntil(lambda: bool(rig.keys.typed), timeout=3000)
    assert rig.keys.typed == ["hi there "] and "rec" in rig.overlay.msgs and "busy" in rig.overlay.msgs


def test_voice_note_when_editor_open(rig, qtbot):
    rig.app.start()
    qtbot.waitUntil(lambda: rig.app.state == "running", timeout=3000)
    rig.snip.open = True
    rig.app.speak("start")
    for _ in range(50):
        rig.source.callback(np.full(RATE // 50, 0.3, np.float32))
    rig.app.speak("stop")
    qtbot.waitUntil(lambda: "note hi there" in rig.overlay.msgs, timeout=3000)
    assert rig.keys.typed == []


def test_stop_releases_listener_and_mic_then_start_again(rig, qtbot):
    rig.app.start()
    qtbot.waitUntil(lambda: rig.app.state == "running", timeout=3000)
    rig.app.toggle()
    assert rig.app.state == "stopped" and rig.listeners[0].stopped and rig.source.callback is None
    rig.app.toggle()
    qtbot.waitUntil(lambda: rig.app.state == "running" and len(rig.listeners) == 2, timeout=3000)


def test_stale_load_after_stop_is_discarded(tmp_path, monkeypatch, qtbot):
    import threading
    gate = threading.Event()

    def slow(_):
        gate.wait(3)
        return Model()
    r = Rig(tmp_path, monkeypatch, loader=slow)
    r.app.start()
    r.app.stop()
    gate.set()
    qtbot.wait(300)
    assert r.app.state == "stopped" and not r.listeners


@pytest.mark.parametrize("msg,expected", [("snip", "start"), ("cancel", "cancel"), ("paste", "paste_all"), ("ctrlv", "ctrl_v"), ("note hello", "note")])
def test_overlay_commands_route_to_snip(rig, msg, expected):
    rig.app.on_command(msg)
    assert rig.snip.log[-1][0] == expected
    if expected == "note":
        assert rig.snip.log[-1] == ("note", "hello")


def test_snip_command_passes_configured_colours(rig):
    config.save_config({"colors": [["Red", "#ff0000"]]}, config.config_file())
    rig.app.on_command("snip")
    assert rig.snip.log[-1] == ("start", [["Red", "#ff0000"]])


def test_set_model_saves_config_and_restarts(rig, qtbot, tmp_path):
    other = tmp_path / "o.gguf"
    other.write_bytes(b"x")
    rig.app.start()
    qtbot.waitUntil(lambda: rig.app.state == "running", timeout=3000)
    rig.app.set_model(str(other))
    assert config.load_config()["model"] == str(other) and config.load_config()["recent"][0] == str(other)
    qtbot.waitUntil(lambda: rig.loads[-1] == str(other) and rig.app.state == "running", timeout=3000)
    assert rig.listeners[0].stopped


def test_quit_stops_everything(rig, qtbot):
    rig.app.start()
    qtbot.waitUntil(lambda: rig.app.state == "running", timeout=3000)
    rig.app.quit()
    assert rig.listeners[0].stopped and rig.quit == [1] and rig.app.state == "stopped"


class Meetings:
    def __init__(self):
        self.log = []

    def set_model(self, m):
        self.log.append(("model", m is not None))

    def toggle(self):
        self.log.append(("toggle",))

    def show_window(self):
        self.log.append(("window",))

    def shutdown(self):
        self.log.append(("shutdown",))


@pytest.fixture
def mrig(tmp_path, monkeypatch, qtbot):
    r = Rig(tmp_path, monkeypatch)
    r.meetings = r.app.meetings = Meetings()
    return r


def test_meeting_command_toggles_recording(mrig):
    mrig.app.on_command("meeting")
    mrig.app.toggle_meeting()
    mrig.app.show_meetings()
    assert mrig.meetings.log == [("toggle",), ("toggle",), ("window",)]


def test_meeting_hotkey_reaches_the_overlay_channel(mrig, qtbot):
    mrig.app.start()
    qtbot.waitUntil(lambda: mrig.app.state == "running", timeout=3000)
    router = mrig.listeners[0].router
    for k in ("f8",):
        router.press(k)
    assert "meeting" in mrig.overlay.msgs


def test_model_goes_to_meetings_on_load_and_is_withdrawn_on_stop(mrig, qtbot):
    mrig.app.start()
    qtbot.waitUntil(lambda: mrig.app.state == "running", timeout=3000)
    mrig.app.stop()
    assert mrig.meetings.log == [("model", True), ("model", False)]


def test_quit_stops_a_meeting_in_progress(mrig):
    mrig.app.quit()
    assert ("shutdown",) in mrig.meetings.log and mrig.quit


def test_everything_still_works_without_meetings(rig):
    rig.app.on_command("meeting")
    rig.app.toggle_meeting()
    rig.app.show_meetings()
    rig.app.quit()
    assert rig.quit
