"""Dictation logic with no mic, GUI or keyboard attached, so it can be tested and reused on every platform."""
import threading
import time

import numpy as np

from .. import hotkeys

RATE = 16000
MIN_SECONDS = 0.2     # shorter clips are accidental taps
SILENT_PEAK = 0.005   # below this the mic is muted or the wrong device
QUIET_PEAK = 0.5      # below this the clip is boosted to TARGET_PEAK
TARGET_PEAK = 0.7
PASTE_SETTLE_S = 0.15


def thread_spawn(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


class DictationState:
    """Recording / transcribing bookkeeping.

    `notify` drives the overlay (rec, busy, idle); `process(audio)` transcribes and delivers one clip.
    The overlay is hidden ('idle') only when nothing is recording and nothing is still queued.
    """

    def __init__(self, mic, notify, process, spawn=thread_spawn):
        self.mic, self.notify, self.process, self.spawn = mic, notify, process, spawn
        self.active, self.source, self.pending = False, "key", 0
        self.lock = threading.Lock()

    def begin(self, source):
        if not self.active:
            self.active, self.source = True, source
            self.notify("rec")
            self.mic.start()

    def end(self):
        if self.active:
            self.active = False
            audio = self.mic.stop()
            with self.lock:
                self.pending += 1
            self.notify("busy")
            self.spawn(self._work, audio)

    def _work(self, audio):
        try:
            self.process(audio)
        finally:
            with self.lock:
                self.pending -= 1
                if not self.pending and not self.active:
                    self.notify("idle")


def prepare_audio(audio, rate=RATE):
    """(audio, None) ready for the model, or (None, reason) when the clip should be ignored."""
    if len(audio) < MIN_SECONDS * rate:
        return None, "too short"
    peak = float(np.abs(audio).max())
    if peak < SILENT_PEAK:
        return None, f"silent (peak {peak:.4f})"
    if peak < QUIET_PEAK:
        audio = audio * (TARGET_PEAK / peak)
    return audio, None


def route_text(text, editor_open, no_space):
    """('note', text) while the snip editor is open, ('type', text) otherwise, None for empty text."""
    if not text:
        return None
    if editor_open:
        return "note", text
    return "type", text if no_space else text + " "


class HotkeyRouter:
    """Turns raw key names into actions. Feed it `press(name)` / `release(name)` from any key listener."""

    def __init__(self, talk, snip, paste, state, notify, editor_open, sleep=time.sleep):
        self.talk, self.snip, self.paste = (hotkeys.parse(h) for h in (talk, snip, paste))
        self.state, self.notify, self.editor_open, self.sleep = state, notify, editor_open, sleep
        self.down, self.fired = set(), set()

    def press(self, name):
        self.down.add(name)
        if name == "esc" and self.editor_open():
            self.notify("cancel")   # Esc closes the snip editor even if it never got keyboard focus
        if hotkeys.is_ctrl_v(name, self.down):
            self.notify("ctrlv")    # the tray follows a snip's image paste with its notes
        if hotkeys.held(self.talk, self.down):
            self.state.begin("key")
        for action, combo in (("snip", self.snip), ("paste", self.paste)):
            if action not in self.fired and hotkeys.held(combo, self.down):
                self.fired.add(action)
                if action == "snip":
                    self.notify(action)   # paste waits for key release: a synthetic Ctrl+V would clash with the held keys

    def release(self, name):
        self.down.discard(name)
        for action, combo in (("snip", self.snip), ("paste", self.paste)):
            if action in self.fired and not hotkeys.held(combo, self.down):
                self.fired.discard(action)
                if action == "paste":
                    self.sleep(PASTE_SETTLE_S)   # let the physical keys fully settle
                    self.notify("paste")
        if self.state.active and self.state.source == "key" and not hotkeys.held(self.talk, self.down):
            self.state.end()
