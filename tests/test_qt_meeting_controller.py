"""Meeting controller: record / pause / stop, the pill, the library window and startup recovery, with fakes."""
import os
from datetime import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from gguf_dictate.core.meeting_recorder import MeetingRecorder  # noqa: E402
from gguf_dictate.core.meetings import Library  # noqa: E402
from gguf_dictate.ui.meeting import MeetingController  # noqa: E402


class Source:
    def __init__(self, fail=None):
        self.fail, self.cb, self.closed = fail, None, False

    def open(self, cb):
        if self.fail:
            raise RuntimeError(self.fail)
        self.cb = cb

    def close(self):
        self.closed = True


class Sig:
    def __init__(self):
        self.fns = []

    def connect(self, fn):
        self.fns.append(fn)

    def emit(self, *a):
        for fn in self.fns:
            fn(*a)


class Pill:
    instances = []

    def __init__(self, pos=None):
        self.pos, self.elapsed, self.paused, self.shown, self.closed = pos, None, False, False, False
        self.record_clicked, self.pause_clicked, self.stop_clicked, self.cancel_clicked, self.moved = Sig(), Sig(), Sig(), Sig(), Sig()
        self.recording = False
        Pill.instances.append(self)

    def set_elapsed(self, s):
        self.elapsed = s

    def set_recording(self, r):
        self.recording = r

    def set_paused(self, p):
        self.paused = p

    def show(self):
        self.shown = True

    def close(self):
        self.closed = True


class Window:
    instances = []

    def __init__(self, library, transcribe=None):
        self.transcribe, self.shown, self.refreshed = transcribe, 0, 0
        Window.instances.append(self)

    def show(self):
        self.shown += 1

    def raise_(self):
        pass

    def activateWindow(self):
        pass

    def refresh(self):
        self.refreshed += 1

    def set_transcribe(self, fn):
        self.transcribe = fn


class Rig:
    def __init__(self, tmp_path, mic=None, system=None):
        Pill.instances, Window.instances = [], []
        self.lib = Library(tmp_path)
        self.mic, self.system = mic or Source(), system or Source()
        self.toasts, self.cfg, self.answer, self.asked = [], {}, True, []
        self.errors = []
        self.ctl = MeetingController(
            self.lib,
            make_recorder=lambda lib: MeetingRecorder(lib, self.mic, self.system, clock=lambda: datetime(2026, 11, 3, 9, 30)),
            make_pill=lambda pos: Pill(pos),
            make_window=lambda lib, transcribe: Window(lib, transcribe),
            toast=lambda t, b: self.toasts.append((t, b)),
            show_error=lambda t, b: self.errors.append((t, b)),
            load_cfg=lambda: dict(self.cfg),
            save_cfg=lambda c: self.cfg.update(c),
            confirm_discard=lambda: self.asked.append(1) or self.answer,
        )

    def begin(self):
        """Hotkey (pill appears), then the record button."""
        self.ctl.toggle()
        Pill.instances[-1].record_clicked.emit()

    def speak(self, seconds=1.0):
        import numpy as np
        self.mic.cb(np.full(int(16000 * seconds), 0.1, np.float32))


@pytest.fixture
def rig(qapp, tmp_path):
    r = Rig(tmp_path)
    yield r
    r.ctl.shutdown()


def test_toggle_shows_the_pill_but_records_nothing_yet(rig):
    rig.ctl.toggle()
    assert rig.ctl.active and not rig.ctl.recording and Pill.instances[0].shown and not Pill.instances[0].recording
    assert rig.lib.all() == [] and rig.mic.cb is None


def test_record_button_starts_the_meeting(rig):
    rig.begin()
    assert rig.ctl.recording and Pill.instances[0].recording
    assert rig.lib.all()[0].status == "recording"


def test_toggle_on_an_unused_pill_dismisses_it_without_a_meeting(rig):
    rig.ctl.toggle()
    rig.ctl.toggle()
    assert not rig.ctl.active and Pill.instances[0].closed and rig.lib.all() == [] and not rig.toasts


def test_pressing_record_twice_makes_one_meeting(rig):
    rig.begin()
    Pill.instances[0].record_clicked.emit()
    assert len(rig.lib.all()) == 1


def test_toggle_again_stops_and_saves(rig):
    rig.begin()
    rig.speak(2.0)
    Pill.instances[0].stop_clicked.emit()
    m = rig.lib.all()[0]
    assert not rig.ctl.recording and m.status == "saved" and m.duration == pytest.approx(2.0)
    assert Pill.instances[0].closed and "saved" in rig.toasts[-1][0].lower()


def test_pill_shows_elapsed_time_while_recording(rig):
    rig.begin()
    rig.speak(3.0)
    rig.ctl.tick()
    assert Pill.instances[0].elapsed == pytest.approx(3.0)


def test_pill_buttons_pause_and_save(rig):
    rig.begin()
    pill = Pill.instances[0]
    pill.pause_clicked.emit()
    assert pill.paused and rig.ctl.recorder.paused
    rig.speak(1.0)
    pill.pause_clicked.emit()
    assert not pill.paused and not rig.ctl.recorder.paused
    pill.stop_clicked.emit()
    assert not rig.ctl.recording


def test_pill_position_is_remembered_and_restored(rig):
    rig.ctl.toggle()
    Pill.instances[0].moved.emit(40, 60)
    rig.ctl.toggle()
    assert rig.cfg["pill_pos"] == [40, 60]
    rig.ctl.toggle()
    assert Pill.instances[1].pos == (40, 60)


def test_first_pill_has_no_saved_position(rig):
    rig.ctl.toggle()
    assert Pill.instances[0].pos is None


def test_start_failure_shows_an_error_and_leaves_nothing_behind(qapp, tmp_path):
    r = Rig(tmp_path, mic=Source(fail="no microphone"))
    r.ctl.toggle()
    Pill.instances[0].record_clicked.emit()
    assert not r.ctl.recording and r.errors and "no microphone" in r.errors[0][1]
    assert r.lib.all() == [] and r.ctl.active and not Pill.instances[0].recording      # still ready to try again


def test_system_audio_failure_continues_with_a_warning_toast(qapp, tmp_path):
    r = Rig(tmp_path, system=Source(fail="no wpctl"))
    r.ctl.toggle()
    Pill.instances[0].record_clicked.emit()
    assert r.ctl.recording and any("system audio" in b for _, b in r.toasts)
    r.ctl.shutdown()


def test_window_opens_once_and_is_reused(rig):
    rig.ctl.show_window()
    rig.ctl.show_window()
    assert len(Window.instances) == 1 and Window.instances[0].shown == 2


def test_window_refreshes_when_a_meeting_is_saved(rig):
    rig.ctl.show_window()
    rig.begin()
    rig.speak()
    rig.ctl.toggle()
    assert Window.instances[0].refreshed >= 1


def test_transcribe_is_unavailable_until_a_model_arrives(rig):
    rig.ctl.show_window()
    assert Window.instances[0].transcribe is None
    rig.ctl.set_model(type("M", (), {"run": lambda self, a: type("R", (), {"text": "hi"})()})())
    assert callable(Window.instances[0].transcribe)
    rig.ctl.set_model(None)
    assert Window.instances[0].transcribe is None


def test_model_set_before_the_window_exists_reaches_it(rig):
    rig.ctl.set_model(type("M", (), {"run": lambda self, a: type("R", (), {"text": "hi"})()})())
    rig.ctl.show_window()
    assert callable(Window.instances[0].transcribe)


def test_transcribe_runs_the_shared_model_over_a_recording(rig):
    class Model:
        def run(self, audio):
            return type("R", (), {"text": "hello there"})()

    rig.ctl.set_model(Model())
    rig.ctl.show_window()
    rig.begin()
    import numpy as np
    rig.mic.cb(np.full(16000 * 3, 0.3, np.float32))
    rig.ctl.toggle()
    m = rig.lib.all()[0]
    Window.instances[0].transcribe(m, lambda f: None, lambda: False)
    assert rig.lib.get(m.id).status == "transcribed" and rig.lib.transcript(m)[0]["text"] == "hello there"


def test_start_without_a_pill_does_nothing(rig):
    rig.ctl.start()
    assert rig.lib.all() == [] and not rig.ctl.recording


def test_recover_saves_interrupted_meetings_and_says_so(rig):
    m = rig.lib.create(datetime(2026, 11, 2, 8, 0))
    import numpy as np

    from gguf_dictate.core.meeting_recorder import WavWriter
    w = WavWriter(m.mic_path)
    w.write(np.full(16000, 0.1, np.float32))
    w.patch()
    rig.ctl.recover()
    assert rig.lib.get(m.id).status == "saved" and rig.toasts and "recovered" in rig.toasts[-1][0].lower()


def test_recover_is_quiet_when_there_is_nothing_to_recover(rig):
    rig.ctl.recover()
    assert rig.toasts == []


def test_shutdown_while_recording_saves_the_meeting(rig):
    rig.begin()
    rig.speak(1.0)
    rig.ctl.shutdown()
    assert rig.lib.all()[0].status == "saved"


def test_changed_fires_on_start_and_stop(rig):
    seen = []
    rig.ctl.changed.connect(lambda: seen.append((rig.ctl.active, rig.ctl.recording)))
    rig.begin()
    Pill.instances[0].stop_clicked.emit()
    assert seen == [(True, False), (True, True), (False, False)]


def test_hotkey_while_recording_leaves_the_pill_and_recording_alone(rig):
    rig.begin()
    rig.speak(1.0)
    rig.ctl.toggle()
    rig.ctl.toggle()
    pill = Pill.instances[0]
    assert rig.ctl.recording and rig.ctl.active and not pill.closed and len(Pill.instances) == 1
    assert rig.lib.all()[0].status == "recording"


def test_cancel_on_a_ready_pill_just_closes_it_without_asking(rig):
    rig.ctl.toggle()
    Pill.instances[0].cancel_clicked.emit()
    assert not rig.ctl.active and Pill.instances[0].closed and rig.asked == [] and rig.lib.all() == []


def test_cancel_while_recording_asks_then_discards_the_meeting_and_audio(rig):
    rig.begin()
    rig.speak(2.0)
    folder = rig.lib.all()[0].mic_path.parent
    Pill.instances[0].cancel_clicked.emit()
    assert rig.asked == [1] and not rig.ctl.active and Pill.instances[0].closed
    assert rig.lib.all() == [] and not folder.exists() and rig.mic.closed
    assert "discarded" in rig.toasts[-1][0].lower()


def test_declining_the_discard_keeps_recording(rig):
    rig.answer = False
    rig.begin()
    rig.speak(1.0)
    Pill.instances[0].cancel_clicked.emit()
    assert rig.ctl.recording and not Pill.instances[0].closed and len(rig.lib.all()) == 1
    rig.speak(1.0)
    assert rig.ctl.recorder.elapsed == pytest.approx(2.0)


def test_can_record_again_after_cancelling(rig):
    rig.begin()
    Pill.instances[0].cancel_clicked.emit()
    rig.begin()
    assert rig.ctl.recording and len(rig.lib.all()) == 1
