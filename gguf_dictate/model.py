"""Loads a speech-to-text GGUF through transcribe.cpp and warms it up (the first GPU run compiles shaders)."""
import sys
import threading
import time
from pathlib import Path

import numpy as np

from .core.state import RATE


class Loaded:
    """Keeps the model alive for as long as its session is used."""

    def __init__(self, model, session):
        self.model, self.session = model, session
        self.lock = threading.Lock()      # dictation and meeting transcription share one session

    def run(self, audio):
        with self.lock:
            return self.session.run(audio)


def load_session(path):
    import transcribe_cpp
    transcribe_cpp.set_log_callback(lambda lvl, msg: print(msg, file=sys.stderr) if lvl >= 3 else None)
    t = time.time()
    model = transcribe_cpp.Model(str(path))
    session = model.session()
    session.run(np.zeros(RATE, np.float32))
    print(f"{Path(path).name} ready in {time.time() - t:.1f}s", flush=True)
    return Loaded(model, session)
