"""Opens the annotation editor over a frozen screen, queues finished snips and drives paste-all."""
from PySide6.QtCore import QRect
from PySide6.QtGui import QCursor, QGuiApplication, QPixmap

from ..config import DEFAULT_COLORS, MAX_COLORS
from ..core.pasting import Pasting
from ..notes import Queue
from ..platform import default_keys, default_notifier, is_wayland
from ..platform.qt import QtClipboard, QtClock
from .editor import EditorView


def grab_screen():
    return (QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()).grabWindow(0)


def crop_rect(desktop, screen, pixmap_width):
    """The part of a whole-desktop image (logical `desktop` rect, `pixmap_width` px wide) that shows `screen`, in image pixels."""
    scale = pixmap_width / desktop.width()
    return QRect(round((screen.x() - desktop.x()) * scale), round((screen.y() - desktop.y()) * scale),
                 round(screen.width() * scale), round(screen.height() * scale))


def grab_portal():
    """Wayland: the portal returns every monitor in one image, so cut out the one under the cursor."""
    from ..platform.portal import read_and_remove, screenshot
    pix = QPixmap()
    pix.loadFromData(read_and_remove(screenshot()))
    screens = QGuiApplication.screens()
    screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    if len(screens) > 1 and not pix.isNull():
        desktop = screens[0].geometry()
        for s in screens[1:]:
            desktop = desktop.united(s.geometry())
        pix = pix.copy(crop_rect(desktop, screen.geometry(), pix.width()))
        pix.setDevicePixelRatio(pix.width() / screen.geometry().width())
    return pix


def default_grab():
    return grab_portal if is_wayland() else grab_screen


def open_editor(shot, colors, on_done, speak, on_close):
    view = EditorView(shot, colors, on_done, speak, on_close=on_close)
    screen = QGuiApplication.screenAt(QCursor.pos())
    if screen:
        view.setScreen(screen)
    return view


class SnipController:
    def __init__(self, on_change, speak, queue=None, pasting=None, grab=None, editor_factory=open_editor, keys=None, notifier=None):
        self.queue, self.on_change, self.speak = queue or Queue(), on_change, speak
        self.grab, self.editor_factory, self.editor = grab or default_grab(), editor_factory, None
        self.notifier = notifier or default_notifier()
        self.pasting = pasting or Pasting(self.queue, QtClipboard(), keys or default_keys(), self.notifier, QtClock(), on_change, self.editor_open)

    def editor_open(self):
        return self.editor is not None

    def count(self):
        return len(self.queue.items())

    def start(self, colors):
        if self.editor or self.pasting.pasting:
            return
        cols = [c for c in (colors or DEFAULT_COLORS) if len(c) == 2][:MAX_COLORS] or DEFAULT_COLORS
        try:
            shot = self.grab()
        except Exception as e:      # noqa: BLE001 - e.g. the screenshot portal was denied or timed out
            self.notifier.toast("Snip failed", str(e))
            return
        if shot.isNull():
            self.notifier.toast("Snip failed", "the screenshot came back empty")
            return
        self.editor = self.editor_factory(shot, cols, self.finished, self.speak, self.closed)
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
