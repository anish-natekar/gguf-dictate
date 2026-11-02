"""Annotation editor state (tools, strokes, box, undo, notes, toolbar focus) with no GUI toolkit."""
from gguf_dictate.core.editor_model import EditorModel

COLORS = [["Red", "#ff3b30"], ["Blue", "#0a84ff"], ["Green", "#30d158"]]


def model():
    return EditorModel(COLORS)


# --- tools and notes --------------------------------------------------------

def test_starts_on_box_tool_whole_screen_with_general_slot():
    m = model()
    assert m.sel is None and m.rect is None and not m.talking
    assert len(m.notes) == len(COLORS) + 1 and m.note_slot() == len(COLORS)
    assert m.hint == "Drag to choose the area, then pick a colour to draw"


def test_pick_colour_sets_slot_and_hint_and_rejects_out_of_range():
    m = model()
    m.pick(1)
    assert m.sel == 1 and m.note_slot() == 1 and m.hint == "Drawing in Blue  -  speak to add a note"
    m.pick(7)
    assert m.sel == 1
    m.pick(None)
    assert m.sel is None and m.focus == 0


def test_add_note_goes_under_selected_colour_and_stops_talking():
    m = model()
    m.talking = True
    m.pick(0)
    m.add_note("overlaps")
    m.pick(None)
    m.add_note("overall bad")
    assert not m.talking
    assert m.notes_for_save() == [{"color": "Red", "text": "overlaps"}, {"color": "General", "text": "overall bad"}]


def test_notes_for_save_orders_by_colour_slot_then_general():
    m = model()
    m.pick(2)
    m.add_note("g")
    m.pick(0)
    m.add_note("r1")
    m.add_note("r2")
    m.pick(None)
    m.add_note("gen")
    assert [(n["color"], n["text"]) for n in m.notes_for_save()] == [("Red", "r1"), ("Red", "r2"), ("Green", "g"), ("General", "gen")]


def test_remove_last_note_only_affects_current_slot():
    m = model()
    m.pick(0)
    m.add_note("a")
    m.pick(1)
    m.add_note("b")
    m.add_note("c")
    assert m.remove_last_note() == "c"
    assert [n["text"] for n in m.notes_for_save()] == ["a", "b"]
    m.pick(2)
    assert m.remove_last_note() is None


def test_panel_rows_show_only_colours_with_notes_and_current_target():
    m = model()
    m.pick(1)
    m.add_note("x")
    assert m.panel_title() == "Notes -> Blue"
    assert m.panel_rows() == [("Blue", "#0a84ff", ["x"])]
    m.talking = True
    assert m.panel_title() == "Recording..."
    assert m.panel_visible()
    m.talking = False
    assert model().panel_visible() is False


# --- strokes, box, undo -----------------------------------------------------

def test_box_tool_does_not_draw():
    m = model()
    m.press(10, 10)
    m.move(20, 20)
    m.release()
    assert m.strokes == []


def test_pen_stroke_records_colour_width_and_points():
    m = model()
    m.pick(1)
    m.press(1, 2)
    m.move(3, 4)
    m.move(5, 6)
    m.release()
    assert m.strokes == [{"color": 1, "w": 5, "pts": [(1, 2), (3, 4), (5, 6)]}]


def test_motion_without_press_does_nothing():
    m = model()
    m.pick(0)
    assert m.move(5, 5) is False and m.strokes == []


def test_box_drag_sets_rect_normalised_any_direction():
    m = model()
    m.press(100, 80)
    m.move(40, 20)
    m.release()
    assert m.rect == (40, 20, 60, 60)


def test_tiny_drag_or_click_keeps_previous_box_and_adds_no_undo_step():
    m = model()
    m.press(0, 0)
    m.move(100, 100)
    m.release()
    assert m.rect == (0, 0, 100, 100) and len(m.history) == 1
    m.press(50, 50)
    m.move(55, 55)
    m.release()
    assert m.rect == (0, 0, 100, 100) and len(m.history) == 1


def test_redrawing_box_then_undo_restores_previous_box():
    m = model()
    m.press(0, 0)
    m.move(100, 100)
    m.release()
    m.press(10, 10)
    m.move(60, 70)
    m.release()
    assert m.rect == (10, 10, 50, 60)
    m.undo()
    assert m.rect == (0, 0, 100, 100)
    m.undo()
    assert m.rect is None


def test_undo_unwinds_strokes_and_box_in_order():
    m = model()
    m.press(0, 0)
    m.move(50, 50)
    m.release()          # box
    m.pick(0)
    m.press(1, 1)
    m.release()                          # stroke 1
    m.press(2, 2)
    m.release()                          # stroke 2
    m.undo()
    assert len(m.strokes) == 1 and m.rect == (0, 0, 50, 50)
    m.undo()
    assert m.strokes == [] and m.rect == (0, 0, 50, 50)
    m.undo()
    assert m.rect is None
    m.undo()                                            # nothing left: no error
    assert m.history == []


def test_clear_removes_strokes_but_keeps_box_undo_history():
    m = model()
    m.press(0, 0)
    m.move(50, 50)
    m.release()
    m.pick(0)
    m.press(1, 1)
    m.release()
    m.clear()
    assert m.strokes == [] and m.history == [("rect", None)]
    m.undo()
    assert m.rect is None


def test_full_screen_resets_box_and_is_undoable_only_if_there_was_a_box():
    m = model()
    m.full_screen()
    assert m.history == []
    m.press(0, 0)
    m.move(50, 50)
    m.release()
    m.full_screen()
    assert m.rect is None
    m.undo()
    assert m.rect == (0, 0, 50, 50)


def test_cycle_pen_size_thin_medium_thick():
    m = model()
    assert m.width == 5
    m.cycle_size()
    assert m.width == 9 and m.hint == "Pen size: Thick"
    m.cycle_size()
    assert m.width == 3 and m.hint == "Pen size: Thin"
    m.cycle_size()
    assert m.width == 5 and m.hint == "Pen size: Medium"


# --- toolbar focus ----------------------------------------------------------

def test_toolbar_items_order_and_kinds():
    m = model()
    kinds = [k for _, k, _ in m.items]
    assert kinds == ["tool"] * 4 + ["action"] * 7
    assert [a for _, _, a in m.items][4:] == ["size", "full", "undo", "clear", "speak", "save", "cancel"]


def test_arrowing_over_colours_selects_them_and_actions_show_hint():
    m = model()
    assert m.move_focus(1) == ("select", 0) and m.sel == 0
    m.move_focus(1)
    m.move_focus(1)
    assert m.sel == 2
    assert m.move_focus(1) == ("hint", None) and m.hint == "Pen size  -  Enter to use"


def test_focus_wraps_both_ways():
    m = model()
    m.move_focus(-1)
    assert m.focus == len(m.items) - 1 and m.items[m.focus][2] == "cancel"
    m.move_focus(1)
    assert m.focus == 0


def test_activate_focus_returns_action_name_only_for_actions():
    m = model()
    assert m.activate_focus() is None
    for _ in range(4):
        m.move_focus(1)
    assert m.activate_focus() == "size"
    m.move_focus(-1)
    assert m.activate_focus() is None                   # a colour tool: already selected by arrowing
