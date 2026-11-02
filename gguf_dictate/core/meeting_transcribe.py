"""Turns a recorded meeting into a transcript: each track is split at silences, transcribed, labelled and merged by time."""
import wave
from itertools import chain

import numpy as np

from .meeting_recorder import HEADER
from .state import RATE

MAX_CHUNK_S = 25.0      # stay well inside what the model takes in one go
FRAME_S = 0.02
HANGOVER_S = 0.5        # a pause shorter than this does not end a sentence
PAD_S = 0.15
SILENT_RMS = 0.003      # below this a frame is silence whatever the track's loudness
REL_RMS = 0.03         # ...and below this fraction of the track's loud parts, so quiet speakers still count
BLOCK_FRAMES = 3000     # 60 s of 20 ms frames: bounds the memory used while scanning a long track
TRACKS = (("Me", "mic_path"), ("Them", "system_path"))


class Cancelled(Exception):
    """The user cancelled the transcription."""


def load_pcm(path, rate=RATE):
    """int16 samples of a recorded track, memory-mapped so a multi-hour file is never loaded whole."""
    try:
        with wave.open(str(path)) as w:
            if w.getframerate() != rate or w.getnchannels() != 1 or w.getsampwidth() != 2:
                raise ValueError(f"{path.name}: expected {rate} Hz mono 16-bit")
        frames = (path.stat().st_size - HEADER) // 2      # from the file size, so a half-finished header cannot mislead
    except (OSError, EOFError):
        return np.zeros(0, np.int16)
    if frames <= 0:
        return np.zeros(0, np.int16)
    return np.memmap(path, dtype="<i2", mode="r", offset=HEADER, shape=(frames,))


def as_float(x):
    return x.astype(np.float32) / 32768 if x.dtype == np.int16 else x.astype(np.float32)


def frame_rms(audio, n):
    frames = len(audio) // n
    out = np.empty(frames, np.float32)
    for a in range(0, frames, BLOCK_FRAMES):
        b = min(frames, a + BLOCK_FRAMES)
        x = as_float(audio[a * n:b * n]).reshape(b - a, n)
        out[a:b] = np.sqrt((x * x).mean(1))
    return out


def speech_regions(audio, rate=RATE, max_s=MAX_CHUNK_S):
    """[(t0, t1)] seconds of speech, none longer than max_s; long stretches are cut at their quietest moment."""
    n = int(FRAME_S * rate)
    rms = frame_rms(audio, n)
    if not len(rms):
        return []
    voiced = np.flatnonzero(rms > max(SILENT_RMS, REL_RMS * np.percentile(rms, 95)))
    if not len(voiced):
        return []
    gap, pad, longest = int(HANGOVER_S / FRAME_S), int(PAD_S / FRAME_S), int(max_s / FRAME_S)
    breaks = np.flatnonzero(np.diff(voiced) > gap)
    firsts = np.concatenate([[voiced[0]], voiced[breaks + 1]])
    lasts = np.concatenate([voiced[breaks], [voiced[-1]]])
    out = []
    for s, e in zip(firsts, lasts):
        s, e = max(0, s - pad), min(len(rms), e + 1 + pad)
        while e - s > longest:
            lo, hi = s + int(0.6 * longest), s + longest
            cut = lo + int(np.argmin(rms[lo:hi]))
            out.append((s * FRAME_S, cut * FRAME_S))
            s = cut
        out.append((s * FRAME_S, e * FRAME_S))
    return out


def transcribe_track(run, audio, speaker, rate=RATE, progress=None, cancelled=None):
    """Segments {t0, t1, speaker, text} for one track; `run(float32 audio)` returns something with .text."""
    regions = speech_regions(audio, rate)
    total, done, segments = sum(b - a for a, b in regions), 0.0, []
    for t0, t1 in regions:
        if cancelled and cancelled():
            raise Cancelled()
        text = " ".join(run(as_float(audio[int(t0 * rate):int(t1 * rate)])).text.split())
        if text:
            segments.append({"t0": round(t0, 2), "t1": round(t1, 2), "speaker": speaker, "text": text})
        done += t1 - t0
        if progress:
            progress(done / total)
    return segments


def merge(*tracks):
    return sorted(chain.from_iterable(tracks), key=lambda s: s["t0"])


def transcribe_meeting(library, meeting, run, progress=None, cancelled=None):
    """Transcribe both tracks and store the result. A failure or cancel puts the meeting back as it was."""
    audio = [(speaker, load_pcm(getattr(meeting, attr))) for speaker, attr in TRACKS]
    total, before, previous = max(1, sum(len(a) for _, a in audio)), 0, meeting.status
    library.set_status(meeting, "transcribing")
    try:
        tracks = []
        for speaker, pcm in audio:
            share, start = len(pcm) / total, before / total

            def report(fraction, share=share, start=start):
                if progress:
                    progress(start + fraction * share)

            tracks.append(transcribe_track(run, pcm, speaker, progress=report, cancelled=cancelled))
            before += len(pcm)
        segments = merge(*tracks)
        library.set_transcript(meeting, segments)
    except BaseException:
        library.set_status(meeting, previous)
        raise
    if progress:
        progress(1.0)
    return segments
