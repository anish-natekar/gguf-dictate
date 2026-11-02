"""Settings dialog."""
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config import DEFAULT_COLORS, load_config, save_config
from ..core.settings import SettingsError, format_colors, remember_model, validate


class SettingsDialog(QDialog):
    saved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dictate settings")
        cfg = load_config()
        self.model = QLineEdit(cfg.get("model", ""))
        self.model.setMinimumWidth(380)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.browse)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.model)
        h.addWidget(browse)
        self.hotkey = QLineEdit(cfg.get("hotkey", "f9"))
        self.snip_hotkey = QLineEdit(cfg.get("snip_hotkey", "ctrl+alt+s"))
        self.paste_hotkey = QLineEdit(cfg.get("paste_hotkey", "ctrl+alt+v"))
        self.meeting_hotkey = QLineEdit(cfg.get("meeting_hotkey", "f8"))
        self.colors = QLineEdit(format_colors(cfg.get("colors", DEFAULT_COLORS)))
        self.lazy = QCheckBox("Open the mic only while the key is held (slower start, no always-on mic)")
        self.lazy.setChecked(cfg.get("lazy_mic", False))
        self.nospace = QCheckBox("Don't add a space after each phrase")
        self.nospace.setChecked(cfg.get("no_space", False))
        form = QFormLayout()
        form.addRow("Model (.gguf)", row)
        form.addRow("Hotkey", self.hotkey)
        form.addRow("", QLabel("Hold to talk. e.g. f9, ctrl+shift+space, ctrl_r"))
        form.addRow("Snip hotkey", self.snip_hotkey)
        form.addRow("Paste-all hotkey", self.paste_hotkey)
        form.addRow("Meeting record hotkey", self.meeting_hotkey)
        form.addRow("Snip colours", self.colors)
        form.addRow("", QLabel("Name=#hex, comma separated (max 9). Keys 1-9 pick them in the editor."))
        form.addRow("", self.lazy)
        form.addRow("", self.nospace)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText("Save and restart")
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.buttons)

    def browse(self):
        start = str(Path(self.model.text()).parent) if self.model.text() else ""
        path, _ = QFileDialog.getOpenFileName(self, "Choose a speech-to-text model", start, "GGUF models (*.gguf *.bin)")
        if path:
            self.model.setText(path)

    def save(self):
        try:
            out = validate({"model": self.model.text(), "hotkey": self.hotkey.text(), "snip_hotkey": self.snip_hotkey.text(),
                            "paste_hotkey": self.paste_hotkey.text(), "meeting_hotkey": self.meeting_hotkey.text(), "colors": self.colors.text(),
                            "lazy_mic": self.lazy.isChecked(), "no_space": self.nospace.isChecked()})
        except SettingsError as e:
            QMessageBox.warning(self, e.title, e.text)
            return
        cfg = load_config()
        cfg.update(out)
        remember_model(cfg, out["model"])
        save_config(cfg)
        self.saved.emit()
        self.accept()
