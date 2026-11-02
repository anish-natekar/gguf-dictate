"""Opens the annotation editor over a frozen screen, queues finished snips and drives paste-all."""
from PySide6.QtGui import QCursor, QGuiApplication

from ..config import DEFAULT_COLORS, MAX_COLORS
from ..core.pasting import Pasting
from ..notes import Queue
from ..platform.linux import NotifySend, XdotoolKeys
from ..platform.qt import QtClipboard, QtClock
from .editor import EditorView


def grab_screen():
    return (QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()).grabWindow(0)


def open_editor(shot, colors, on_done, speak, on_close):
    view = EditorView(shot, colors, on_done, speak, on_close=on_close)
    screen = QGuiApplication.screenAt(QCursor.pos())
    if screen:
        view.setScreen(screen)
    return view


class SnipController:
    def __init__(self, on_change, speak, queue=None, pasting=None, grab=grab_screen, editor_factory=open_editor):
        self.queue, self.on_change, self.speak = queue or Queue(), on_change, speak
        self.grab, self.editor_factory, self.editor = grab, editor_factory, None
        self.pasting = pasting or Pasting(self.queue, QtClipboard(), XdotoolKeys(), NotifySend(), QtClock(), on_change, self.editor_open)

    def editor_open(self):
        return self.editor is not None

    def count(self):
        return len(self.queue.items())

    def start(self, colors):
        if self.editor or self.pasting.pasting:
            return
        cols = [c for c in (colors or DEFAULT_COLORS) if len(c) == 2][:MAX_COLORS] or DEFAULT_COLORS
        self.editor = self.editor_factory(self.grab(), cols, self.finished, self.speak, self.closed)
        self.editor.set_queued(self.count())
        self.editor.open()

    def closed(self):
        self.editor = None

    def finished(self, surface, notes):
        self.queue.add(surface, notes)
        self.pasting.saved(notes)

    def cancel(self):
        if self.editor:
            self.editor.cancel()

    def note(self, text):
        if self.editor:
            self.editor.add_note(text)

    def ctrl_v(self):
        self.pasting.ctrl_v()

    def paste_all(self):
        self.pasting.paste_all()

    def clear(self):
        self.queue.clear()
        self.on_change()
