"""Qt annotation editor, driven headless (QT_QPA_PLATFORM=offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPixmap  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from gguf_dictate.ui.editor import EditorView  # noqa: E402

COLORS = [["Red", "#ff0000"], ["Blue", "#0000ff"], ["Green", "#00ff00"]]


@pytest.fixture
def env(qtbot, tmp_path):
    shot = QPixmap(800, 600)
    shot.fill(QColor("#222222"))
    done, spoke = [], []
    flag = tmp_path / "editor-open"
    view = EditorView(shot, COLORS, lambda surf, notes: done.append((surf, notes)), spoke.append, flag=flag, fullscreen=False)
    qtbot.addWidget(view)
    view.show()
    qtbot.waitExposed(view)
    view.done, view.spoke, view.flag = done, spoke, flag
    return view


def drag(view, a, b):
    c = view.canvas
    QTest.mousePress(c, Qt.LeftButton, Qt.NoModifier, QPoint(*a))
    QTest.mouseMove(c, QPoint(*b))
    QTest.mouseRelease(c, Qt.LeftButton, Qt.NoModifier, QPoint(*b))


def test_toolbar_has_a_button_per_model_item(env):
    assert len(env.buttons) == len(env.model.items) == 11


def test_flag_exists_while_open_and_removed_on_close(env, qtbot):
    assert env.flag.exists()
    env.close()
    assert not env.flag.exists()


def test_number_keys_pick_colours_and_0_returns_to_box_tool(env, qtbot):
    qtbot.keyClick(env, Qt.Key_2)
    assert env.model.sel == 1 and env.buttons[2].isChecked()
    qtbot.keyClick(env, Qt.Key_0)
    assert env.model.sel is None and env.buttons[0].isChecked()


def test_box_tool_drag_sets_capture_box(env):
    drag(env, (100, 100), (300, 250))
    assert env.model.rect == (100, 100, 200, 150)


def test_pen_drag_adds_stroke_and_ctrl_z_undoes_it(env, qtbot):
    qtbot.keyClick(env, Qt.Key_1)
    drag(env, (50, 50), (120, 90))
    assert len(env.model.strokes) == 1
    qtbot.keyClick(env, Qt.Key_Z, Qt.ControlModifier)
    assert env.model.strokes == []


def test_save_returns_cropped_png_with_stroke_pixels_and_notes(env, qtbot, tmp_path):
    drag(env, (100, 100), (300, 250))                 # box tool
    qtbot.keyClick(env, Qt.Key_1)
    drag(env, (150, 150), (250, 150))                 # horizontal red stroke inside the box
    env.add_note("button overlaps label")
    qtbot.keyClick(env, Qt.Key_Return, Qt.ControlModifier)
    (surface, notes), = env.done
    assert notes == [{"color": "Red", "text": "button overlaps label"}]
    out = tmp_path / "snip.png"
    surface.write_to_png(str(out))
    img = QImage(str(out))
    assert (img.width(), img.height()) == (200, 150)
    assert QColor(img.pixel(100, 50)).red() > 200 and QColor(img.pixel(100, 50)).green() < 60     # stroke at (200,150) -> (100,50)
    assert QColor(img.pixel(5, 5)).name() == "#222222"                                           # untouched background
    assert not env.isVisible() and not env.flag.exists()


def test_save_without_box_captures_whole_screenshot(env, qtbot, tmp_path):
    qtbot.keyClick(env, Qt.Key_Return, Qt.ControlModifier)
    (surface, _), = env.done
    surface.write_to_png(str(tmp_path / "a.png"))
    img = QImage(str(tmp_path / "a.png"))
    assert (img.width(), img.height()) == (800, 600)


def test_escape_cancels_without_saving_and_stops_a_running_recording(env, qtbot):
    env.toggle_speak()
    assert env.spoke == ["start"] and env.model.talking
    qtbot.keyClick(env, Qt.Key_Escape)
    assert env.done == [] and not env.isVisible() and env.spoke == ["start", "stop"]


def test_save_stops_a_running_recording_too(env, qtbot):
    env.toggle_speak()
    qtbot.keyClick(env, Qt.Key_Return, Qt.ControlModifier)
    assert env.spoke == ["start", "stop"] and len(env.done) == 1


def test_voice_note_appears_in_panel_and_clears_recording_state(env):
    env.toggle_speak()
    assert env.panel.isVisibleTo(env) and "Recording" in env.panel_title.text()
    env.add_note("icon misaligned")
    assert not env.model.talking
    assert "icon misaligned" in env.panel_text()


def test_blue_capture_box_boundary_is_painted(env):
    drag(env, (100, 100), (300, 250))
    img = env.canvas.grab().toImage()
    edge = QColor(img.pixel(99, 150))                 # just outside the left edge of the box = the blue outline
    assert edge.blue() > 200 and edge.red() < 60


def test_full_screen_frame_is_blue_when_no_box(env):
    img = env.canvas.grab().toImage()
    c = QColor(img.pixel(2, 300))
    assert c.blue() > 200 and c.red() < 60


def test_arrow_keys_move_toolbar_focus_and_select_colours(env, qtbot):
    qtbot.keyClick(env, Qt.Key_Right)
    assert env.model.sel == 0 and env.buttons[1].isChecked()
    qtbot.keyClick(env, Qt.Key_Left)
    assert env.model.sel is None


def test_enter_activates_focused_action_button(env, qtbot):
    for _ in range(4):
        qtbot.keyClick(env, Qt.Key_Right)             # box, red, blue, green -> size
    before = env.model.width
    qtbot.keyClick(env, Qt.Key_Return)
    assert env.model.width != before


def test_f_key_resets_box_to_full_screen(env, qtbot):
    drag(env, (100, 100), (300, 250))
    qtbot.keyClick(env, Qt.Key_F)
    assert env.model.rect is None


def test_backspace_removes_last_note(env, qtbot):
    env.add_note("a")
    env.add_note("b")
    qtbot.keyClick(env, Qt.Key_Backspace)
    assert env.model.notes_for_save() == [{"color": "General", "text": "a"}]


def test_clicking_toolbar_swatch_selects_colour(env, qtbot):
    qtbot.mouseClick(env.buttons[3], Qt.LeftButton)
    assert env.model.sel == 2


def test_queue_badge_text(env):
    env.set_queued(3)
    assert "3" in env.queue_badge.text()
    env.set_queued(0)
    assert env.queue_badge.isHidden()


def test_on_close_callback_runs_when_editor_closes(qtbot, tmp_path):
    from PySide6.QtGui import QPixmap

    from gguf_dictate.ui.editor import EditorView
    closed = []
    v = EditorView(QPixmap(200, 120), [["Red", "#ff0000"]], lambda *a: None, lambda c: None, flag=tmp_path / "flag", fullscreen=False,
                   on_close=lambda: closed.append(1))
    qtbot.addWidget(v)
    v.show()
    v.close()
    assert closed == [1]
