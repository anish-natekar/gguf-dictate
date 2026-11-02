"""Meeting recording controller: owns the recorder, the floating pill and the Meetings window.

The recorder, pill and window are injected as factories so the controller can be tested without audio or a display.
"""
from PySide6.QtCore import QObject, QTimer, Signal

from ..config import load_config, save_config
from ..core.meeting_recorder import repair
from ..core.meeting_transcribe import transcribe_meeting

TICK_MS = 250


class MeetingController(QObject):
    changed = Signal()      # recording started or stopped (the tray menu follows)

    def __init__(self, library, make_recorder, make_pill, make_window, toast, show_error, load_cfg=load_config, save_cfg=save_config,
                 confirm_discard=lambda: True):
        super().__init__()
        self.library, self.make_recorder, self.make_pill, self.make_window = library, make_recorder, make_pill, make_window
        self.toast, self.show_error, self.load_cfg, self.save_cfg, self.confirm_discard = toast, show_error, load_cfg, save_cfg, confirm_discard
        self.recorder, self.pill, self.window, self.model = None, None, None, None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)

    @property
    def recording(self):
        return self.recorder is not None

    @property
    def active(self):
        """The pill is on screen, ready or recording."""
        return self.pill is not None

    # ---- recording --------------------------------------------------------
    def toggle(self):
        """Hotkey / tray: show the recorder pill; again to dismiss it if unused. A running meeting is only ended from the pill's save button."""
        if self.recording:
            return
        self.stop() if self.active else self.arm()

    def arm(self):
        """Show the pill ready to record. Nothing is recorded until its record button is pressed."""
        if self.active:
            return
        pos = self.load_cfg().get("pill_pos")
        self.pill = self.make_pill(tuple(pos) if pos else None)
        self.pill.record_clicked.connect(self.start)
        self.pill.pause_clicked.connect(self.pause)
        self.pill.stop_clicked.connect(self.stop)
        self.pill.cancel_clicked.connect(self.cancel)
        self.pill.moved.connect(self.remember_pill)
        self.pill.show()
        self.changed.emit()

    def start(self):
        if self.recording or not self.active:
            return
        recorder = self.make_recorder(self.library)
        try:
            recorder.start()
        except Exception as e:      # noqa: BLE001 - usually a missing or busy microphone
            self.show_error("Meeting could not start", str(e))
            return
        self.recorder = recorder
        self.pill.set_recording(True)
        self.timer.start(TICK_MS)
        self.changed.emit()
        for warning in recorder.warnings:
            self.toast("Meeting recording", warning)

    def pause(self):
        if not self.recording:
            return
        rec = self.recorder
        rec.resume() if rec.paused else rec.pause()
        self.pill.set_paused(rec.paused)

    def stop(self):
        if not self.active:
            return
        rec, pill = self.recorder, self.pill
        self.recorder = self.pill = None
        self.timer.stop()
        pill.close()
        if rec is None:      # dismissed before recording
            self.changed.emit()
            return
        meeting = rec.stop()
        for warning in rec.warnings:
            self.toast("Meeting recording", warning)
        self.changed.emit()
        self.toast("Meeting saved", f"{meeting.title} - open Meetings to generate the transcript.")
        if self.window:
            self.window.refresh()

    def cancel(self):
        """Close the pill. A running recording is thrown away, after asking."""
        if not self.active:
            return
        if self.recording and not self.confirm_discard():
            return
        rec, pill = self.recorder, self.pill
        self.recorder = self.pill = None
        self.timer.stop()
        pill.close()
        if rec is not None:
            meeting = rec.stop()
            self.library.delete(meeting)
            self.toast("Recording discarded", "The meeting was not saved.")
            if self.window:
                self.window.refresh()
        self.changed.emit()

    def tick(self):
        if self.recording:
            self.pill.set_elapsed(self.recorder.elapsed)

    def remember_pill(self, x, y):
        cfg = self.load_cfg()
        cfg["pill_pos"] = [x, y]
        self.save_cfg(cfg)

    def shutdown(self):
        self.stop()

    # ---- library window ---------------------------------------------------
    def transcriber(self):
        model = self.model
        if model is None:
            return None
        return lambda meeting, progress, cancelled: transcribe_meeting(self.library, meeting, model.run, progress, cancelled)

    def set_model(self, model):
        self.model = model
        if self.window:
            self.window.set_transcribe(self.transcriber())

    def show_window(self):
        if self.window is None:
            self.window = self.make_window(self.library, self.transcriber())
        self.window.refresh()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    # ---- startup ----------------------------------------------------------
    def recover(self):
        """Save any recording a crash or power cut left unfinished."""
        saved = repair(self.library)
        if saved:
            self.toast("Meeting recovered", f"{len(saved)} interrupted recording(s) were saved. Open Meetings to see them.")
