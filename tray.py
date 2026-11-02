#!/usr/bin/python3
"""Top-bar icon for dictate: start/stop, change model, settings, help, about.

Runs on the system Python (needs python3-gi + AyatanaAppIndicator3, both stock
on Ubuntu GNOME) and manages dictate.py as a child process in the venv.
"""
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3 as AppIndicator  # noqa: E402
from gi.repository import GLib, Gtk  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PY, SCRIPT = HERE / ".venv" / "bin" / "python", HERE / "dictate.py"
CONFIG = Path.home() / ".config" / "dictate" / "config.json"
LOG = Path("/tmp/dictate.log")
from overlay import Overlay  # noqa: E402

REPO = "https://github.com/anish-natekar/gguf-dictate"
HOTKEY_RE = re.compile(r"^[a-z0-9_]+(\+[a-z0-9_]+)*$")

ICONS = {"stopped": "microphone-disabled-symbolic", "loading": "microphone-sensitivity-low-symbolic",
         "running": "microphone-sensitivity-high-symbolic"}
LABELS = {"stopped": "Stopped", "loading": "Loading model...", "running": "Ready"}

HELP = """Hold the hotkey, talk, release. The text is typed into the focused window.

Hotkey: {hotkey}   (change it in Settings)

Examples for the hotkey box:
  f9            ctrl+shift+space      ctrl_r (right Ctrl only)
Use "ctrl" for either Ctrl key, "ctrl_r" / "ctrl_l" for one side.
Avoid ctrl+alt+space: Claude desktop uses it.

Tips
  - Wait for "Ready" in this menu before talking.
  - The first words are kept even if you start talking a bit early.
  - Quiet mic? Raise input volume in system Sound settings.
  - Log: /tmp/dictate.log
"""


def load_config():
    try:
        return json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2))


def info(parent, title, text):
    d = Gtk.MessageDialog(parent=parent, message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.CLOSE, text=title)
    d.format_secondary_text(text)
    d.run()
    d.destroy()


class Tray:
    def __init__(self):
        self.proc, self.state, self.log_fh = None, "stopped", None
        self.ind = AppIndicator.Indicator.new("dictate", ICONS["stopped"], AppIndicator.IndicatorCategory.APPLICATION_STATUS)
        self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.ind.set_title("Dictate")
        self.build_menu()
        self.overlay = Overlay()
        GLib.timeout_add(500, self.poll)
        if load_config().get("model"):
            self.start()
        else:
            GLib.idle_add(self.settings)

    # ---- menu -------------------------------------------------------------
    def build_menu(self):
        cfg = load_config()
        m = Gtk.Menu()

        def add(label, cb=None, sensitive=True, parent=None):
            item = Gtk.MenuItem(label=label)
            item.set_sensitive(sensitive)
            if cb:
                item.connect("activate", lambda *_: cb())
            (parent or m).append(item)
            return item

        self.status_item = add("", sensitive=False)
        self.toggle_item = add("", self.toggle)
        m.append(Gtk.SeparatorMenuItem())

        model = cfg.get("model")
        sub = Gtk.Menu()
        add("Choose .gguf file...", self.choose_model, parent=sub)
        recent = [p for p in cfg.get("recent", []) if Path(p).is_file()]
        if recent:
            sub.append(Gtk.SeparatorMenuItem())
        for p in recent:
            item = Gtk.CheckMenuItem(label=Path(p).name)
            item.set_active(p == model)
            item.connect("activate", lambda w, p=p: self.set_model(p) if w.get_active() else None)
            sub.append(item)
        model_item = Gtk.MenuItem(label=f"Model: {Path(model).name if model else 'none'}")
        model_item.set_submenu(sub)
        m.append(model_item)

        add("Settings...", self.settings)
        m.append(Gtk.SeparatorMenuItem())
        add("How to use / shortcuts", self.show_help)
        add("About", self.about)
        m.append(Gtk.SeparatorMenuItem())
        add("Quit", self.quit)
        m.show_all()
        self.ind.set_menu(m)
        self.menu = m
        self.refresh()

    def refresh(self):
        hotkey = load_config().get("hotkey", "f9")
        self.status_item.set_label(f"{LABELS[self.state]}  -  hold [{hotkey}] to talk")
        self.toggle_item.set_label("Start" if self.state == "stopped" else "Stop")
        self.ind.set_icon_full(ICONS[self.state], LABELS[self.state])

    # ---- process ----------------------------------------------------------
    def start(self):
        if self.proc:
            return
        subprocess.run(["pkill", "-f", r"python[0-9.]* .*dictate\.py"], check=False)  # stray copies would type everything twice
        self.log_fh = open(LOG, "w")
        self.proc = subprocess.Popen([str(PY), "-u", str(SCRIPT)], stdout=self.log_fh, stderr=subprocess.STDOUT)
        self.state = "loading"
        self.refresh()

    def stop(self):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None
            self.log_fh.close()
        self.state = "stopped"
        self.refresh()

    def restart(self):
        self.stop()
        self.start()

    def toggle(self):
        self.stop() if self.state != "stopped" else self.start()

    def poll(self):
        if self.proc and self.proc.poll() is not None:
            self.proc, self.state = None, "stopped"
            self.refresh()
            tail = LOG.read_text(errors="replace").strip().splitlines()[-1:] or [""]
            info(None, "Dictate stopped unexpectedly", f"{tail[0][:200]}\n\nSee {LOG} for details.")
        elif self.state == "loading" and " ready in " in LOG.read_text(errors="replace"):
            self.state = "running"
            self.refresh()
        return True

    # ---- config actions ---------------------------------------------------
    def set_model(self, path):
        cfg = load_config()
        cfg["model"] = path
        cfg["recent"] = [path] + [p for p in cfg.get("recent", []) if p != path][:4]
        save_config(cfg)
        self.build_menu()
        self.restart()

    def pick_file(self, parent=None):
        d = Gtk.FileChooserDialog(title="Choose a speech-to-text model", parent=parent, action=Gtk.FileChooserAction.OPEN)
        d.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Open", Gtk.ResponseType.OK)
        f = Gtk.FileFilter()
        f.set_name("GGUF models")
        f.add_pattern("*.gguf")
        f.add_pattern("*.bin")
        d.add_filter(f)
        cur = load_config().get("model")
        if cur:
            d.set_current_folder(str(Path(cur).parent))
        path = d.get_filename() if d.run() == Gtk.ResponseType.OK else None
        d.destroy()
        return path

    def choose_model(self):
        path = self.pick_file()
        if path:
            self.set_model(path)

    def settings(self):
        cfg = load_config()
        d = Gtk.Dialog(title="Dictate settings", flags=Gtk.DialogFlags.MODAL)
        d.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Save and restart", Gtk.ResponseType.OK)
        g = Gtk.Grid(column_spacing=8, row_spacing=8, margin=14)
        d.get_content_area().add(g)

        model = Gtk.Entry(text=cfg.get("model", ""), width_chars=48)
        browse = Gtk.Button(label="Browse...")
        browse.connect("clicked", lambda *_: model.set_text(self.pick_file(d) or model.get_text()))
        hotkey = Gtk.Entry(text=cfg.get("hotkey", "f9"))
        hint = Gtk.Label(label="Hold to talk. e.g. f9, ctrl+shift+space, ctrl_r", xalign=0)
        lazy = Gtk.CheckButton(label="Open the mic only while the key is held (slower start, no always-on mic)")
        lazy.set_active(cfg.get("lazy_mic", False))
        nospace = Gtk.CheckButton(label="Don't add a space after each phrase")
        nospace.set_active(cfg.get("no_space", False))

        g.attach(Gtk.Label(label="Model (.gguf)", xalign=0), 0, 0, 1, 1)
        g.attach(model, 1, 0, 1, 1)
        g.attach(browse, 2, 0, 1, 1)
        g.attach(Gtk.Label(label="Hotkey", xalign=0), 0, 1, 1, 1)
        g.attach(hotkey, 1, 1, 1, 1)
        g.attach(hint, 1, 2, 2, 1)
        g.attach(lazy, 1, 3, 2, 1)
        g.attach(nospace, 1, 4, 2, 1)
        d.show_all()

        while d.run() == Gtk.ResponseType.OK:
            path, hk = model.get_text().strip(), hotkey.get_text().strip().lower().replace(" ", "")
            if not Path(path).expanduser().is_file():
                info(d, "Model file not found", f"{path or '(empty)'} is not a file.")
            elif not HOTKEY_RE.match(hk):
                info(d, "Invalid hotkey", "Use key names joined with +, e.g. f9 or ctrl+shift+space.")
            else:
                cfg.update(hotkey=hk, lazy_mic=lazy.get_active(), no_space=nospace.get_active())
                cfg["model"] = str(Path(path).expanduser())
                cfg["recent"] = [cfg["model"]] + [p for p in cfg.get("recent", []) if p != cfg["model"]][:4]
                save_config(cfg)
                self.build_menu()
                self.restart()
                break
        d.destroy()

    def show_help(self):
        info(None, "How to use Dictate", HELP.format(hotkey=load_config().get("hotkey", "f9")))

    def about(self):
        d = Gtk.AboutDialog(program_name="Dictate", version="0.1", website=REPO, website_label="GitHub",
                            comments="Local push-to-talk dictation using any speech-to-text GGUF model.\n"
                                     f"Model: {Path(load_config().get('model', 'none')).name}\nPowered by transcribe.cpp.",
                            license_type=Gtk.License.MIT_X11, icon_name="audio-input-microphone")
        d.run()
        d.destroy()

    def quit(self):
        self.stop()
        Gtk.main_quit()


def main():
    lock = open("/tmp/dictate-tray.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit("dictate tray is already running")
    app = Tray()
    for sig in (signal.SIGINT, signal.SIGTERM):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, lambda: (app.quit(), False)[1])
    Gtk.main()


if __name__ == "__main__":
    main()
