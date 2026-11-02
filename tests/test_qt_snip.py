"""SnipController: opens the editor, queues finished snips, feeds voice notes. Editor and screen are faked."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")
from PySide6.QtGui import QPixmap  # noqa: E402

from gguf_dictate.ui.snip import SnipController  # noqa: E402


class FakeEditor:
    def __init__(self, shot, colors, on_done, speak, on_close):
        self.shot, self.colors, self.on_done, self.speak, self.on_close = shot, colors, on_done, speak, on_close
        self.notes, self.queued, self.opened, self.cancelled = [], None, False, False

    def set_queued(self, n):
        self.queued = n

    def open(self):
        self.opened = True

    def add_note(self, text):
        self.notes.append(text)

    def cancel(self):
        self.cancelled = True
        self.on_close()


class Surface:
    def write_to_png(self, path):
        open(path, "wb").write(b"png")


class Pasting:
    pasting = False

    def __init__(self):
        self.log = []

    def saved(self, notes):
        self.log.append(("saved", notes))

    def ctrl_v(self):
        self.log.append("ctrl_v")

    def paste_all(self):
        self.log.append("paste_all")


@pytest.fixture
def snip(tmp_path):
    from gguf_dictate.notes import Queue
    s = SnipController(on_change=lambda: s.changes.append(1), speak=lambda c: None, queue=Queue(tmp_path), pasting=Pasting(),
                       grab=lambda: QPixmap(10, 10), editor_factory=FakeEditor)
    s.changes = []
    return s


COLORS = [["Red", "#ff3b30"], ["Blue", "#0a84ff"]]


def test_start_opens_editor_with_queue_count(snip):
    snip.start(COLORS)
    assert snip.editor.opened and snip.editor.queued == 0 and snip.editor.colors == COLORS and snip.editor_open()


def test_start_falls_back_to_default_colours_and_caps_them(snip):
    snip.start(None)
    assert len(snip.editor.colors) == 5


def test_second_start_while_open_is_ignored(snip):
    snip.start(COLORS)
    first = snip.editor
    snip.start(COLORS)
    assert snip.editor is first


def test_start_ignored_while_paste_all_runs(snip):
    snip.pasting.pasting = True
    snip.start(COLORS)
    assert snip.editor is None and not snip.editor_open()


def test_finishing_queues_png_and_json_and_tells_pasting(snip):
    snip.start(COLORS)
    notes = [{"color": "Red", "text": "bug"}]
    snip.editor.on_done(Surface(), notes)
    assert snip.count() == 1 and snip.pasting.log == [("saved", notes)]


def test_closing_editor_clears_it(snip):
    snip.start(COLORS)
    snip.editor.on_close()
    assert snip.editor is None and not snip.editor_open()


def test_note_goes_to_open_editor_only(snip):
    snip.note("ignored")
    snip.start(COLORS)
    snip.note("kept")
    assert snip.editor.notes == ["kept"]


def test_cancel_closes_editor_and_is_safe_when_closed(snip):
    snip.cancel()
    snip.start(COLORS)
    ed = snip.editor
    snip.cancel()
    assert ed.cancelled and snip.editor is None


def test_clear_empties_queue_and_notifies(snip):
    snip.start(COLORS)
    snip.editor.on_done(Surface(), [])
    snip.clear()
    assert snip.count() == 0 and snip.changes


def test_ctrl_v_and_paste_all_delegate(snip):
    snip.ctrl_v()
    snip.paste_all()
    assert snip.pasting.log == ["ctrl_v", "paste_all"]
