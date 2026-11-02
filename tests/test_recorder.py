"""Recorder (preroll ring buffer + levels) and the sounddevice source, tested with fakes: no mic needed."""
import sys
import types

import numpy as np
import pytest

from gguf_dictate.core.recorder import PREROLL_S, Recorder
from gguf_dictate.core.state import RATE

PRE = int(PREROLL_S * RATE)


class FakeSource:
    def __init__(self):
        self.events, self.callback = [], None

    def open(self, callback):
        self.events.append("open")
        self.callback = callback

    def close(self):
        self.events.append("close")
        self.callback = None


def chunk(value, n=320):
    return np.full(n, value, np.float32)


def make(lazy=False):
    src, levels = FakeSource(), []
    return Recorder(src, on_level=levels.append, lazy=lazy), src, levels


def test_preroll_default_is_a_quarter_second():
    assert PREROLL_S == 0.25 and PRE == 4000


def test_stop_without_start_returns_empty():
    rec, _, _ = make()
    assert rec.stop().size == 0


def test_audio_before_start_is_trimmed_to_preroll_and_prepended():
    rec, _, _ = make()
    for v in (0.1, 0.2, 0.3):                  # 3 x 320 samples, all inside the preroll window
        rec.feed(chunk(v))
    rec.start()
    rec.feed(chunk(0.9))
    audio = rec.stop()
    assert audio.dtype == np.float32
    assert len(audio) == 4 * 320
    assert np.allclose(audio[:320], 0.1) and np.allclose(audio[-320:], 0.9)


def test_preroll_drops_oldest_samples():
    rec, _, _ = make()
    rec.feed(chunk(0.1, PRE))                  # fills the window
    rec.feed(chunk(0.2, 1000))                 # pushes 1000 old samples out
    rec.start()
    audio = rec.stop()
    assert len(audio) == PRE
    assert np.allclose(audio[:PRE - 1000], 0.1) and np.allclose(audio[-1000:], 0.2)


def test_levels_reported_only_while_recording_as_rms():
    rec, _, levels = make()
    rec.feed(chunk(0.5))
    assert levels == []
    rec.start()
    rec.feed(chunk(0.5))
    rec.feed(np.array([0.3, -0.3, 0.3, -0.3], np.float32))
    rec.stop()
    rec.feed(chunk(0.5))
    assert levels == pytest.approx([0.5, 0.3])


def test_second_recording_does_not_include_first_recording_audio_beyond_preroll():
    rec, _, _ = make()
    rec.start()
    rec.feed(chunk(0.9, 16000))                 # one second of first take
    rec.stop()
    rec.start()                                 # immediate re-press
    audio = rec.stop()
    assert len(audio) == PRE and np.allclose(audio, 0.9)   # preroll = tail of what just happened, not the whole old take


def test_audio_after_stop_goes_back_to_preroll():
    rec, _, _ = make()
    rec.start()
    rec.stop()
    rec.feed(chunk(0.4))
    rec.start()
    assert np.allclose(rec.stop(), 0.4)


def test_not_lazy_opens_source_immediately_and_never_closes_on_stop():
    rec, src, _ = make(lazy=False)
    rec.start()
    rec.stop()
    assert src.events == ["open"]


def test_lazy_opens_on_start_and_closes_on_stop():
    rec, src, _ = make(lazy=True)
    assert src.events == []
    rec.start()
    assert src.events == ["open"]
    src.callback(chunk(0.5))                    # source feeds the recorder through the callback
    audio = rec.stop()
    assert src.events == ["open", "close"] and len(audio) == 320


def test_non_lazy_source_callback_is_feed():
    rec, src, _ = make()
    rec.start()
    src.callback(chunk(0.7))
    assert np.allclose(rec.stop(), 0.7)


# --- SoundDeviceSource ------------------------------------------------------

@pytest.fixture
def fake_sd(monkeypatch):
    mod = types.ModuleType("sounddevice")
    mod.made = []

    class InputStream:
        def __init__(self, **kw):
            self.kw, self.started, self.closed = kw, False, False
            mod.made.append(self)

        def start(self):
            self.started = True

        def stop(self):
            self.started = False

        def close(self):
            self.closed = True

    mod.InputStream = InputStream
    monkeypatch.setitem(sys.modules, "sounddevice", mod)
    return mod


def test_sounddevice_source_opens_mono_float32_16k_20ms_blocks(fake_sd):
    from gguf_dictate.platform.audio import SoundDeviceSource
    got = []
    src = SoundDeviceSource()
    src.open(got.append)
    s, = fake_sd.made
    assert s.started and (s.kw["samplerate"], s.kw["channels"], s.kw["dtype"], s.kw["blocksize"]) == (RATE, 1, "float32", 320)
    indata = np.arange(320, dtype=np.float32).reshape(320, 1)
    s.kw["callback"](indata, 320, None, None)
    assert got[0].shape == (320,) and np.array_equal(got[0], indata[:, 0])
    indata[:] = 0
    assert got[0][-1] == 319                    # callback must copy: PortAudio reuses its buffer


def test_sounddevice_source_close_stops_and_closes_stream(fake_sd):
    from gguf_dictate.platform.audio import SoundDeviceSource
    src = SoundDeviceSource()
    src.open(lambda c: None)
    src.close()
    s, = fake_sd.made
    assert not s.started and s.closed
    src.close()                                 # idempotent


def test_sounddevice_source_reopen_makes_new_stream(fake_sd):
    from gguf_dictate.platform.audio import SoundDeviceSource
    src = SoundDeviceSource()
    src.open(lambda c: None)
    src.close()
    src.open(lambda c: None)
    assert len(fake_sd.made) == 2


def test_sounddevice_missing_gives_helpful_error(monkeypatch):
    from gguf_dictate.platform.audio import SoundDeviceSource
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    with pytest.raises(RuntimeError, match="sounddevice"):
        SoundDeviceSource().open(lambda c: None)
