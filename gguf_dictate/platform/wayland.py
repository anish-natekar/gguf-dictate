"""Wayland (GNOME) adapters: keys come from evdev, keystrokes go out through mutter's RemoteDesktop D-Bus API."""
import select
import subprocess
import threading
import time

BUS = "org.gnome.Mutter.RemoteDesktop"
ROOT = "/org/gnome/Mutter/RemoteDesktop"
SESSION = "org.gnome.Mutter.RemoteDesktop.Session"
KEY_LEFTCTRL, KEY_V = 29, 47      # evdev keycodes, which is what NotifyKeyboardKeycode takes
PASTE_SETTLE_S = 0.12
KEYS_SETTLE_S = 0.05

NAMES = {"LEFTCTRL": "ctrl_l", "RIGHTCTRL": "ctrl_r", "LEFTALT": "alt_l", "RIGHTALT": "alt_gr", "LEFTSHIFT": "shift_l",
         "RIGHTSHIFT": "shift_r", "LEFTMETA": "cmd_l", "RIGHTMETA": "cmd_r", "ESC": "esc"}


def key_name(code, names):
    """pynput-style name for an evdev keycode ('f9', 'ctrl_l', 's'), or None for codes that are not keys."""
    raw = names.get(code)
    if isinstance(raw, (list, tuple)):
        raw = raw[0]
    if not raw or not raw.startswith("KEY_"):
        return None
    raw = raw[4:]
    return NAMES.get(raw, raw.lower())


def find_keyboards():
    """Readable evdev devices that look like keyboards; raises RuntimeError with the fix when none can be read."""
    import evdev
    found, denied = [], False
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except PermissionError:
            denied = True
            continue
        except OSError:
            continue
        if evdev.ecodes.KEY_A in dev.capabilities().get(evdev.ecodes.EV_KEY, []):
            found.append(dev)
        else:
            dev.close()
    if not found:
        raise RuntimeError("cannot read the keyboard on Wayland: add yourself to the 'input' group "
                           "(sudo usermod -aG input $USER) and log in again" if denied else "no keyboard found")
    return found


class EvdevListener:
    """Feeds HotkeyRouter from /dev/input, so it sees keys whichever window has focus (Wayland hides them from apps)."""

    def __init__(self, router, devices=None, names=None, wait=select.select):
        if names is None:
            from evdev import ecodes
            names = ecodes.bytype[ecodes.EV_KEY]
        self.router, self.names, self.wait = router, names, wait
        self.devices = devices if devices is not None else find_keyboards()
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()

    def run(self):
        by_fd = {d.fileno(): d for d in self.devices}
        while not self.stopping.is_set():
            ready, _, _ = self.wait(list(by_fd), [], [], 0.2)
            for fd in ready:
                try:
                    for event in by_fd[fd].read():
                        self.handle(event)
                except OSError:      # unplugged
                    by_fd.pop(fd, None)
            if not by_fd:
                return

    def handle(self, event):
        if event.type != 1 or event.value == 2:      # EV_KEY only; auto-repeat is ignored
            return
        name = key_name(event.code, self.names)
        if name:
            (self.router.press if event.value else self.router.release)(name)

    def stop(self):
        self.stopping.set()
        self.thread.join(1)
        for d in self.devices:
            try:
                d.close()
            except OSError:
                pass


class MutterKeys:
    """Types by putting text on the clipboard (wl-copy) and sending Ctrl+V; needs no extra permission on GNOME.

    A RemoteDesktop session is opened per paste: mutter drops idle ones, and a short-lived one leaves no remote-control indicator behind.
    """

    def __init__(self, call=None, run=subprocess.run, sleep=time.sleep):
        self.call, self.run, self.sleep = call or dbus_call, run, sleep
        self.lock = threading.Lock()

    def paste(self):
        with self.lock:
            session = self.call(BUS, ROOT, "org.gnome.Mutter.RemoteDesktop", "CreateSession")
            try:
                self.call(BUS, session, SESSION, "Start")
                for code, down in ((KEY_LEFTCTRL, True), (KEY_V, True), (KEY_V, False), (KEY_LEFTCTRL, False)):
                    self.call(BUS, session, SESSION, "NotifyKeyboardKeycode", "ub", (code, down))
                self.sleep(KEYS_SETTLE_S)
            finally:
                try:
                    self.call(BUS, session, SESSION, "Stop")
                except RuntimeError:      # already gone
                    pass

    def type_text(self, text):
        self.run(["wl-copy", "--", text], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.sleep(PASTE_SETTLE_S)
        self.paste()


def dbus_call(service, path, interface, method, signature="", args=()):
    """One blocking session-bus call (jeepney, so argument types such as uint32 can be spelled out); returns the first reply value."""
    from jeepney import DBusAddress, new_method_call
    from jeepney.io.blocking import open_dbus_connection
    conn = dbus_call.conn = getattr(dbus_call, "conn", None) or open_dbus_connection(bus="SESSION")
    reply = conn.send_and_get_reply(new_method_call(DBusAddress(path, service, interface), method, signature, tuple(args)), timeout=3)
    if reply.header.message_type.name == "error":
        raise RuntimeError(f"{method}: {reply.body[0] if reply.body else reply.header.fields}")
    return reply.body[0] if reply.body else None
