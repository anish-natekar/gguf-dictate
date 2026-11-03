#!/usr/bin/env python3
"""Single-process app: Qt tray + overlay + snip editor, with dictation running on worker threads.

    dictate-tray            # tray icon; pick a model in Settings the first time
    dictate-tray --model /path/to/model.gguf
"""
import argparse
import shutil
import signal
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication, QFileDialog

from .config import DEFAULT_COLORS, load_config, lock_path, log_path, meetings_dir, save_config
from .core.dictation import Dictation
from .core.lock import SingleInstance
from .core.recorder import Recorder
from .core.settings import remember_model

SNIP_DELAY_MS = 250      # let the tray menu close before the screen is frozen


class App(QObject):
    """Owns the dictation lifecycle (load model -> record/transcribe -> stop) and routes overlay commands to the snip controller."""

    loaded = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self, load_model, source, keys, snip, overlay, tray, start_listener, show_error, open_settings, quit_app, log=print,
                 show_help=lambda hotkey: None, show_about=lambda model: None, meetings=None):
        super().__init__()
        self.load_model, self.source, self.keys, self.snip, self.overlay, self.tray = load_model, source, keys, snip, overlay, tray
        self.start_listener, self.show_error, self.open_settings, self.quit_app, self.log = start_listener, show_error, open_settings, quit_app, log
        self.help_cb, self.about_cb, self.meetings = show_help, show_about, meetings
        self.state, self.gen, self.dictation, self.mic, self.listener = "stopped", 0, None, None, None
        self.loaded.connect(self.on_loaded)
        self.failed.connect(self.on_failed)

    def set_state(self, state):
        self.state = state
        self.tray.set_state(state)

    # ---- lifecycle --------------------------------------------------------
    def start(self):
        if self.state != "stopped":
            return
        path = load_config().get("model")
        if not path or not Path(path).expanduser().is_file():
            self.open_settings()
            return
        self.gen += 1
        gen = self.gen
        self.set_state("loading")

        def work():
            try:
                self.loaded.emit(gen, self.load_model(path))
            except Exception as e:      # noqa: BLE001 - any loader failure goes to the user
                self.failed.emit(gen, str(e))
        threading.Thread(target=work, daemon=True).start()

    def on_loaded(self, gen, model):
        if gen != self.gen:      # stopped or restarted while loading
            return
        cfg = load_config()
        hotkey = cfg.get("hotkey", "f9")
        try:
            self.mic = Recorder(self.source(), on_level=lambda lvl: self.overlay.post(f"lvl {lvl:.5f}"), lazy=cfg.get("lazy_mic", False))
            self.dictation = Dictation(model, self.mic, self.keys, self.overlay.post, self.snip.editor_open, hotkey,
                                       cfg.get("snip_hotkey", "ctrl+alt+s"), cfg.get("paste_hotkey", "ctrl+alt+v"),
                                       no_space=cfg.get("no_space", False), meeting=cfg.get("meeting_hotkey", "f8") if self.meetings else None,
                                       log=self.log)
            self.listener = self.start_listener(self.dictation.router)
            if self.meetings:
                self.meetings.set_model(model)
        except Exception as e:      # noqa: BLE001 - e.g. no microphone / missing libportaudio2
            self.stop()
            self.show_error("Dictate could not start", str(e))
            return
        self.log(f"hold [{hotkey}] to talk")
        self.set_state("running")

    def on_failed(self, gen, message):
        if gen != self.gen:
            return
        self.set_state("stopped")
        self.show_error("Dictate could not load the model", message)

    def stop(self):
        self.gen += 1
        if self.listener:
            self.listener.stop()
        if self.mic:
            self.mic.close()
        self.listener = self.mic = self.dictation = None
        if self.meetings:
            self.meetings.set_model(None)
        self.set_state("stopped")

    def restart(self):
        self.stop()
        self.start()

    def toggle(self):
        self.stop() if self.state != "stopped" else self.start()

    def quit(self):
        if self.meetings:
            self.meetings.shutdown()
        self.stop()
        self.quit_app()

    # ---- commands ---------------------------------------------------------
    def speak(self, cmd):
        """Speak button in the snip editor."""
        if self.dictation:
            self.dictation.state.begin("button") if cmd == "start" else self.dictation.state.end()

    def on_command(self, msg):
        if msg == "snip":
            self.snip.start(load_config().get("colors", DEFAULT_COLORS))
        elif msg == "cancel":
            self.snip.cancel()
        elif msg == "paste":
            self.snip.paste_all()
        elif msg == "meeting":
            self.toggle_meeting()
        elif msg == "ctrlv":
            self.snip.ctrl_v()
        elif msg.startswith("note "):
            self.snip.note(msg[5:])

    # ---- tray actions -----------------------------------------------------
    def take_snip(self):
        QTimer.singleShot(SNIP_DELAY_MS, lambda: self.on_command("snip"))

    def paste_all(self):
        self.snip.paste_all()

    def clear(self):
        self.snip.clear()

    def toggle_meeting(self):
        if self.meetings:
            self.meetings.toggle()

    def show_meetings(self):
        if self.meetings:
            self.meetings.show_window()

    def settings(self):
        self.open_settings()

    def set_model(self, path):
        save_config(remember_model(load_config(), path))
        self.restart()

    def choose_model(self):
        cur = load_config().get("model")
        path, _ = QFileDialog.getOpenFileName(None, "Choose a speech-to-text model", str(Path(cur).parent) if cur else "", "GGUF models (*.gguf *.bin)")
        if path:
            self.set_model(path)

    def show_help(self):
        self.help_cb(load_config().get("hotkey", "f9"))

    def about(self):
        self.about_cb(load_config().get("model"))


DESKTOP = """[Desktop Entry]
Type=Application
Name=Dictate
Comment=Top-bar push-to-talk dictation and snip tool
Exec={exec}
Icon=audio-input-microphone
Terminal=false
Categories=Utility;AudioVideo;
"""


def install_desktop(autostart):
    """Write an app-menu launcher (and autostart entry with --autostart) pointing at this install."""
    exe = shutil.which("dictate-tray") or f"{sys.executable} -m gguf_dictate.app"
    targets = [Path.home() / ".local/share/applications/dictate.desktop"]
    if autostart:
        targets.append(Path.home() / ".config/autostart/dictate.desktop")
    for t in targets:
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text(DESKTOP.format(exec=exe))
        print("wrote", t)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", help="path to a .gguf model (remembered)")
    ap.add_argument("--install-desktop", action="store_true", help="write an app-menu launcher and exit")
    ap.add_argument("--autostart", action="store_true", help="with --install-desktop: also start at login")
    args = ap.parse_args()
    if args.install_desktop:
        return install_desktop(args.autostart)
    lock = SingleInstance(lock_path())
    if not lock.acquire():
        raise SystemExit("dictate is already running")
    if not sys.stdout.isatty():
        sys.stdout = sys.stderr = open(log_path(), "w", buffering=1)
    if args.model:
        save_config(remember_model(load_config(), str(Path(args.model).expanduser().resolve())))

    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    from .core.meeting_recorder import MeetingRecorder
    from .core.meetings import Library
    from .model import load_session
    from .platform import default_keys, default_notifier, default_system_source, session_warning
    from .platform.audio import SoundDeviceSource
    from .platform.keys import start_listener
    from .ui import dialogs
    from .ui.meeting import MeetingController
    from .ui.meeting_pill import MeetingPill
    from .ui.meetings import MeetingsWindow
    from .ui.overlay import Overlay
    from .ui.settings import SettingsDialog
    from .ui.snip import SnipController
    from .ui.tray import Tray

    tray = Tray(None, lambda: snip.count(), lambda: meetings.recording)
    keys = default_keys()
    snip = SnipController(on_change=lambda: tray.refresh(), speak=lambda cmd: app.speak(cmd), keys=keys, notifier=default_notifier(icon=tray.icon))
    overlay = Overlay()
    notifier = default_notifier(icon=tray.icon)
    meetings = MeetingController(
        Library(meetings_dir()),
        make_recorder=lambda lib: MeetingRecorder(lib, SoundDeviceSource(), default_system_source()),
        make_pill=lambda pos: MeetingPill(pos),
        make_window=lambda lib, transcribe: MeetingsWindow(lib, transcribe),
        toast=notifier.toast, show_error=dialogs.show_error, confirm_discard=dialogs.confirm_discard)
    dialog = {}

    def open_settings():
        d = dialog["d"] = SettingsDialog()
        d.saved.connect(app.restart)
        d.show()
        d.raise_()
        d.activateWindow()

    app = App(load_session, SoundDeviceSource, keys, snip, overlay, tray, start_listener, dialogs.show_error, open_settings, qapp.quit,
              log=lambda m: print(m, flush=True), show_help=lambda hk: dialogs.show_help(hk, log_path()), show_about=dialogs.show_about,
              meetings=meetings)
    tray.actions = app
    meetings.changed.connect(tray.refresh)
    tray.refresh()
    overlay.extra = app.on_command
    overlay.show()
    tray.show()
    warning = session_warning()
    if warning:
        print(warning, flush=True)
        QTimer.singleShot(1500, lambda: notifier.toast("Dictate hotkeys won't work", warning))
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: app.quit())
    ticker = QTimer()      # lets Python signal handlers run while Qt is idle
    ticker.start(500)
    ticker.timeout.connect(lambda: None)
    QTimer.singleShot(0, app.start)
    QTimer.singleShot(0, meetings.recover)
    code = qapp.exec()
    lock.release()
    sys.exit(code)


if __name__ == "__main__":
    main()
