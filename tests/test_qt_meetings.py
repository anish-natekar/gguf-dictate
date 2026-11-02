"""Meetings library window, headless."""
import os
import threading
from datetime import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")
from PySide6.QtCore import QDate, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from gguf_dictate.core.meeting_transcribe import Cancelled  # noqa: E402
from gguf_dictate.core.meetings import Library  # noqa: E402
from gguf_dictate.ui.meetings import MeetingsWindow  # noqa: E402

SEGS = [{"t0": 0.0, "t1": 4.0, "speaker": "Me", "text": "Shall we begin?"}, {"t0": 65.0, "t1": 70.0, "speaker": "Them", "text": "Yes, go ahead."}]


@pytest.fixture
def lib(tmp_path):
    lib = Library(tmp_path)
    a = lib.create(datetime(2026, 11, 3, 9, 0))
    lib.set_title(a, "Standup")
    lib.finish(a, 600)
    a.mic_path.write_bytes(b"x")
    b = lib.create(datetime(2026, 11, 3, 15, 0))
    lib.set_title(b, "Budget review")
    lib.finish(b, 3725)
    lib.set_notes(b, "decide the budget")
    lib.set_transcript(b, SEGS)
    c = lib.create(datetime(2026, 11, 20, 10, 0))
    lib.set_title(c, "Planning")
    lib.finish(c, 300)
    lib.a, lib.b, lib.c = a, b, c
    return lib


class Env:
    def __init__(self, lib, transcribe=None, confirm=True):
        self.opened, self.asked = [], []
        self.win = MeetingsWindow(lib, transcribe=transcribe, open_path=self.opened.append,
                                  confirm_delete=lambda m: self.asked.append(m.id) or confirm)


@pytest.fixture
def make(qtbot, lib):
    def build(**kw):
        env = Env(lib, **kw)
        qtbot.addWidget(env.win)
        return env
    return build


def go(win, y, m, d):
    win.calendar.setSelectedDate(QDate(y, m, d))


def titles(win):
    return [win.list.item(i).text() for i in range(win.list.count())]


def test_opens_on_the_day_of_the_latest_meeting(make):
    win = make().win
    assert win.calendar.selectedDate() == QDate(2026, 11, 20)
    assert len(titles(win)) == 1 and "Planning" in titles(win)[0] and win.title.text() == "Planning"


def test_days_with_meetings_are_highlighted_in_the_month_grid(make):
    win = make().win
    marked = lambda d: win.calendar.dateTextFormat(QDate(2026, 11, d)).background().style() != Qt.NoBrush    # noqa: E731
    assert marked(3) and marked(20) and not marked(4)


def test_changing_month_highlights_that_months_days(make, lib):
    lib.create(datetime(2026, 12, 9, 8, 0))
    win = make().win
    win.calendar.setCurrentPage(2026, 12)
    assert win.calendar.dateTextFormat(QDate(2026, 12, 9)).background().style() != Qt.NoBrush


def test_picking_a_day_lists_its_meetings_newest_first(make):
    win = make().win
    go(win, 2026, 11, 3)
    assert [t.split("   ")[1] for t in titles(win)] == ["Budget review", "Standup"]
    assert win.title.text() == "Budget review"      # first row is selected


def test_a_day_without_meetings_disables_the_detail_pane(make):
    win = make().win
    go(win, 2026, 11, 5)
    assert titles(win) == [] and not win.detail.isEnabled()


def test_empty_library_opens_cleanly(qtbot, tmp_path):
    win = MeetingsWindow(Library(tmp_path))
    qtbot.addWidget(win)
    assert win.list.count() == 0 and not win.detail.isEnabled()


def test_search_looks_across_all_days_and_clearing_returns_to_the_day(make):
    win = make().win
    win.search.setText("budget")
    assert len(titles(win)) == 1 and "2026-11-03" in titles(win)[0] and win.title.text() == "Budget review"
    win.search.setText("hello zzz")
    assert titles(win) == []
    win.search.setText("")
    assert "Planning" in titles(win)[0]


def test_search_finds_words_in_the_transcript(make):
    win = make().win
    win.search.setText("ahead")
    assert win.title.text() == "Budget review"


def test_selecting_a_meeting_shows_its_details(make):
    win = make().win
    go(win, 2026, 11, 3)
    win.list.setCurrentRow(0)
    assert win.title.text() == "Budget review"
    assert "1:02:05" in win.meta.text() and "transcribed" in win.meta.text()
    assert win.notes.toPlainText() == "decide the budget"
    assert win.transcript.toPlainText() == "[0:00] Me: Shall we begin?\n[1:05] Them: Yes, go ahead."


def test_editing_the_title_saves_and_updates_the_row(make, lib):
    win = make().win
    go(win, 2026, 11, 3)
    win.list.setCurrentRow(1)
    win.title.setText("Daily sync")
    win.title.editingFinished.emit()
    assert lib.get(lib.a.id).title == "Daily sync" and "Daily sync" in win.list.item(1).text()


def test_a_blank_title_is_rejected(make, lib):
    win = make().win
    win.title.setText("   ")
    win.title.editingFinished.emit()
    assert lib.get(lib.c.id).title == "Planning" and win.title.text() == "Planning"


def test_notes_are_saved_when_you_switch_meetings(make, lib):
    win = make().win
    go(win, 2026, 11, 3)
    win.list.setCurrentRow(1)
    win.notes.setPlainText("remember the milk")
    win.list.setCurrentRow(0)
    assert lib.notes(lib.a) == "remember the milk"


def test_notes_are_saved_after_a_pause_in_typing(make, lib, qtbot):
    win = make().win
    win.notes.setPlainText("typed")
    qtbot.waitUntil(lambda: lib.notes(lib.c) == "typed", timeout=3000)


def test_notes_are_saved_when_the_window_closes(make, lib):
    win = make().win
    win.notes.setPlainText("last words")
    win.close()
    assert lib.notes(lib.c) == "last words"


def test_generate_transcribes_in_the_background_and_shows_the_result(make, lib, qtbot):
    release, seen = threading.Event(), []

    def fake(m, progress, cancelled):
        progress(0.5)
        release.wait(3)
        lib.set_transcript(m, SEGS)
        seen.append(m.id)

    win = make(transcribe=fake).win
    assert win.generate.isEnabled()
    with qtbot.waitSignal(win.job_done, timeout=5000):
        win.generate.click()
        assert not win.generate.isEnabled() and not win.cancel.isHidden() and not win.delete_btn.isEnabled()
        qtbot.waitUntil(lambda: win.progress.value() == 50, timeout=3000)
        release.set()
    assert seen == [lib.c.id]
    assert "Yes, go ahead." in win.transcript.toPlainText() and "transcribed" in win.meta.text()
    assert win.cancel.isHidden() and win.generate.text() == "Regenerate transcript"
    assert "transcribed" in win.list.item(0).text()


def test_cancel_stops_the_job_and_leaves_the_meeting_untranscribed(make, lib, qtbot):
    def fake(m, progress, cancelled):
        while not cancelled():
            threading.Event().wait(0.01)
        raise Cancelled()

    win = make(transcribe=fake).win
    with qtbot.waitSignal(win.job_done, timeout=5000):
        win.generate.click()
        win.cancel.click()
    assert "ancel" in win.status.text() and lib.transcript(lib.c) == [] and win.generate.isEnabled()


def test_a_failed_job_reports_the_error_and_the_window_survives(make, lib, qtbot):
    def fake(m, progress, cancelled):
        raise RuntimeError("model fell over")

    win = make(transcribe=fake).win
    with qtbot.waitSignal(win.job_done, timeout=5000):
        win.generate.click()
    assert "model fell over" in win.status.text() and win.generate.isEnabled()


def test_generate_is_disabled_without_a_model(make):
    win = make(transcribe=None).win
    assert not win.generate.isEnabled() and win.generate.toolTip()


def test_only_one_job_runs_at_a_time(make, qtbot):
    release = threading.Event()
    win = make(transcribe=lambda m, p, c: release.wait(3)).win
    with qtbot.waitSignal(win.job_done, timeout=5000):
        win.generate.click()
        go(win, 2026, 11, 3)
        assert not win.generate.isEnabled()      # another meeting, but the model is busy
        release.set()


def test_delete_asks_first(make, lib):
    env = make(confirm=False)
    env.win.delete_btn.click()
    assert env.asked == [lib.c.id] and lib.get(lib.c.id)


def test_delete_removes_the_meeting_everywhere(make, lib):
    env = make(confirm=True)
    go(env.win, 2026, 11, 3)
    env.win.list.setCurrentRow(0)
    env.win.delete_btn.click()
    assert [m.id for m in lib.all()] == [lib.c.id, lib.a.id]
    assert [t.split("   ")[1] for t in titles(env.win)] == ["Standup"]


def test_audio_buttons_open_existing_files_only(make, lib):
    env = make()
    go(env.win, 2026, 11, 3)
    env.win.list.setCurrentRow(1)      # Standup has a mic file but no system file
    assert env.win.open_mic.isEnabled() and not env.win.open_system.isEnabled()
    env.win.open_mic.click()
    assert env.opened == [lib.a.mic_path]


def test_copy_puts_markdown_on_the_clipboard(make):
    win = make().win
    go(win, 2026, 11, 3)
    win.list.setCurrentRow(0)
    win.copy_btn.click()
    text = QGuiApplication.clipboard().text()
    assert text.startswith("# Budget review") and "decide the budget" in text and "**Them** [1:05] Yes, go ahead." in text


def test_refresh_picks_up_a_meeting_recorded_while_the_window_is_open(make, lib):
    win = make().win
    lib.create(datetime(2026, 11, 20, 18, 0))
    win.refresh()
    assert len(titles(win)) == 2


def test_generate_enables_once_the_model_arrives(make):
    win = make(transcribe=None).win
    assert not win.generate.isEnabled()
    win.set_transcribe(lambda m, p, c: None)
    assert win.generate.isEnabled() and not win.generate.toolTip()
    win.set_transcribe(None)
    assert not win.generate.isEnabled()
