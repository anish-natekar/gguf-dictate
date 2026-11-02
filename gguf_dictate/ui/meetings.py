"""Meetings window: month calendar, day list, full-text search, notes, transcript and a Generate button.

The model, file opening and delete confirmation are injected, so the window can be tested without any of them.
`transcribe(meeting, progress, cancelled)` runs on a worker thread and raises Cancelled when asked to stop.
"""
import threading

from PySide6.QtCore import QDate, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QGuiApplication, QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from gguf_dictate.core.meeting_transcribe import Cancelled
from gguf_dictate.core.meeting_view import export_markdown, format_transcript, row_text, status_label
from gguf_dictate.core.pill_model import format_elapsed

NOTES_SAVE_MS = 800
HIGHLIGHT = QColor("#0a84ff")


def default_open(path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def default_confirm(m):
    box = QMessageBox.question(None, "Delete meeting", f"Delete '{m.title}' and its recordings? This cannot be undone.")
    return box == QMessageBox.Yes


class MeetingsWindow(QWidget):
    progress_changed = Signal(float)
    job_done = Signal(str, str)      # meeting id, error text ("" on success)

    def __init__(self, library, transcribe=None, open_path=default_open, confirm_delete=default_confirm):
        super().__init__()
        self.library, self.transcribe, self.open_path, self.confirm_delete = library, transcribe, open_path, confirm_delete
        self.current, self.running = None, None      # selected meeting id; {"id", "cancel"} while a job runs
        self.setWindowTitle("Meetings")
        self.resize(1040, 660)
        self.build()
        self.notes_timer = QTimer(self)
        self.notes_timer.setSingleShot(True)
        self.notes_timer.timeout.connect(self.save_notes)
        latest = library.all()
        if latest:
            self.calendar.setSelectedDate(QDate(latest[0].start.year, latest[0].start.month, latest[0].start.day))
        self.connect_signals()
        self.highlight()
        self.populate()

    def set_transcribe(self, transcribe):
        """Called once the speech model has loaded (or unloaded, with None)."""
        self.transcribe = transcribe
        self.show_job_state(self.selected())

    def build(self):
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.search = QLineEdit(placeholderText="Search titles, notes and transcripts")
        self.search.setClearButtonEnabled(True)
        self.list = QListWidget()
        left = QWidget()
        col = QVBoxLayout(left)
        for w in (self.calendar, self.search, self.list):
            col.addWidget(w)
        col.setStretch(2, 1)

        self.title = QLineEdit()
        self.title.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.meta = QLabel()
        self.generate = QPushButton("Generate transcript")
        self.cancel = QPushButton("Cancel")
        self.cancel.setVisible(False)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.notes = QPlainTextEdit(placeholderText="Notes")
        self.notes.setMaximumHeight(130)
        self.transcript = QPlainTextEdit(readOnly=True, placeholderText="No transcript yet. Press Generate transcript.")
        self.open_mic, self.open_system = QPushButton("Open mic audio"), QPushButton("Open system audio")
        self.copy_btn, self.delete_btn = QPushButton("Copy as Markdown"), QPushButton("Delete")
        self.detail = QWidget()
        box = QVBoxLayout(self.detail)
        box.addWidget(self.title)
        box.addWidget(self.meta)
        job = QHBoxLayout()
        for w in (self.generate, self.cancel, self.progress):
            job.addWidget(w)
        job.setStretch(2, 1)
        box.addLayout(job)
        box.addWidget(self.status)
        box.addWidget(QLabel("Notes"))
        box.addWidget(self.notes)
        box.addWidget(QLabel("Transcript"))
        box.addWidget(self.transcript, 1)
        bottom = QHBoxLayout()
        for w in (self.open_mic, self.open_system, self.copy_btn):
            bottom.addWidget(w)
        bottom.addStretch(1)
        bottom.addWidget(self.delete_btn)
        box.addLayout(bottom)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(self.detail)
        split.setStretchFactor(1, 1)
        outer = QHBoxLayout(self)
        outer.addWidget(split)

    def connect_signals(self):
        self.calendar.selectionChanged.connect(self.populate)
        self.calendar.currentPageChanged.connect(lambda *_: self.highlight())
        self.search.textChanged.connect(self.populate)
        self.list.currentRowChanged.connect(self.on_row)
        self.title.editingFinished.connect(self.save_title)
        self.notes.textChanged.connect(lambda: self.notes_timer.start(NOTES_SAVE_MS))
        self.generate.clicked.connect(self.start_job)
        self.cancel.clicked.connect(self.cancel_job)
        self.progress_changed.connect(self.on_progress)
        self.job_done.connect(self.on_job_done)
        self.open_mic.clicked.connect(lambda: self.open_path(self.selected().mic_path))
        self.open_system.clicked.connect(lambda: self.open_path(self.selected().system_path))
        self.copy_btn.clicked.connect(self.copy_markdown)
        self.delete_btn.clicked.connect(self.delete_selected)

    # ----- list and calendar

    def highlight(self):
        self.calendar.setDateTextFormat(QDate(), QTextCharFormat())      # a null date clears every mark
        fmt = QTextCharFormat()
        fmt.setBackground(QBrush(HIGHLIGHT))
        fmt.setForeground(QBrush(QColor("white")))
        fmt.setFontWeight(700)
        year, month = self.calendar.yearShown(), self.calendar.monthShown()
        for day in self.library.days_with_meetings(year, month):
            self.calendar.setDateTextFormat(QDate(year, month, day), fmt)

    def shown(self):
        query = self.search.text().strip()
        if query:
            return self.library.search(query), True
        return self.library.on_day(self.calendar.selectedDate().toPython()), False

    def populate(self, *_):
        """Rebuild the list for the picked day (or the search), keeping the selection if that meeting is still listed."""
        self.save_notes()
        meetings, with_date = self.shown()
        self.list.blockSignals(True)
        self.list.clear()
        for m in meetings:
            item = QListWidgetItem((f"{m.start:%Y-%m-%d}  " if with_date else "") + row_text(m))
            item.setData(Qt.UserRole, m.id)
            self.list.addItem(item)
            if m.id == self.current:
                self.list.setCurrentItem(item)
        if self.list.currentRow() < 0 and meetings:
            self.list.setCurrentRow(0)
        self.list.blockSignals(False)
        item = self.list.currentItem()
        self.current = item.data(Qt.UserRole) if item else None
        self.show_current()

    def refresh(self):
        self.highlight()
        self.populate()

    def on_row(self, row):
        self.save_notes()
        item = self.list.item(row)
        self.current = item.data(Qt.UserRole) if item else None
        self.show_current()

    def selected(self):
        try:
            return self.library.get(self.current) if self.current else None
        except KeyError:
            return None

    # ----- detail pane

    def show_current(self):
        m = self.selected()
        self.detail.setEnabled(m is not None)
        self.status.clear()
        for w in (self.title, self.notes):
            w.blockSignals(True)
        if m is None:
            self.title.clear()
            self.notes.clear()
            self.meta.clear()
            self.transcript.clear()
        else:
            self.title.setText(m.title)
            self.notes.setPlainText(self.library.notes(m))
            self.meta.setText(f"{m.start:%A %d %B %Y, %H:%M}   {format_elapsed(m.duration)}   {status_label(m.status)}")
            self.transcript.setPlainText(format_transcript(self.library.transcript(m)))
        for w in (self.title, self.notes):
            w.blockSignals(False)
        self.show_job_state(m)

    def show_job_state(self, m):
        busy = self.running is not None
        mine = busy and m is not None and self.running["id"] == m.id
        self.cancel.setVisible(mine)
        self.progress.setVisible(mine)
        self.delete_btn.setEnabled(m is not None and not mine)
        self.open_mic.setEnabled(m is not None and m.mic_path.exists())
        self.open_system.setEnabled(m is not None and m.system_path.exists())
        self.generate.setText("Regenerate transcript" if m is not None and m.status == "transcribed" else "Generate transcript")
        self.generate.setEnabled(m is not None and self.transcribe is not None and not busy and m.status != "recording")
        self.generate.setToolTip("" if self.transcribe is not None else "The speech model is not loaded yet")

    def save_title(self):
        m = self.selected()
        text = self.title.text().strip()
        if m is None:
            return
        if not text:
            self.title.setText(m.title)
            return
        if text != m.title:
            self.library.set_title(m, text)
            self.populate()

    def save_notes(self):
        self.notes_timer.stop()
        m = self.selected()
        if m is not None and self.notes.toPlainText() != self.library.notes(m):
            self.library.set_notes(m, self.notes.toPlainText())

    def closeEvent(self, event):
        self.save_notes()
        super().closeEvent(event)

    # ----- transcription job

    def start_job(self):
        m = self.selected()
        if m is None or self.running or self.transcribe is None:
            return
        job = self.running = {"id": m.id, "cancel": False}
        self.progress.setValue(0)
        self.status.clear()
        self.show_job_state(m)

        def work():
            error = ""
            try:
                self.transcribe(m, self.progress_changed.emit, lambda: job["cancel"])
            except Cancelled:
                error = "cancelled"
            except Exception as e:      # shown in the window, never allowed to kill the worker silently
                error = str(e) or type(e).__name__
            self.job_done.emit(m.id, error)

        threading.Thread(target=work, daemon=True).start()

    def cancel_job(self):
        if self.running:
            self.running["cancel"] = True
            self.status.setText("Cancelling...")

    def on_progress(self, fraction):
        if self.running and self.running["id"] == self.current:
            self.progress.setValue(int(fraction * 100))

    def on_job_done(self, meeting_id, error):
        self.running = None
        self.populate()
        if error == "cancelled":
            self.status.setText("Cancelled.")
        elif error:
            self.status.setText(f"Transcription failed: {error}")

    # ----- actions

    def copy_markdown(self):
        m = self.selected()
        if m is not None:
            QGuiApplication.clipboard().setText(export_markdown(m, self.library.notes(m), self.library.transcript(m)))
            self.status.setText("Copied to the clipboard.")

    def delete_selected(self):
        m = self.selected()
        if m is None or not self.confirm_delete(m):
            return
        self.notes_timer.stop()
        self.current = None
        self.library.delete(m)
        self.highlight()
        self.populate()
