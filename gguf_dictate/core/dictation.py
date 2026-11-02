"""Everything between key events and typed text, with the model, mic and keyboard injected (so it runs headless in tests)."""
import threading
import time

from .state import RATE, DictationState, HotkeyRouter, prepare_audio, route_text, thread_spawn


class Dictation:
    """model.run(audio).text -> str; mic.start()/stop(); keys.type_text(text); notify(msg) drives the overlay."""

    def __init__(self, model, mic, keys, notify, editor_open, talk, snip, paste,
                 no_space=False, meeting=None, log=print, spawn=thread_spawn, sleep=time.sleep):
        self.model, self.keys, self.notify, self.editor_open, self.no_space, self.log = model, keys, notify, editor_open, no_space, log
        self.busy = threading.Lock()
        self.state = DictationState(mic, self._notify, self._process, spawn)
        self.router = HotkeyRouter(talk, snip, paste, self.state, self._notify, editor_open, sleep, meeting)

    def _notify(self, msg):
        if msg == "rec":
            self.log("recording...")
        elif msg == "cancel":
            self.log("Esc: closing the snip editor")
        self.notify(msg)

    def _process(self, audio):
        with self.busy:
            audio, why = prepare_audio(audio)
            if audio is None:
                self.log(why if why == "too short" else f"mic is {why}: check input device / volume / mute")
                return
            t0 = time.time()
            text = self.model.run(audio).text.strip()
            self.log(f"[{len(audio) / RATE:.1f}s audio -> {(time.time() - t0) * 1000:.0f}ms] {text}")
            routed = route_text(text, self.editor_open(), self.no_space)   # editor open: a voice note, not typing
            if routed and routed[0] == "note":
                self.notify("note " + routed[1])
            elif routed:
                self.keys.type_text(routed[1])
