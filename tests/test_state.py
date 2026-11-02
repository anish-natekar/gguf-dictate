"""Dictation state machine, audio gating, text routing and hotkey routing (pure logic, no mic/GUI/keyboard)."""
import numpy as np
import pytest

from gguf_dictate.core.state import RATE, DictationState, HotkeyRouter, prepare_audio, route_text


class FakeMic:
    def __init__(self, audio=None):
        self.calls, self.audio = [], audio if audio is not None else np.ones(RATE, np.float32)

    def start(self):
        self.calls.append("start")

    def stop(self):
        self.calls.append("stop")
        return self.audio


class Harness:
    """Collects notifications and holds spawned work so tests control when it finishes."""

    def __init__(self):
        self.sent, self.processed, self.jobs = [], [], []
        self.mic = FakeMic()
        self.state = DictationState(self.mic, self.sent.append, self.processed.append, spawn=lambda fn, *a: self.jobs.append((fn, a)))

    def run_jobs(self):
        jobs, self.jobs = self.jobs, []
        for fn, a in jobs:
            fn(*a)


@pytest.fixture
def h():
    return Harness()


# --- DictationState ---------------------------------------------------------

def test_begin_starts_mic_once_and_notifies_rec(h):
    h.state.begin("key")
    h.state.begin("key")              # key auto-repeat must not restart the mic
    assert h.mic.calls == ["start"] and h.sent == ["rec"]
    assert h.state.active and h.state.source == "key"


def test_end_without_begin_does_nothing(h):
    h.state.end()
    assert h.sent == [] and h.mic.calls == [] and h.jobs == []


def test_end_stops_mic_notifies_busy_and_queues_work(h):
    h.state.begin("button")
    h.state.end()
    assert h.mic.calls == ["start", "stop"] and h.sent == ["rec", "busy"]
    assert not h.state.active and h.state.pending == 1 and h.state.source == "button"
    h.run_jobs()
    assert len(h.processed) == 1 and h.sent[-1] == "idle" and h.state.pending == 0


def test_idle_not_sent_while_a_new_recording_is_active(h):
    """Regression: a stale 'idle' from an earlier transcription hid the overlay mid-recording."""
    h.state.begin("key")
    h.state.end()
    h.state.begin("key")              # user talks again before the first result is back
    h.run_jobs()
    assert "idle" not in h.sent
    h.state.end()
    h.run_jobs()
    assert h.sent.count("idle") == 1 and h.sent[-1] == "idle"


def test_idle_only_after_all_pending_work_finishes(h):
    for _ in range(2):
        h.state.begin("key")
        h.state.end()
    (first, a1), (second, a2) = h.jobs
    first(*a1)
    assert "idle" not in h.sent and h.state.pending == 1
    second(*a2)
    assert h.sent[-1] == "idle" and h.state.pending == 0


def test_idle_sent_even_if_processing_raises(h):
    def boom(_):
        raise RuntimeError("model died")
    h.state.process = boom
    h.state.begin("key")
    h.state.end()
    with pytest.raises(RuntimeError):
        h.run_jobs()
    assert h.sent[-1] == "idle" and h.state.pending == 0


# --- prepare_audio ----------------------------------------------------------

def test_prepare_rejects_too_short():
    audio, why = prepare_audio(np.ones(int(0.19 * RATE), np.float32))
    assert audio is None and why == "too short"


def test_prepare_rejects_silence():
    audio, why = prepare_audio(np.full(RATE, 0.001, np.float32))
    assert audio is None and why.startswith("silent")


def test_prepare_normalises_quiet_audio_to_0_7_peak():
    audio, why = prepare_audio(np.full(RATE, 0.1, np.float32))
    assert why is None and float(np.abs(audio).max()) == pytest.approx(0.7)


def test_prepare_leaves_loud_audio_untouched():
    src = np.full(RATE, 0.6, np.float32)
    audio, why = prepare_audio(src)
    assert why is None and np.array_equal(audio, src)


def test_prepare_exactly_0_2s_is_accepted():
    audio, why = prepare_audio(np.ones(int(0.2 * RATE), np.float32))
    assert why is None and audio is not None


# --- route_text -------------------------------------------------------------

def test_route_types_with_trailing_space_by_default():
    assert route_text("hello", editor_open=False, no_space=False) == ("type", "hello ")


def test_route_no_space_option():
    assert route_text("hello", editor_open=False, no_space=True) == ("type", "hello")


def test_route_becomes_note_while_editor_open_without_space():
    assert route_text("red button overlaps", editor_open=True, no_space=False) == ("note", "red button overlaps")


def test_route_empty_text_is_dropped():
    assert route_text("", editor_open=False, no_space=False) is None
    assert route_text("", editor_open=True, no_space=False) is None


# --- HotkeyRouter -----------------------------------------------------------

class RouterHarness(Harness):
    def __init__(self, editor_open=False):
        super().__init__()
        self.editor = editor_open
        self.slept = []
        self.router = HotkeyRouter("f9", "ctrl+alt+s", "ctrl+alt+v", self.state, self.sent.append,
                                   editor_open=lambda: self.editor, sleep=self.slept.append)

    def press(self, *names):
        for n in names:
            self.router.press(n)

    def release(self, *names):
        for n in names:
            self.router.release(n)


@pytest.fixture
def r():
    return RouterHarness()


def test_talk_key_hold_and_release_records_then_ends(r):
    r.press("f9")
    r.press("f9")                     # auto-repeat
    assert r.state.active and r.sent == ["rec"]
    r.release("f9")
    assert not r.state.active and r.sent == ["rec", "busy"]


def test_release_of_other_key_does_not_end_recording(r):
    r.press("f9", "a")
    r.release("a")
    assert r.state.active


def test_button_recording_is_not_ended_by_key_release(r):
    r.state.begin("button")
    r.press("x")
    r.release("x")
    assert r.state.active


def test_snip_hotkey_fires_once_while_held(r):
    r.press("ctrl_l", "alt_l", "s")
    r.press("s")
    assert r.sent.count("snip") == 1
    r.release("s")
    r.press("s")
    assert r.sent.count("snip") == 2


def test_paste_all_fires_on_release_after_settle_delay(r):
    r.press("ctrl_l", "alt_l", "v")
    assert "paste" not in r.sent and "ctrlv" not in r.sent
    r.release("v")
    assert r.sent == ["paste"] and r.slept == [0.15]


def test_paste_all_does_not_fire_if_released_before_complete_combo(r):
    r.press("ctrl_l", "v")
    r.release("v")
    assert "paste" not in r.sent


def test_plain_ctrl_v_notifies_ctrlv_but_ctrl_alt_v_does_not(r):
    r.press("ctrl_l", "v")
    assert r.sent == ["ctrlv"]
    r.release("v", "ctrl_l")
    r.press("ctrl_l", "alt_l", "v")
    assert r.sent.count("ctrlv") == 1


def test_esc_cancels_only_while_editor_open(r):
    r.press("esc")
    assert "cancel" not in r.sent
    r.editor = True
    r.press("esc")
    assert r.sent == ["cancel"]


def test_snip_hotkey_can_be_changed():
    r = RouterHarness()
    r.router = HotkeyRouter("ctrl_r", "f10", "f11", r.state, r.sent.append, editor_open=lambda: False, sleep=r.slept.append)
    r.press("f10")
    assert r.sent == ["snip"]
    r.press("ctrl_r")
    assert r.state.active
