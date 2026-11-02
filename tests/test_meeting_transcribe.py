from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pytest

from gguf_dictate.core.meeting_recorder import WavWriter
from gguf_dictate.core.meeting_transcribe import (
    MAX_CHUNK_S,
    Cancelled,
    load_pcm,
    merge,
    speech_regions,
    transcribe_meeting,
    transcribe_track,
)
from gguf_dictate.core.meetings import Library

RATE = 16000


def tone(seconds, amp=0.2):
    t = np.arange(int(seconds * RATE)) / RATE
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def silence(seconds):
    return np.zeros(int(seconds * RATE), np.float32)


def near(region, t0, t1, tol=0.3):
    return abs(region[0] - t0) <= tol and abs(region[1] - t1) <= tol


class FakeRun:
    """Stands in for the model: numbers each clip it is given."""

    def __init__(self, texts=None):
        self.texts, self.lengths = texts, []

    def __call__(self, audio):
        self.lengths.append(len(audio) / RATE)
        n = len(self.lengths)
        return SimpleNamespace(text=self.texts[n - 1] if self.texts else f"  words {n} ")


def test_two_bursts_with_a_long_pause_are_two_regions():
    audio = np.concatenate([silence(1), tone(3), silence(2), tone(2), silence(1)])
    r = speech_regions(audio)
    assert len(r) == 2 and near(r[0], 1, 4) and near(r[1], 6, 8)


def test_short_pauses_do_not_split_a_sentence():
    audio = np.concatenate([tone(2), silence(0.3), tone(2)])
    assert len(speech_regions(audio)) == 1


def test_silence_has_no_regions():
    assert speech_regions(silence(10)) == [] and speech_regions(np.zeros(0, np.float32)) == []


def test_long_speech_is_cut_into_clips_of_at_most_the_limit_in_a_quiet_spot():
    audio = np.concatenate([tone(17), tone(0.3, 0.0005), tone(43)])
    r = speech_regions(audio)
    assert all(b - a <= MAX_CHUNK_S + 0.01 for a, b in r) and len(r) >= 3
    assert abs(r[0][1] - 17.15) < 0.4      # the first cut lands in the dip, not mid-word
    assert all(r[i][1] == r[i + 1][0] for i in range(len(r) - 1))      # no audio lost between cuts
    assert r[0][0] < 0.2 and r[-1][1] > 59.8


def test_loud_and_quiet_speakers_are_both_found():
    audio = np.concatenate([tone(2, 0.4), silence(1.5), tone(2, 0.02)])
    assert len(speech_regions(audio)) == 2


def test_transcribe_track_offsets_labels_and_drops_empty_text():
    audio = np.concatenate([silence(1), tone(2), silence(2), tone(2)])
    run = FakeRun(["hello there", "   "])
    segs = transcribe_track(run, audio, "Them")
    assert len(segs) == 1 and segs[0]["speaker"] == "Them" and segs[0]["text"] == "hello there"
    assert near((segs[0]["t0"], segs[0]["t1"]), 1, 3)


def test_transcribe_track_reports_progress_and_honours_cancel():
    audio = np.concatenate([tone(1), silence(2), tone(1), silence(2), tone(1)])
    seen = []
    transcribe_track(FakeRun(), audio, "Me", progress=seen.append)
    assert seen == sorted(seen) and seen[-1] == pytest.approx(1.0) and len(seen) == 3
    with pytest.raises(Cancelled):
        transcribe_track(FakeRun(), audio, "Me", cancelled=lambda: True)


def test_merge_orders_by_time_across_speakers():
    me = [{"t0": 0.0, "t1": 1, "speaker": "Me", "text": "a"}, {"t0": 9.0, "t1": 10, "speaker": "Me", "text": "c"}]
    them = [{"t0": 4.0, "t1": 5, "speaker": "Them", "text": "b"}]
    assert [s["text"] for s in merge(me, them)] == ["a", "b", "c"]


def test_load_pcm_reads_streamed_wav_without_loading_it_all(tmp_path):
    w = WavWriter(tmp_path / "a.wav")
    w.write(tone(1))
    w.close()
    pcm = load_pcm(tmp_path / "a.wav")
    assert len(pcm) == RATE and pcm.dtype == np.int16
    assert len(load_pcm(tmp_path / "missing.wav")) == 0


def test_load_pcm_rejects_other_sample_rates(tmp_path):
    import wave
    with wave.open(str(tmp_path / "b.wav"), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(44100)
        f.writeframes(b"\0\0" * 10)
    with pytest.raises(ValueError):
        load_pcm(tmp_path / "b.wav")


def meeting_with(tmp_path, mic, system):
    lib = Library(tmp_path)
    m = lib.create(datetime(2026, 11, 3, 14, 30))
    for path, audio in ((m.mic_path, mic), (m.system_path, system)):
        if audio is not None:
            w = WavWriter(path)
            w.write(audio)
            w.close()
    lib.finish(m, 10)
    return lib, m


def test_transcribe_meeting_saves_a_merged_me_and_them_transcript(tmp_path):
    mic = np.concatenate([tone(2), silence(8)])
    system = np.concatenate([silence(5), tone(2), silence(3)])
    lib, m = meeting_with(tmp_path, mic, system)
    progress = []
    run = FakeRun(["from me", "from them"])
    out = transcribe_meeting(lib, m, run, progress=progress.append)
    assert [(s["speaker"], s["text"]) for s in out] == [("Me", "from me"), ("Them", "from them")]
    assert lib.get(m.id).status == "transcribed" and lib.transcript(m) == out
    assert progress == sorted(progress) and progress[-1] == pytest.approx(1.0)
    assert [x.id for x in lib.search("them")] == [m.id]


def test_transcribe_meeting_works_with_only_a_mic_track(tmp_path):
    lib, m = meeting_with(tmp_path, tone(2), None)
    out = transcribe_meeting(lib, m, FakeRun(["solo"]))
    assert [s["speaker"] for s in out] == ["Me"]


def test_cancel_leaves_the_meeting_saved_and_untranscribed(tmp_path):
    lib, m = meeting_with(tmp_path, tone(2), tone(2))
    with pytest.raises(Cancelled):
        transcribe_meeting(lib, m, FakeRun(), cancelled=lambda: True)
    assert lib.get(m.id).status == "saved" and lib.transcript(m) == []


def test_model_failure_restores_status_and_propagates(tmp_path):
    lib, m = meeting_with(tmp_path, tone(2), None)

    def boom(audio):
        raise RuntimeError("model fell over")

    with pytest.raises(RuntimeError, match="fell over"):
        transcribe_meeting(lib, m, boom)
    assert lib.get(m.id).status == "saved"


def test_status_is_transcribing_while_the_job_runs(tmp_path):
    lib, m = meeting_with(tmp_path, tone(2), None)
    seen = []

    def run(audio):
        seen.append(lib.get(m.id).status)
        return SimpleNamespace(text="x")

    transcribe_meeting(lib, m, run)
    assert seen == ["transcribing"]
