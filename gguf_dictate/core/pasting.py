"""Ctrl+V of the latest snip and paste-all of the queue, written against small platform interfaces.

clipboard: on_change_listener(cb), load_image(path) -> handle, set_image(handle), set_text(text)
keys:      paste()              (the synthetic Ctrl+V)
notifier:  toast(title, body)
clock:     after(ms, fn, *args)
"""
from .. import notes as notes_mod

IMG_MS = 900       # an image needs time to upload before the next paste
TXT_MS = 250
PRESS_DELAY_MS = 150
OWN_CLIP_MS = 300  # clipboard changes this soon after our own write are ours
FOLLOW_UP_MS = 700


class Pasting:
    def __init__(self, queue, clipboard, keys, notifier, clock, on_change, editor_open):
        self.queue, self.clipboard, self.keys, self.notifier, self.clock = queue, clipboard, keys, notifier, clock
        self.on_change, self.editor_open = on_change, editor_open
        self.pasting, self.own_clip = False, False
        self.latest_text = self.latest_img = self.last_text = None   # latest snip: Ctrl+V pastes it
        clipboard.on_change_listener(self.clip_changed)

    def clip_changed(self, *_):
        if not self.own_clip:       # user copied something else: stop following Ctrl+V
            self.latest_text = self.latest_img = None

    def _set_clip(self, fn):
        self.own_clip = True
        fn()
        self.clock.after(OWN_CLIP_MS, self._release_clip)

    def _release_clip(self):
        self.own_clip = False

    def saved(self, notes):
        """A snip was just added to the queue."""
        self.on_change()
        count = len(self.queue.items())
        self.latest_img = self.clipboard.load_image(self.queue.items()[-1][0])
        self.latest_text = self.last_text = notes_mod.format_notes(1, notes) if notes else None
        self._set_clip(lambda: self.clipboard.set_image(self.latest_img))
        self.notifier.toast("Snip saved", f"{count} in queue. Ctrl+V pastes this one" + (" + its notes" if notes else "") + "; Ctrl+Alt+V pastes all.")

    def ctrl_v(self):
        """Ctrl+V was pressed: the app pastes the image natively, then we follow with the snip's notes."""
        if self.pasting or self.editor_open() or not self.latest_text:
            return
        text, img = self.latest_text, self.latest_img
        self.latest_text = None      # one follow-up per snip

        def send_text():
            self._set_clip(lambda: self.clipboard.set_text(text))
            self.clock.after(PRESS_DELAY_MS, self.keys.paste)
            self.clock.after(FOLLOW_UP_MS, lambda: self._set_clip(lambda: self.clipboard.set_image(img)))   # restore the image
        self.clock.after(IMG_MS, send_text)

    def paste_all(self):
        items = self.queue.items()
        if self.pasting or self.editor_open() or not items:
            return
        steps = []
        for n, (png, notes) in enumerate(items, 1):
            steps.append(("img", self.clipboard.load_image(png)))
            if notes:
                steps.append(("txt", notes_mod.format_notes(n, notes)))
        self.pasting = True
        self._run(steps)

    def _run(self, steps):
        if not steps:
            self.queue.clear()
            self.on_change()
            self.clock.after(OWN_CLIP_MS, self._restore_latest)   # let the last paste read the clipboard first
            return
        kind, val = steps[0]
        self._set_clip(lambda: self.clipboard.set_image(val) if kind == "img" else self.clipboard.set_text(val))
        self.clock.after(PRESS_DELAY_MS, self._press, steps)

    def _press(self, steps):
        self.keys.paste()
        self.clock.after(IMG_MS if steps[0][0] == "img" else TXT_MS, self._run, steps[1:])   # images need time to upload

    def _restore_latest(self):
        """After paste-all the clipboard holds the last note text: put the latest snip back so Ctrl+V pastes it."""
        if self.latest_img:
            self._set_clip(lambda: self.clipboard.set_image(self.latest_img))
            self.latest_text = self.last_text
        self.pasting = False
