"""OS-specific adapters. `default_keys` / `default_notifier` pick the right ones for the running OS."""
import sys

from .linux import NotifySend, PipeWireMonitorSource, XdotoolKeys

__all__ = ["PynputKeys", "QtNotifier", "UnsupportedSystemAudio", "default_keys", "default_listener", "default_notifier",
           "default_system_source", "is_wayland", "prefer_xwayland"]


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


def is_wayland(platform=None, env=None):
    import os
    env = os.environ if env is None else env
    return (platform or sys.platform).startswith("linux") and env.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def default_keys(platform=None, wayland=None):
    if not (platform or sys.platform).startswith("linux"):
        return PynputKeys()
    from .wayland import MutterKeys
    return MutterKeys() if (is_wayland(platform) if wayland is None else wayland) else XdotoolKeys()


def default_listener(platform=None, wayland=None):
    """start_listener(router) for this session: pynput on X11, Windows and macOS; evdev on Wayland."""
    if is_wayland(platform) if wayland is None else wayland:
        from .wayland import EvdevListener

        def start(router):
            listener = EvdevListener(router)
            listener.start()
            return listener
        return start
    from .keys import start_listener
    return start_listener


def default_notifier(platform=None, icon=None):
    return NotifySend() if (platform or sys.platform).startswith("linux") else QtNotifier(icon)



def prefer_xwayland(env=None):
    """On Wayland run Qt through XWayland: only there can the overlay and meeting pill place themselves and stay on top."""
    import os
    env = os.environ if env is None else env
    if is_wayland(env=env) and "QT_QPA_PLATFORM" not in env:
        env["QT_QPA_PLATFORM"] = "xcb"
