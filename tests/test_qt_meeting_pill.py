"""Meeting recording pill, headless."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QMouseEvent  # noqa: E402

from gguf_dictate.core.pill_model import MARGIN  # noqa: E402
from gguf_dictate.ui.meeting_pill import MeetingPill, glyph  # noqa: E402


def screen():
    g = QGuiApplication.primaryScreen().availableGeometry()
    return g.left(), g.top(), g.left() + g.width(), g.top() + g.height()


def make(qtbot, **kw):
    p = MeetingPill(**kw)
    qtbot.addWidget(p)
    p.show()
    qtbot.waitExposed(p)
    return p


def mouse(kind, pos, buttons):
    local = QPointF(pos)
    return QMouseEvent(kind, local, local, Qt.LeftButton if kind != QEvent.MouseMove else Qt.NoButton, buttons, Qt.NoModifier)


def drag(p, to):
    """Press on the pill body, move so the pill's top-left lands on `to`, release."""
    grip = QPoint(6, 6)
    start = p.frameGeometry().topLeft() + grip
    p.mousePressEvent(mouse(QEvent.MouseButtonPress, start, Qt.LeftButton))
    p.mouseMoveEvent(mouse(QEvent.MouseMove, QPoint(*to) + grip, Qt.LeftButton))
    p.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, QPoint(*to) + grip, Qt.NoButton))


def test_window_is_always_on_top_frameless_and_clickable(qtbot):
    p = make(qtbot)
    f = p.windowFlags()
    assert f & Qt.FramelessWindowHint and f & Qt.WindowStaysOnTopHint
    assert not f & Qt.WindowTransparentForInput      # unlike the dictation overlay, it has buttons and is dragged
    assert p.testAttribute(Qt.WA_ShowWithoutActivating)


def test_starts_in_the_top_right_corner_by_default(qtbot):
    left, top, right, _ = screen()
    p = make(qtbot)
    assert (p.x(), p.y()) == (right - p.width() - MARGIN, top + MARGIN)


def test_restores_a_saved_position_and_pulls_an_offscreen_one_back(qtbot):
    left, top, right, bottom = screen()
    p = make(qtbot, pos=(left + 120, top + 90))
    assert (p.x(), p.y()) == (left + 120, top + 90)
    q = make(qtbot, pos=(99999, 99999))
    assert (q.x(), q.y()) == (right - q.width(), bottom - q.height())


def test_shows_elapsed_time(qtbot):
    p = make(qtbot)
    assert p.time.text() == "0:00"
    p.set_elapsed(3725)
    assert p.time.text() == "1:02:05"


def test_pause_and_stop_buttons_emit(qtbot):
    p = make(qtbot)
    with qtbot.waitSignal(p.pause_clicked, timeout=1000):
        qtbot.mouseClick(p.pause_btn, Qt.LeftButton)
    with qtbot.waitSignal(p.stop_clicked, timeout=1000):
        qtbot.mouseClick(p.stop_btn, Qt.LeftButton)


def test_paused_state_changes_the_button_and_stops_the_blinking(qtbot):
    p = make(qtbot)
    p.set_recording(True)
    assert p.pause_btn.toolTip() == "Pause"
    p.set_paused(True)
    assert p.pause_btn.toolTip() == "Resume"
    shown = p.dot_on
    p.blink()
    assert p.dot_on == shown
    p.set_paused(False)
    assert p.pause_btn.toolTip() == "Pause"
    before = p.dot_on
    p.blink()
    assert p.dot_on != before


def test_drag_moves_the_pill_and_reports_where_it_was_dropped(qtbot):
    left, top, right, bottom = screen()
    p = make(qtbot)
    mid = ((left + right) // 2, (top + bottom) // 2)
    with qtbot.waitSignal(p.moved, timeout=1000) as sig:
        drag(p, mid)
    assert (p.x(), p.y()) == mid and sig.args == list(mid)


def test_dropping_near_a_corner_snaps_into_it(qtbot):
    left, top, right, bottom = screen()
    p = make(qtbot)
    drag(p, (left + 10, top + 7))
    assert (p.x(), p.y()) == (left + MARGIN, top + MARGIN)
    drag(p, (right - p.width() - 5, bottom - p.height() - 9))
    assert (p.x(), p.y()) == (right - p.width() - MARGIN, bottom - p.height() - MARGIN)


def test_cannot_be_dragged_off_the_screen(qtbot):
    left, top, right, bottom = screen()
    p = make(qtbot)
    drag(p, (right + 500, bottom + 500))
    assert p.x() + p.width() <= right and p.y() + p.height() <= bottom


def test_moving_the_mouse_without_a_press_does_nothing(qtbot):
    p = make(qtbot)
    before = (p.x(), p.y())
    p.mouseMoveEvent(mouse(QEvent.MouseMove, QPoint(200, 200), Qt.LeftButton))
    assert (p.x(), p.y()) == before


@pytest.mark.parametrize("kind", ["pause", "play", "stop", "save", "cancel"])
def test_button_icons_are_light_enough_to_see_on_the_dark_pill(qapp, kind):
    img = glyph(kind).pixmap(16, 16).toImage()
    opaque = [img.pixelColor(x, y) for x in range(16) for y in range(16) if img.pixelColor(x, y).alpha() > 200]
    assert opaque and all(c.red() > 240 and c.green() > 240 and c.blue() > 240 for c in opaque)


def test_the_pill_is_actually_painted(qtbot):
    p = make(qtbot)
    img = p.grab().toImage()
    assert img.pixelColor(img.width() // 2, img.height() // 2).alpha() > 100


def test_pill_opens_ready_with_only_a_record_button(qtbot):
    p = make(qtbot)
    assert not p.recording and not p.record_btn.isHidden() and p.pause_btn.isHidden() and p.stop_btn.isHidden()
    assert p.record_btn.toolTip() == "Start recording" and p.time.text() == "0:00"
    before = p.dot_on
    p.blink()
    assert p.dot_on == before      # no blinking until it records


def test_record_button_emits_and_recording_swaps_the_buttons(qtbot):
    p = make(qtbot)
    with qtbot.waitSignal(p.record_clicked, timeout=1000):
        qtbot.mouseClick(p.record_btn, Qt.LeftButton)
    p.set_recording(True)
    assert p.record_btn.isHidden() and not p.pause_btn.isHidden() and not p.stop_btn.isHidden()
    assert p.stop_btn.toolTip() == "Save"
    p.set_recording(False)
    assert not p.record_btn.isHidden() and p.pause_btn.isHidden()


def test_cancel_button_is_there_ready_and_recording_and_emits(qtbot):
    p = make(qtbot)
    assert not p.cancel_btn.isHidden() and p.cancel_btn.toolTip() == "Close"
    p.set_recording(True)
    assert not p.cancel_btn.isHidden() and p.cancel_btn.toolTip() == "Cancel and discard"
    with qtbot.waitSignal(p.cancel_clicked, timeout=1000):
        qtbot.mouseClick(p.cancel_btn, Qt.LeftButton)
