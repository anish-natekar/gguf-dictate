"""Push-to-talk recorder: a rolling pre-roll buffer so the first syllable isn't clipped, plus live mic levels."""
import threading

import numpy as np

from .state import RATE

PREROLL_S = 0.25


class Recorder:
    """Fed mono float32 chunks by an audio source (anything with open(callback) / close()).

    Without `lazy` the source stays open and the pre-roll is always warm; with `lazy` it opens on start().
    """

    def __init__(self, source, on_level=None, rate=RATE, lazy=False):
        self.source, self.on_level, self.lazy = source, on_level, lazy
        self.preroll = int(PREROLL_S * rate)
        self.pre, self.buf, self.recording = np.zeros(0, np.float32), [], False
        self.lock = threading.Lock()
        if not lazy:
            source.open(self.feed)

    def feed(self, chunk):
        level = None
        with self.lock:
            self.pre = np.concatenate([self.pre, chunk])[-self.preroll:]
            if self.recording:
                self.buf.append(chunk)
                if self.on_level:
                    level = float(np.sqrt(np.mean(chunk * chunk)))
        if level is not None:
            self.on_level(level)

    def start(self):
        if self.lazy:
            self.source.open(self.feed)
        with self.lock:
            self.buf, self.recording = [self.pre], True

    def stop(self):
        with self.lock:
            self.recording = False
            audio = np.concatenate(self.buf) if self.buf else np.zeros(0, np.float32)
            self.buf = []
        if self.lazy:
            self.source.close()
        return audio

    def close(self):
        self.source.close()
