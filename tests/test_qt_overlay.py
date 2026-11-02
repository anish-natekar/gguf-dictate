"""Qt overlay pill, headless."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt  # noqa: E402

from gguf_dictate.ui.overlay import Overlay  # noqa: E402


@pytest.fixture
def ov(qtbot):
    got = []
    o = Overlay(extra=got.append)
    qtbot.addWidget(o)
    o.show()
    qtbot.waitExposed(o)
    o.got = got
    return o


def alpha_at_centre(o):
    img = o.grab().toImage()
    return img.pixelColor(img.width() // 2, img.height() // 2).alpha()


def test_is_click_through_never_takes_focus_and_is_transparent(ov):
    flags = ov.windowFlags()
    assert flags & Qt.WindowTransparentForInput and flags & Qt.WindowDoesNotAcceptFocus and flags & Qt.WindowStaysOnTopHint
    assert ov.testAttribute(Qt.WA_TranslucentBackground) and ov.testAttribute(Qt.WA_ShowWithoutActivating)


def test_invisible_when_idle(ov):
    assert alpha_at_centre(ov) == 0


def test_recording_draws_a_pill_then_idle_fades_it_out(ov, qtbot):
    ov.handle("rec")
    qtbot.waitUntil(lambda: ov.model.alpha > 0.9, timeout=3000)
    assert alpha_at_centre(ov) > 100
    ov.handle("idle")
    qtbot.waitUntil(lambda: ov.model.alpha == 0.0 and ov.timer is None, timeout=3000)
    assert alpha_at_centre(ov) == 0


def test_busy_shows_spinner(ov, qtbot):
    ov.handle("busy")
    qtbot.waitUntil(lambda: ov.model.alpha > 0.9, timeout=3000)
    assert alpha_at_centre(ov) > 100


def test_non_animation_messages_go_to_the_extra_callback(ov):
    ov.handle("snip")
    ov.handle("note hello there")
    assert ov.got == ["snip", "note hello there"]
    assert ov.model.state == "idle"


def test_post_is_thread_safe_entry_point(ov, qtbot):
    import threading
    t = threading.Thread(target=lambda: ov.post("snip"))
    t.start()
    t.join()
    qtbot.waitUntil(lambda: ov.got == ["snip"], timeout=2000)


def test_sits_at_bottom_centre_of_screen(ov):
    g = ov.screen().availableGeometry()
    assert abs(ov.geometry().center().x() - g.center().x()) <= 1
    assert ov.geometry().bottom() <= g.bottom()
