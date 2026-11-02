"""Paste logic (Ctrl+V latest snip, paste-all queue) against fake clipboard / keys / clock: no display needed."""
import pytest

from gguf_dictate.core.pasting import IMG_MS, TXT_MS, Pasting
from gguf_dictate.notes import Queue


class Surface:
    def write_to_png(self, path):
        open(path, "wb").write(b"png")


class FakeClock:
    def __init__(self):
        self.now, self.jobs = 0, []

    def after(self, ms, fn, *args):
        self.jobs.append((self.now + ms, len(self.jobs), fn, args))

    def advance(self, ms):
        end = self.now + ms
        while True:
            due = sorted(j for j in self.jobs if j[0] <= end)
            if not due:
                break
            job = due[0]
            self.jobs.remove(job)
            self.now = job[0]
            job[2](*job[3])
        self.now = end


class World:
    """Everything the paste logic touches, recorded in one ordered log."""

    def __init__(self, tmp_path, editor=False):
        self.log, self.editor, self.changes = [], editor, 0
        self.clock = FakeClock()
        self.listener = None
        self.queue = Queue(tmp_path)
        self.p = Pasting(self.queue, self, self, self, self.clock, on_change=self.on_change, editor_open=lambda: self.editor)

    # clipboard
    def on_change_listener(self, cb):
        self.listener = cb

    def load_image(self, path):
        return path                            # the real clipboard decodes the file now: paste-all deletes it later

    def set_image(self, path):
        self.log.append(("image", path.name))
        self.listener and self.listener()

    def set_text(self, text):
        self.log.append(("text", text))
        self.listener and self.listener()

    # keys
    def paste(self):
        self.log.append(("paste",))

    # notifier
    def toast(self, title, body):
        self.log.append(("toast", title, body))

    def on_change(self):
        self.changes += 1

    def user_copies(self):
        self.listener()

    def save(self, notes):
        self.queue.add(Surface(), notes)
        self.p.saved(notes)

    def kinds(self):
        return [e[0] for e in self.log]


@pytest.fixture
def w(tmp_path):
    return World(tmp_path)


RED = [{"color": "Red", "text": "a"}]
BLUE = [{"color": "Blue", "text": "b"}]


# --- saving -----------------------------------------------------------------

def test_saving_puts_latest_image_on_clipboard_and_toasts(w):
    w.save(RED)
    assert w.log[0][0] == "image"
    assert w.log[-1] == ("toast", "Snip saved", "1 in queue. Ctrl+V pastes this one + its notes; Ctrl+Alt+V pastes all.")


def test_toast_without_notes_omits_notes_hint(w):
    w.save([])
    assert w.log[-1][2] == "1 in queue. Ctrl+V pastes this one; Ctrl+Alt+V pastes all."


def test_saving_notifies_queue_changed(w):
    w.save(RED)
    assert w.changes == 1


# --- Ctrl+V latest ----------------------------------------------------------

def test_ctrl_v_follows_image_with_notes_then_restores_image(w):
    w.save(RED)
    w.clock.advance(400)                       # let the own-clipboard guard expire
    w.log.clear()
    w.p.ctrl_v()
    w.clock.advance(IMG_MS - 1)
    assert w.log == []                         # the app is still pasting the image natively
    w.clock.advance(1)
    assert w.log == [("text", "\nScreenshot 1\n\n## Red\n- a")]
    w.clock.advance(150)
    assert w.log[-1] == ("paste",)
    w.clock.advance(700)
    assert [e[0] for e in w.log] == ["text", "paste", "image"]


def test_ctrl_v_follow_up_only_once_per_snip(w):
    w.save(RED)
    w.clock.advance(400)
    w.p.ctrl_v()
    w.clock.advance(3000)
    w.log.clear()
    w.p.ctrl_v()
    w.clock.advance(3000)
    assert w.log == []


def test_ctrl_v_does_nothing_without_notes(w):
    w.save([])
    w.clock.advance(400)
    w.log.clear()
    w.p.ctrl_v()
    w.clock.advance(3000)
    assert w.log == []


def test_ctrl_v_ignored_while_editor_open(w):
    w.save(RED)
    w.clock.advance(400)
    w.log.clear()
    w.editor = True
    w.p.ctrl_v()
    w.clock.advance(3000)
    assert w.log == []


def test_user_copying_something_else_disarms_ctrl_v(w):
    w.save(RED)
    w.clock.advance(400)
    w.user_copies()
    w.log.clear()
    w.p.ctrl_v()
    w.clock.advance(3000)
    assert w.log == []


def test_our_own_clipboard_writes_do_not_disarm(w):
    w.save(RED)                                # set_image fires the change signal, inside the guard window
    w.clock.advance(400)
    w.p.ctrl_v()
    w.clock.advance(IMG_MS)
    assert w.log[-1][0] == "text"


# --- paste all --------------------------------------------------------------

def test_paste_all_sequence_and_timing(w):
    w.save(RED)
    w.save(BLUE)
    w.clock.advance(400)
    w.log.clear()
    w.p.paste_all()
    assert w.p.pasting
    w.clock.advance(0)
    assert [e[0] for e in w.log] == ["image"]
    w.clock.advance(150)
    assert [e[0] for e in w.log] == ["image", "paste"]
    w.clock.advance(IMG_MS)                    # image upload time, then the notes text
    assert w.log[2] == ("text", "\nScreenshot 1\n\n## Red\n- a")
    w.clock.advance(150 + TXT_MS)              # paste, short text wait, next image
    assert [e[0] for e in w.log] == ["image", "paste", "text", "paste", "image"]
    w.clock.advance(150 + IMG_MS + 150 + TXT_MS + 5000)
    texts = [e[1] for e in w.log if e[0] == "text"]
    assert texts == ["\nScreenshot 1\n\n## Red\n- a", "\nScreenshot 2\n\n## Blue\n- b"]


def test_paste_all_skips_text_step_for_snip_without_notes(w):
    w.save([])
    w.clock.advance(400)
    w.log.clear()
    w.p.paste_all()
    w.clock.advance(5000)
    assert [e[0] for e in w.log if e[0] in ("text",)] == []


def test_paste_all_clears_queue_and_restores_latest_image_and_ctrl_v(w):
    """Regression: after paste-all emptied the queue, plain Ctrl+V used to paste nothing."""
    w.save(RED)
    w.save(BLUE)
    w.clock.advance(400)
    changes = w.changes
    w.p.paste_all()
    w.clock.advance(20000)
    assert w.queue.items() == [] and w.changes == changes + 1
    assert not w.p.pasting
    assert w.log[-1][0] == "image"             # latest snip back on the clipboard
    w.clock.advance(400)
    w.log.clear()
    w.p.ctrl_v()                               # and its notes follow again
    w.clock.advance(IMG_MS)
    assert w.log == [("text", "\nScreenshot 1\n\n## Blue\n- b")]


def test_paste_all_ignored_when_empty_busy_or_editor_open(w):
    w.p.paste_all()
    assert w.log == [] and not w.p.pasting
    w.save(RED)
    w.clock.advance(400)
    w.editor = True
    w.log.clear()
    w.p.paste_all()
    assert w.log == [] and not w.p.pasting
    w.editor = False
    w.p.paste_all()
    n = len(w.clock.jobs)
    w.p.paste_all()                            # second press while pasting
    assert len(w.clock.jobs) == n


def test_ctrl_v_ignored_while_paste_all_running(w):
    w.save(RED)
    w.clock.advance(400)
    w.p.paste_all()
    w.log.clear()
    w.p.ctrl_v()
    w.clock.advance(100)
    assert not any(e[0] == "text" for e in w.log)
