"""Dictation and meeting transcription share one model session, so calls must not overlap."""
import threading
import time

from gguf_dictate.model import Loaded


class Session:
    def __init__(self):
        self.inside, self.worst = 0, 0

    def run(self, audio):
        self.inside += 1
        self.worst = max(self.worst, self.inside)
        time.sleep(0.02)
        self.inside -= 1
        return "ok"


def test_concurrent_runs_are_serialised():
    s = Session()
    m = Loaded(None, s)
    threads = [threading.Thread(target=m.run, args=(None,)) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert s.worst == 1
