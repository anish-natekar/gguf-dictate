"""Records a meeting as two 16 kHz mono WAV tracks (mic and system audio) streamed to disk as they arrive."""
import struct
import threading
from datetime import datetime

import numpy as np

from .state import RATE

HEADER = 44
HEADER_REFRESH_S = 1      # keep the sizes in the header current, so a crash leaves a file most players can open


def header(frames, rate=RATE):
    data = frames * 2
    return b"RIFF" + struct.pack("<I", 36 + data) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + b"data" + struct.pack("<I", data)


class WavWriter:
    """Appends int16 PCM and flushes every write; the header is patched periodically and on close."""

    def __init__(self, path, rate=RATE):
        self.path, self.rate, self.frames, self.patched = path, rate, 0, 0
        self.f = open(path, "wb")
        self.f.write(header(0, rate))
        self.f.flush()

    def write(self, samples):
        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
        self.f.write(pcm.tobytes())
        self.f.flush()
        self.frames += len(pcm)
        if self.frames - self.patched >= HEADER_REFRESH_S * self.rate:
            self.patch()

    def patch(self):
        self.f.seek(0)
        self.f.write(header(self.frames, self.rate))
        self.f.seek(0, 2)
        self.f.flush()
        self.patched = self.frames

    def close(self):
        if not self.f.closed:
            self.patch()
            self.f.close()


def repair_wav(path, rate=RATE):
    """Fix the header of a WAV left behind by a crash; returns the number of frames it holds."""
    try:
        frames = max(0, (path.stat().st_size - HEADER) // 2)
        with open(path, "r+b") as f:
            f.truncate(HEADER + frames * 2)      # drop a torn final sample
            f.seek(0)
            f.write(header(frames, rate))
    except OSError:
        return 0
    return frames


def repair(library):
    """Finish meetings whose recording was cut short; empty ones are discarded. Returns the ids that were saved."""
    saved = []
    for m in library.unfinished():
        frames = max(repair_wav(m.mic_path), repair_wav(m.system_path))
        if frames:
            library.finish(m, frames / RATE)
            saved.append(m.id)
        else:
            library.delete(m)
    for m in library.all():      # a crash mid-transcription leaves "transcribing" behind
        if m.status == "transcribing":
            library.set_status(m, "transcribed" if library.transcript(m) else "saved")
    return saved


class MeetingRecorder:
    """Sources are anything with open(callback) / close() that deliver mono float32 at 16 kHz.

    The mic is required; a system-audio failure is recorded in `warnings` and the meeting goes on with the mic alone.
    """

    def __init__(self, library, mic, system, on_level=None, clock=datetime.now, rate=RATE):
        self.library, self.mic, self.system, self.on_level, self.clock, self.rate = library, mic, system, on_level, clock, rate
        self.lock = threading.Lock()
        self.meeting, self.writers, self.live, self.paused, self.warnings = None, {}, False, False, []

    @property
    def elapsed(self):
        with self.lock:
            return max((w.frames for w in self.writers.values()), default=0) / self.rate

    def start(self):
        if self.live:
            raise RuntimeError("already recording")
        m = self.library.create(self.clock())
        self.meeting, self.warnings, self.paused = m, [], False
        self.writers = {"mic": WavWriter(m.mic_path, self.rate)}
        self.live = True
        try:
            self.mic.open(self.feed_mic)
        except Exception:
            self.live = False
            self.writers["mic"].close()
            self.library.delete(m)
            raise
        self.writers["system"] = WavWriter(m.system_path, self.rate)
        try:
            self.system.open(self.feed_system)
        except Exception as e:
            self.writers.pop("system").close()
            m.system_path.unlink(missing_ok=True)
            self.warnings.append(f"system audio unavailable: {e}")
        return m

    def write(self, track, chunk):
        with self.lock:
            if self.live and not self.paused and track in self.writers:
                self.writers[track].write(chunk)
                return True
        return False

    def feed_mic(self, chunk):
        if self.write("mic", chunk) and self.on_level:
            self.on_level(float(np.sqrt(np.mean(chunk * chunk))))

    def feed_system(self, chunk):
        self.write("system", chunk)

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        with self.lock:
            self.live = False      # late callbacks from the audio threads are dropped from here on
        for source in (self.mic, self.system):
            try:
                source.close()
            except Exception as e:
                self.warnings.append(f"closing audio source failed: {e}")
        with self.lock:
            frames = max((w.frames for w in self.writers.values()), default=0)
            for w in self.writers.values():
                w.close()
        self.library.finish(self.meeting, frames / self.rate)
        return self.meeting
