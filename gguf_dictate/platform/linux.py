"""Linux/X11 implementations of the interfaces core.pasting needs (GTK clipboard, xdotool, notify-send, GLib timers)."""
import subprocess

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402


class GtkClipboard:
    def __init__(self):
        self.cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)

    def on_change_listener(self, callback):
        self.cb.connect("owner-change", lambda *_: callback())

    def load_image(self, path):
        return GdkPixbuf.Pixbuf.new_from_file(str(path))    # decoded now: paste-all deletes the file afterwards

    def set_image(self, pixbuf):
        self.cb.set_image(pixbuf)

    def set_text(self, text):
        self.cb.set_text(text, -1)


class XdotoolKeys:
    def paste(self):
        subprocess.Popen(["xdotool", "key", "--clearmodifiers", "ctrl+v"])

    def type_text(self, text):
        subprocess.run(["xdotool", "type", "--clearmodifiers", "--delay", "1", "--", text], check=False)


class NotifySend:
    def toast(self, title, body):
        subprocess.Popen(["notify-send", "-i", "camera-photo", "-t", "3500", title, body])


class GlibClock:
    def after(self, ms, fn, *args):
        GLib.timeout_add(ms, lambda: fn(*args) and False)    # returning a falsy value stops the timer
