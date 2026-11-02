"""Top-bar icon for dictate: start/stop, change model, settings, help, about.

Needs python3-gi + AyatanaAppIndicator3 (stock on Ubuntu GNOME) and manages the dictation
process (`python -m gguf_dictate.dictate`) as a child.
"""
import fcntl
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3 as AppIndicator  # noqa: E402
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import __version__, hotkeys, ipc  # noqa: E402
from .config import DEFAULT_COLORS, MAX_COLORS, load_config, lock_path, log_path, save_config  # noqa: E402
from .overlay import Overlay  # noqa: E402
from .snip import Snip  # noqa: E402

LOG = log_path()
REPO = "https://github.com/anish-natekar/gguf-dictate"

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
  - Log: {log}
"""


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
        self.snip = Snip(lambda: self.refresh(), self.speak)
        self.build_menu()
        self.overlay = Overlay()
        self.overlay.extra = self.on_command
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

        self.snip_item = add("", self.take_snip)
        self.paste_item = add("", self.snip.paste_all)
        self.clear_item = add("Clear snip queue", self.snip.clear)
        m.append(Gtk.SeparatorMenuItem())
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
        cfg, n = load_config(), self.snip.count()
        self.snip_item.set_label(f"Take snip  [{cfg.get('snip_hotkey', 'ctrl+alt+s')}]")
        self.paste_item.set_label(f"Paste {n} queued snip(s)  [{cfg.get('paste_hotkey', 'ctrl+alt+v')}]")
        self.paste_item.set_sensitive(n > 0)
        self.clear_item.set_sensitive(n > 0)

    # ---- snip -------------------------------------------------------------
    def take_snip(self):
        GLib.timeout_add(250, lambda: self.snip.start(load_config().get("colors", DEFAULT_COLORS)) or False)   # let the menu close first

    @staticmethod
    def speak(cmd):
        """Speak button in the snip editor: tell the dictation process to start/stop recording."""
        ipc.send(cmd, ipc.CONTROL)

    def on_command(self, msg):
        if msg == "snip":
            self.snip.start(load_config().get("colors", DEFAULT_COLORS))
        elif msg == "cancel":
            if self.snip.editor:
                self.snip.editor.cancel()
        elif msg == "paste":
            self.snip.paste_all()
        elif msg == "ctrlv":
            self.snip.ctrl_v()
        elif msg.startswith("note "):
            self.snip.note(msg[5:])

    # ---- process ----------------------------------------------------------
    def start(self):
        if self.proc:
            return
        subprocess.run(["pkill", "-f", r"python[0-9.]* (-u )?-m gguf_dictate\.dictate"], check=False)  # stray copies would type everything twice
        self.log_fh = open(LOG, "w")
        self.proc = subprocess.Popen([sys.executable, "-u", "-m", "gguf_dictate.dictate"], stdout=self.log_fh, stderr=subprocess.STDOUT)
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
        elif self.state == "loading" and " ready in " in LOG.read_text(errors="replace")[:200_000]:
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
        snip_hk = Gtk.Entry(text=cfg.get("snip_hotkey", "ctrl+alt+s"))
        paste_hk = Gtk.Entry(text=cfg.get("paste_hotkey", "ctrl+alt+v"))
        colors = Gtk.Entry(text=", ".join(f"{n}={h}" for n, h in cfg.get("colors", DEFAULT_COLORS)), width_chars=48)
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
        g.attach(Gtk.Label(label="Snip hotkey", xalign=0), 0, 3, 1, 1)
        g.attach(snip_hk, 1, 3, 1, 1)
        g.attach(Gtk.Label(label="Paste-all hotkey", xalign=0), 0, 4, 1, 1)
        g.attach(paste_hk, 1, 4, 1, 1)
        g.attach(Gtk.Label(label="Snip colours", xalign=0), 0, 5, 1, 1)
        g.attach(colors, 1, 5, 2, 1)
        g.attach(Gtk.Label(label="Name=#hex, comma separated (max 9). Keys 1-9 pick them in the editor.", xalign=0), 1, 6, 2, 1)
        g.attach(lazy, 1, 7, 2, 1)
        g.attach(nospace, 1, 8, 2, 1)
        d.show_all()

        while d.run() == Gtk.ResponseType.OK:
            path, hk = model.get_text().strip(), hotkey.get_text().strip().lower().replace(" ", "")
            sk, pk = (e.get_text().strip().lower().replace(" ", "") for e in (snip_hk, paste_hk))
            try:
                cols = [[n.strip(), h.strip()] for n, h in (c.split("=") for c in colors.get_text().split(",") if c.strip())][:MAX_COLORS]
                assert cols and all(Gdk.RGBA().parse(h) for _, h in cols)
            except (ValueError, AssertionError):
                cols = None
            if not Path(path).expanduser().is_file():
                info(d, "Model file not found", f"{path or '(empty)'} is not a file.")
            elif not all(hotkeys.valid(k) for k in (hk, sk, pk)):
                info(d, "Invalid hotkey", "Use key names joined with +, e.g. f9 or ctrl+shift+space.")
            elif cols is None:
                info(d, "Invalid colours", "Use Name=#rrggbb pairs, e.g. Red=#ff3b30, Blue=#0a84ff")
            else:
                cfg.update(hotkey=hk, snip_hotkey=sk, paste_hotkey=pk, colors=cols, lazy_mic=lazy.get_active(), no_space=nospace.get_active())
                cfg["model"] = str(Path(path).expanduser())
                cfg["recent"] = [cfg["model"]] + [p for p in cfg.get("recent", []) if p != cfg["model"]][:4]
                save_config(cfg)
                self.build_menu()
                self.restart()
                break
        d.destroy()

    def show_help(self):
        info(None, "How to use Dictate", HELP.format(hotkey=load_config().get("hotkey", "f9"), log=LOG))

    def about(self):
        d = Gtk.AboutDialog(program_name="Dictate", version=__version__, website=REPO, website_label="GitHub",
                            comments="Local push-to-talk dictation using any speech-to-text GGUF model.\n"
                                     f"Model: {Path(load_config().get('model', 'none')).name}\nPowered by transcribe.cpp.",
                            license_type=Gtk.License.MIT_X11, icon_name="audio-input-microphone")
        d.run()
        d.destroy()

    def quit(self):
        self.stop()
        Gtk.main_quit()


DESKTOP = """[Desktop Entry]
Type=Application
Name=Dictate
Comment=Top-bar push-to-talk dictation and snip tool
Exec={exec}
Icon=audio-input-microphone
Terminal=false
Categories=Utility;AudioVideo;
"""


def install_desktop():
    """Write an app-menu launcher (and autostart entry with --autostart) pointing at this install."""
    exe = shutil.which("dictate-tray") or f"{sys.executable} -m gguf_dictate.tray"
    targets = [Path.home() / ".local/share/applications/dictate.desktop"]
    if "--autostart" in sys.argv:
        targets.append(Path.home() / ".config/autostart/dictate.desktop")
    for t in targets:
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text(DESKTOP.format(exec=exe))
        print("wrote", t)


def main():
    if "--install-desktop" in sys.argv:
        return install_desktop()
    lock = open(lock_path(), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit("dictate tray is already running") from None
    app = Tray()
    for sig in (signal.SIGINT, signal.SIGTERM):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, lambda: (app.quit(), False)[1])
    Gtk.main()


if __name__ == "__main__":
    main()
