"""Qt tray menu and settings dialog, headless."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QDialogButtonBox, QMessageBox  # noqa: E402

from gguf_dictate import config  # noqa: E402
from gguf_dictate.ui.settings import SettingsDialog  # noqa: E402
from gguf_dictate.ui.tray import Tray  # noqa: E402


class Calls:
    def __init__(self):
        self.log = []

    def __getattr__(self, name):
        return lambda *a: self.log.append((name, *a))


@pytest.fixture
def cfgdir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "config_file", lambda: tmp_path / "config.json")
    return tmp_path


@pytest.fixture
def tray(qtbot, cfgdir):
    c = Calls()
    t = Tray(c, count=lambda: 0)
    t.c = c
    return t


def labels(t):
    return [a.text() for a in t.menu.actions() if not a.isSeparator()]


def action(t, prefix):
    return next(a for a in t.menu.actions() if a.text().startswith(prefix))


def test_menu_has_all_entries(tray):
    ls = labels(tray)
    for want in ["Stopped", "Start", "Model:", "Take snip", "Paste 0 queued", "Clear snip queue", "Settings", "How to use", "About", "Quit"]:
        assert any(x.startswith(want) for x in ls), want


def test_state_changes_status_and_toggle_labels(tray):
    tray.set_state("loading")
    assert "Loading model" in labels(tray)[0] and action(tray, "Stop")
    tray.set_state("running")
    assert labels(tray)[0].startswith("Ready") and "hold [f9]" in labels(tray)[0]


def test_hotkeys_shown_come_from_config(tray, cfgdir):
    config.save_config({"snip_hotkey": "ctrl+shift+x", "paste_hotkey": "ctrl+shift+y"}, cfgdir / "config.json")
    tray.refresh()
    assert "[ctrl+shift+x]" in action(tray, "Take snip").text() and "[ctrl+shift+y]" in action(tray, "Paste").text()


def test_paste_and_clear_disabled_until_queue_has_items(qtbot, cfgdir):
    n = [0]
    t = Tray(Calls(), count=lambda: n[0])
    assert not action(t, "Paste").isEnabled() and not action(t, "Clear").isEnabled()
    n[0] = 2
    t.refresh()
    assert action(t, "Paste 2 queued").isEnabled() and action(t, "Clear").isEnabled()


def test_actions_call_through(tray):
    action(tray, "Start").trigger()
    action(tray, "Clear").trigger() if action(tray, "Clear").isEnabled() else None
    action(tray, "Quit").trigger()
    names = [x[0] for x in tray.c.log]
    assert "toggle" in names and "quit" in names


def test_recent_models_listed_and_selectable(tray, cfgdir):
    m = cfgdir / "a.gguf"
    m.write_bytes(b"x")
    config.save_config({"model": str(m), "recent": [str(m), str(cfgdir / "gone.gguf")]}, cfgdir / "config.json")
    tray.refresh()
    sub = action(tray, "Model: a.gguf").menu()
    recents = [a for a in sub.actions() if a.isCheckable()]
    assert [a.text() for a in recents] == ["a.gguf"] and recents[0].isChecked()


# ---- settings dialog -----------------------------------------------------
@pytest.fixture
def dlg(qtbot, cfgdir):
    m = cfgdir / "m.gguf"
    m.write_bytes(b"x")
    config.save_config({"model": str(m)}, cfgdir / "config.json")
    d = SettingsDialog()
    qtbot.addWidget(d)
    d.m = m
    return d


def test_dialog_prefills_from_config_and_defaults(dlg):
    assert dlg.hotkey.text() == "f9" and dlg.snip_hotkey.text() == "ctrl+alt+s" and dlg.paste_hotkey.text() == "ctrl+alt+v"
    assert dlg.model.text() == str(dlg.m) and "Red=" in dlg.colors.text()


def test_dialog_save_persists_and_emits(dlg, qtbot):
    dlg.hotkey.setText("Ctrl_R")
    with qtbot.waitSignal(dlg.saved, timeout=1000):
        dlg.buttons.button(QDialogButtonBox.Save).click()
    cfg = config.load_config()
    assert cfg["hotkey"] == "ctrl_r" and cfg["model"] == str(dlg.m) and cfg["recent"][0] == str(dlg.m)


def test_dialog_rejects_bad_hotkey_without_saving(dlg, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: shown.append(a[1:3]))
    dlg.hotkey.setText("ctrl+")
    dlg.buttons.button(QDialogButtonBox.Save).click()
    assert shown and shown[0][0] == "Invalid hotkey"
    assert config.load_config().get("hotkey") is None


def test_dialog_rejects_missing_model(dlg, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: shown.append(a[1]))
    dlg.model.setText("/nonexistent.gguf")
    dlg.buttons.button(QDialogButtonBox.Save).click()
    assert shown == ["Model file not found"]
