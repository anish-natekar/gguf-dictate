"""Help and About boxes."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from .. import __version__

REPO = "https://github.com/anish-natekar/gguf-dictate"

HELP = """Hold the hotkey, talk, release. The text is typed into the focused window.

Hotkey: {hotkey}   (change it in Settings)

Examples for the hotkey box:
  f9            ctrl+shift+space      ctrl_r (right Ctrl only)
Use "ctrl" for either Ctrl key, "ctrl_r" / "ctrl_l" for one side.
Avoid ctrl+alt+space: Claude desktop uses it.

Meetings: the meeting hotkey (Settings, default F8) shows a small recorder; press its red button to record.
Tray > Meetings... lists recordings and makes transcripts.

Tips
  - Wait for "Ready" in this menu before talking.
  - The first words are kept even if you start talking a bit early.
  - Quiet mic? Raise input volume in system Sound settings.
  - Log: {log}
"""


def show_help(hotkey, log):
    QMessageBox.information(None, "How to use Dictate", HELP.format(hotkey=hotkey, log=log))


def show_about(model):
    QMessageBox.about(None, "About Dictate", f"<b>Dictate {__version__}</b><br>Local push-to-talk dictation using any speech-to-text GGUF model.<br>"
                                             f"Model: {Path(model or 'none').name}<br>Powered by transcribe.cpp.<br><a href='{REPO}'>GitHub</a>")


def show_error(title, text):
    QMessageBox.warning(None, title, text)


def confirm_discard():
    box = QMessageBox(QMessageBox.Question, "Discard recording", "Discard this meeting recording? The audio will be deleted.",
                      QMessageBox.Yes | QMessageBox.No)
    box.setDefaultButton(QMessageBox.No)
    box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    return box.exec() == QMessageBox.Yes
