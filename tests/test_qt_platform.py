"""Qt clipboard + clock adapters for core.pasting, headless."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")
from PySide6.QtGui import QColor, QGuiApplication, QImage  # noqa: E402

from gguf_dictate.platform.qt import QtClipboard, QtClock  # noqa: E402


def png(tmp_path, w=7, h=5):
    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(QColor("red"))
    p = tmp_path / "a.png"
    assert img.save(str(p), "PNG")
    return p


def test_load_image_decodes_now_so_the_file_can_be_deleted(qtbot, tmp_path):
    p = png(tmp_path)
    cb = QtClipboard()
    img = cb.load_image(p)
    p.unlink()
    assert (img.width(), img.height()) == (7, 5)


def test_set_image_and_set_text_reach_the_system_clipboard(qtbot, tmp_path):
    cb = QtClipboard()
    cb.set_image(cb.load_image(png(tmp_path)))
    assert QGuiApplication.clipboard().image().width() == 7
    cb.set_text("hello")
    assert QGuiApplication.clipboard().text() == "hello"


def test_change_listener_fires_on_clipboard_change(qtbot):
    cb = QtClipboard()
    seen = []
    cb.on_change_listener(lambda: seen.append(1))
    cb.set_text("x")
    qtbot.waitUntil(lambda: bool(seen), timeout=2000)


def test_clock_after_runs_callback_with_args_once(qtbot):
    got = []
    QtClock().after(20, lambda a, b: got.append((a, b)), 1, 2)
    assert got == []
    qtbot.waitUntil(lambda: got == [(1, 2)], timeout=2000)
