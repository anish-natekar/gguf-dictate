"""System-tray icon and menu. `actions` supplies the behaviour (toggle, choose_model, set_model, ...)."""
from pathlib import Path

from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..config import load_config

ICONS = {"stopped": "microphone-disabled-symbolic", "loading": "microphone-sensitivity-low-symbolic",
         "running": "microphone-sensitivity-high-symbolic"}
LABELS = {"stopped": "Stopped", "loading": "Loading model...", "running": "Ready"}


class Tray:
    def __init__(self, actions, count):
        self.actions, self.count, self.state = actions, count, "stopped"
        self.icon = QSystemTrayIcon()
        self.icon.setToolTip("Dictate")
        self.menu = QMenu()
        self.icon.setContextMenu(self.menu)
        self.refresh()

    def add(self, label, cb=None, enabled=True, menu=None):
        a = QAction(label, self.menu)
        a.setEnabled(enabled)
        if cb:
            a.triggered.connect(lambda *_: cb())
        (menu or self.menu).addAction(a)
        return a

    def refresh(self):
        cfg = load_config()
        n = self.count()
        a = self.actions
        m = self.menu
        m.clear()
        self.add(f"{LABELS[self.state]}  -  hold [{cfg.get('hotkey', 'f9')}] to talk", enabled=False)
        self.add("Start" if self.state == "stopped" else "Stop", a.toggle)
        m.addSeparator()
        self.model_menu(cfg)
        self.add(f"Take snip  [{cfg.get('snip_hotkey', 'ctrl+alt+s')}]", a.take_snip)
        self.add(f"Paste {n} queued snip(s)  [{cfg.get('paste_hotkey', 'ctrl+alt+v')}]", a.paste_all, enabled=n > 0)
        self.add("Clear snip queue", a.clear, enabled=n > 0)
        m.addSeparator()
        self.add("Settings...", a.settings)
        m.addSeparator()
        self.add("How to use / shortcuts", a.show_help)
        self.add("About", a.about)
        m.addSeparator()
        self.add("Quit", a.quit)
        self.icon.setIcon(QIcon.fromTheme(ICONS[self.state], QIcon.fromTheme("audio-input-microphone")))

    def model_menu(self, cfg):
        model = cfg.get("model")
        sub = self.menu.addMenu(f"Model: {Path(model).name if model else 'none'}")
        self.add("Choose .gguf file...", self.actions.choose_model, menu=sub)
        recent = [p for p in cfg.get("recent", []) if Path(p).is_file()]
        if recent:
            sub.addSeparator()
        group = QActionGroup(sub)
        for p in recent:
            act = self.add(Path(p).name, menu=sub)
            act.setCheckable(True)
            act.setChecked(p == model)
            group.addAction(act)
            act.triggered.connect(lambda checked=False, p=p: self.actions.set_model(p))

    def set_state(self, state):
        self.state = state
        self.refresh()

    def show(self):
        self.icon.show()
