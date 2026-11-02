"""Qt implementations of the clipboard and clock interfaces core.pasting needs (call from the GUI thread)."""
from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication, QImage


class QtClipboard:
    def __init__(self):
        self.cb = QGuiApplication.clipboard()

    def on_change_listener(self, callback):
        self.cb.dataChanged.connect(lambda: callback())

    def load_image(self, path):
        return QImage(str(path))      # decoded now: paste-all deletes the file afterwards

    def set_image(self, image):
        self.cb.setImage(image)

    def set_text(self, text):
        self.cb.setText(text)


class QtClock:
    def after(self, ms, fn, *args):
        QTimer.singleShot(ms, lambda: fn(*args))
