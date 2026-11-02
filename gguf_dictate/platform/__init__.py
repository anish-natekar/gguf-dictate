"""OS-specific adapters. `default_keys` / `default_notifier` pick the right ones for the running OS."""
import sys

from .linux import NotifySend, XdotoolKeys

__all__ = ["PynputKeys", "QtNotifier", "default_keys", "default_notifier"]


class PynputKeys:
    """Typing and Ctrl+V through pynput (Windows, macOS). Linux uses xdotool, which is more reliable on X11."""

    def __init__(self, controller=None, modifier=None):
        if controller is None:
            from pynput import keyboard
            controller = keyboard.Controller()
            modifier = keyboard.Key.cmd if sys.platform == "darwin" else keyboard.Key.ctrl
        self.controller, self.modifier = controller, modifier

    def paste(self):
        with self.controller.pressed(self.modifier):
            self.controller.press("v")
            self.controller.release("v")

    def type_text(self, text):
        self.controller.type(text)


class QtNotifier:
    """Toast through the tray icon's balloon message."""

    def __init__(self, icon):
        self.icon = icon

    def toast(self, title, body):
        self.icon.showMessage(title, body)


def default_keys(platform=None):
    return XdotoolKeys() if (platform or sys.platform).startswith("linux") else PynputKeys()


def default_notifier(platform=None, icon=None):
    return NotifySend() if (platform or sys.platform).startswith("linux") else QtNotifier(icon)
