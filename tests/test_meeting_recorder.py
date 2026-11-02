import wave
from datetime import datetime

import numpy as np
import pytest

from gguf_dictate.core.meeting_recorder import MeetingRecorder, repair
from gguf_dictate.core.meetings import Library

RATE = 16000
T = datetime(2026, 11, 3, 14, 30)


class FakeSource:
    def __init__(self, fail=False):
        self.fail, self.cb, self.opened, self.closed = fail, None, 0, 0

    def open(self, callback):
        if self.fail:
            raise RuntimeError("no such device")
        self.cb, self.opened = callback, self.opened + 1

    def close(self):
        self.closed += 1

    def say(self, seconds, value=0.1):
        self.cb(np.full(int(seconds * RATE), value, np.float32))


def read(path):
    with wave.open(str(path)) as w:
        return w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes(), w.readframes(w.getnframes())


@pytest.fixture
def setup(tmp_path):
    lib, mic, system = Library(tmp_path), FakeSource(), FakeSource()
    rec = MeetingRecorder(lib, mic, system, clock=lambda: T)
    return lib, mic, system, rec


def test_records_both_tracks_as_16k_mono_wav(setup):
    lib, mic, system, rec = setup
    m = rec.start()
    mic.say(2)
    system.say(3)
    rec.stop()
    assert read(m.mic_path)[:4] == (RATE, 1, 2, 2 * RATE)
    assert read(m.system_path)[:4] == (RATE, 1, 2, 3 * RATE)
    assert mic.closed == system.closed == 1


def test_stop_saves_meeting_with_duration_of_longest_track(setup):
    lib, mic, system, rec = setup
    m = rec.start()
    mic.say(2)
    system.say(3)
    rec.stop()
    saved = lib.get(m.id)
    assert saved.status == "saved" and saved.duration == pytest.approx(3.0) and saved.start == T


def test_pause_leaves_no_gap_and_resume_continues(setup):
    lib, mic, system, rec = setup
    m = rec.start()
    mic.say(1)
    rec.pause()
    mic.say(5)
    assert rec.paused
    rec.resume()
    mic.say(1)
    rec.stop()
    assert read(m.mic_path)[3] == 2 * RATE


def test_elapsed_counts_recorded_audio_only(setup):
    lib, mic, system, rec = setup
    rec.start()
    mic.say(1.5)
    system.say(0.5)
    assert rec.elapsed == pytest.approx(1.5)
    rec.stop()


def test_loud_samples_are_clipped_not_wrapped(setup):
    lib, mic, system, rec = setup
    m = rec.start()
    mic.cb(np.array([5.0, -5.0, 0.0], np.float32))
    rec.stop()
    samples = np.frombuffer(read(m.mic_path)[4], np.int16)
    assert samples.tolist() == [32767, -32767, 0]


def test_system_failure_keeps_recording_the_mic_and_reports_it(tmp_path):
    lib, mic, system = Library(tmp_path), FakeSource(), FakeSource(fail=True)
    rec = MeetingRecorder(lib, mic, system, clock=lambda: T)
    m = rec.start()
    mic.say(1)
    rec.stop()
    assert "no such device" in rec.warnings[0] and read(m.mic_path)[3] == RATE
    assert not m.system_path.exists()


def test_mic_failure_raises_and_leaves_no_half_meeting(tmp_path):
    lib = Library(tmp_path)
    rec = MeetingRecorder(lib, FakeSource(fail=True), FakeSource(), clock=lambda: T)
    with pytest.raises(RuntimeError):
        rec.start()
    assert lib.all() == []


def test_audio_before_start_or_after_stop_is_ignored(setup):
    lib, mic, system, rec = setup
    m = rec.start()
    mic.say(1)
    cb = mic.cb
    rec.stop()
    cb(np.ones(RATE, np.float32))      # a late callback from the audio thread
    assert read(m.mic_path)[3] == RATE


def test_cannot_start_twice(setup):
    lib, mic, system, rec = setup
    rec.start()
    with pytest.raises(RuntimeError):
        rec.start()
    rec.stop()


def test_levels_reported_for_the_pill(tmp_path):
    levels = []
    lib, mic, system = Library(tmp_path), FakeSource(), FakeSource()
    rec = MeetingRecorder(lib, mic, system, on_level=levels.append, clock=lambda: T)
    rec.start()
    mic.say(0.1, 0.2)
    rec.stop()
    assert levels and levels[0] == pytest.approx(0.2, abs=1e-3)


def test_crash_leaves_audio_recoverable(tmp_path):
    lib, mic, system = Library(tmp_path), FakeSource(), FakeSource()
    rec = MeetingRecorder(lib, mic, system, clock=lambda: T)
    m = rec.start()
    mic.say(2)
    system.say(1)
    # no stop(): the process died here
    fresh = Library(tmp_path)
    assert [x.id for x in fresh.unfinished()] == [m.id]
    assert repair(fresh) == [m.id]
    assert read(m.mic_path)[3] == 2 * RATE and read(m.system_path)[3] == RATE
    saved = fresh.get(m.id)
    assert saved.status == "saved" and saved.duration == pytest.approx(2.0)
    assert repair(fresh) == []


def test_repair_discards_an_empty_recording(tmp_path):
    lib = Library(tmp_path)
    m = lib.create(T)
    assert repair(lib) == []
    assert not m.dir.exists()


def test_repair_resets_a_transcribing_status_left_by_a_crash(tmp_path):
    from gguf_dictate.core.meeting_recorder import repair
    from gguf_dictate.core.meetings import Library
    lib = Library(tmp_path)
    a, b = lib.create(datetime(2026, 11, 3, 9, 0)), lib.create(datetime(2026, 11, 3, 10, 0))
    lib.set_transcript(b, [{"t0": 0, "t1": 1, "speaker": "Me", "text": "x"}])
    lib.set_status(a, "transcribing")
    lib.set_status(b, "transcribing")
    repair(lib)
    assert lib.get(a.id).status == "saved" and lib.get(b.id).status == "transcribed"
