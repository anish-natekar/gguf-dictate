"""Linux/X11 implementations of the interfaces core.pasting and core.dictation need (xdotool, notify-send)."""
import subprocess


class XdotoolKeys:
    def paste(self):
        subprocess.Popen(["xdotool", "key", "--clearmodifiers", "ctrl+v"])

    def type_text(self, text):
        subprocess.run(["xdotool", "type", "--clearmodifiers", "--delay", "1", "--", text], check=False)


class NotifySend:
    def toast(self, title, body):
        subprocess.Popen(["notify-send", "-i", "camera-photo", "-t", "3500", title, body])
