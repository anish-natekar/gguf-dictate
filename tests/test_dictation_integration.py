"""Headless end-to-end: key events -> recorder -> (fake) model -> typed text / voice note. No mic, display or GPU."""
import numpy as np
import pytest

from gguf_dictate.core.dictation import Dictation
from gguf_dictate.core.recorder import Recorder
from gguf_dictate.core.state import RATE


class FakeSource:
    callback = None

    def open(self, callback):
        self.callback = callback

    def close(self):
        self.callback = None


class FakeModel:
    def __init__(self, text="hello world"):
        self.text, self.heard, self.queue = text, [], []

    def run(self, audio):
        self.heard.append(audio)
        text = self.queue.pop(0) if self.queue else self.text
        return type("R", (), {"text": f"  {text}  "})()


class FakeKeys:
    def __init__(self):
        self.typed = []

    def type_text(self, text):
        self.typed.append(text)


class Rig:
    def __init__(self, text="hello world", editor=False, no_space=False):
        self.source, self.model, self.keys = FakeSource(), FakeModel(text), FakeKeys()
        self.sent, self.logs, self.jobs, self.editor = [], [], [], editor
        self.mic = Recorder(self.source, on_level=lambda lvl: self.sent.append("lvl"))
        self.d = Dictation(self.model, self.mic, self.keys, self.sent.append, lambda: self.editor, "f9", "ctrl+alt+s", "ctrl+alt+v",
                           no_space=no_space, log=self.logs.append, spawn=lambda fn, *a: self.jobs.append((fn, a)), sleep=lambda s: None)

    def speak(self, seconds=1.0, level=0.3):
        self.d.router.press("f9")
        for _ in range(int(seconds * 50)):
            self.source.callback(np.full(RATE // 50, level, np.float32))
        self.d.router.release("f9")

    def finish(self):
        jobs, self.jobs = self.jobs, []
        for fn, a in jobs:
            fn(*a)


def test_hold_key_speak_release_types_transcript_with_trailing_space():
    r = Rig()
    r.speak()
    r.finish()
    assert r.keys.typed == ["hello world "]
    assert [s for s in r.sent if s != "lvl"] == ["rec", "busy", "idle"] and "lvl" in r.sent


def test_model_hears_normalised_float32_audio_including_preroll():
    r = Rig()
    r.source.callback(np.full(RATE // 5, 0.3, np.float32))     # 0.2 s before the key: only the last 0.25 s is kept
    r.speak(seconds=1.0, level=0.3)
    r.finish()
    heard, = r.model.heard
    assert heard.dtype == np.float32 and len(heard) == int(0.2 * RATE) + RATE
    assert float(np.abs(heard).max()) == pytest.approx(0.7)    # quiet mic boosted


def test_no_space_option():
    r = Rig(no_space=True)
    r.speak()
    r.finish()
    assert r.keys.typed == ["hello world"]


def test_editor_open_routes_transcript_to_voice_note_not_typing():
    r = Rig(editor=True)
    r.speak()
    r.finish()
    assert r.keys.typed == [] and "note hello world" in r.sent


def test_silent_mic_is_reported_and_skips_model():
    r = Rig()
    r.speak(level=0.0001)
    r.finish()
    assert r.model.heard == [] and r.keys.typed == []
    assert any("silent" in m for m in r.logs) and r.sent[-1] == "idle"


def test_accidental_tap_is_ignored():
    r = Rig()
    r.speak(seconds=0.05)
    r.finish()
    assert r.model.heard == [] and any("too short" in m for m in r.logs) and r.sent[-1] == "idle"


def test_empty_transcript_types_nothing():
    r = Rig(text="")
    r.speak()
    r.finish()
    assert r.keys.typed == [] and r.sent[-1] == "idle"


def test_two_utterances_in_a_row_are_typed_in_order_and_overlay_hides_once_at_end():
    r = Rig()
    r.model.queue = ["one", "two"]
    r.speak()
    r.speak()
    r.finish()
    assert r.keys.typed == ["one ", "two "]
    assert r.sent.count("idle") == 1 and r.sent[-1] == "idle"


def test_speak_button_records_without_key_and_is_not_ended_by_key_events():
    r = Rig()
    r.d.state.begin("button")
    r.d.router.press("x")
    r.d.router.release("x")
    assert r.d.state.active
    for _ in range(50):
        r.source.callback(np.full(RATE // 50, 0.3, np.float32))
    r.d.state.end()
    r.finish()
    assert r.keys.typed == ["hello world "]


def test_model_crash_does_not_wedge_later_dictation():
    r = Rig()
    boom = {"on": True}
    real = r.model.run

    def flaky(audio):
        if boom["on"]:
            raise RuntimeError("gpu hiccup")
        return real(audio)
    r.model.run = flaky
    r.speak()
    with pytest.raises(RuntimeError):
        r.finish()
    assert r.sent[-1] == "idle" and r.d.state.pending == 0
    boom["on"] = False
    r.speak()
    r.finish()
    assert r.keys.typed == ["hello world "]


def test_snip_and_paste_hotkeys_reach_the_overlay_channel():
    r = Rig()
    for k in ("ctrl_l", "alt_l", "s"):
        r.d.router.press(k)
    for k in ("s", "alt_l", "ctrl_l"):
        r.d.router.release(k)
    for k in ("ctrl_l", "alt_l", "v"):
        r.d.router.press(k)
    r.d.router.release("v")
    assert [s for s in r.sent if s in ("snip", "paste")] == ["snip", "paste"]


def test_log_lines_for_recording_and_cancel():
    r = Rig(editor=True)
    r.d.router.press("f9")
    r.d.router.release("f9")
    r.d.router.press("esc")
    assert "recording..." in r.logs and any("Esc" in m for m in r.logs) and "cancel" in r.sent
