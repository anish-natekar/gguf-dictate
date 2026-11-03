"""OS-specific adapters. `default_keys` / `default_notifier` pick the right ones for the running OS."""
import sys

from .linux import NotifySend, PipeWireMonitorSource, XdotoolKeys

__all__ = ["PynputKeys", "QtNotifier", "UnsupportedSystemAudio", "default_keys", "default_notifier", "default_system_source", "session_warning"]


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


class UnsupportedSystemAudio:
    """Stands in where call/system audio cannot be captured yet: meetings then record the mic alone."""

    def open(self, callback):
        raise RuntimeError("system audio capture is not supported on this platform yet")

    def close(self):
        pass


def default_system_source(platform=None):
    return PipeWireMonitorSource() if (platform or sys.platform).startswith("linux") else UnsupportedSystemAudio()


def default_keys(platform=None):
    return XdotoolKeys() if (platform or sys.platform).startswith("linux") else PynputKeys()


def default_notifier(platform=None, icon=None):
    return NotifySend() if (platform or sys.platform).startswith("linux") else QtNotifier(icon)


def session_warning(platform=None, env=None):
    """Why global hotkeys cannot work in this session, or None. Wayland blocks the global key listener and xdotool."""
    import os
    if not (platform or sys.platform).startswith("linux"):
        return None
    env = os.environ if env is None else env
    if env.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        return "Wayland session: hotkeys and pasting need X11. Log out and pick 'Ubuntu on Xorg'."
    return None
