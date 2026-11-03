"""Screen capture through the xdg-desktop-portal Screenshot API: the only way to grab the screen on GNOME Wayland."""
import os
import secrets
from urllib.parse import unquote, urlparse

SERVICE = "org.freedesktop.portal.Desktop"
PATH = "/org/freedesktop/portal/desktop"
SCREENSHOT = "org.freedesktop.portal.Screenshot"
REQUEST = "org.freedesktop.portal.Request"


class ScreenshotError(RuntimeError):
    pass


def request_path(unique_name, token):
    """Where the portal will answer: /.../request/<caller with ':' dropped and '.' as '_'>/<token>."""
    return f"{PATH}/request/{unique_name.lstrip(':').replace('.', '_')}/{token}"


def uri_to_path(uri):
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ScreenshotError(f"unexpected screenshot location: {uri}")
    return unquote(parsed.path)


def screenshot(timeout=10, connect=None):
    """Take a full-desktop screenshot and return the PNG's path (the caller deletes it). Raises ScreenshotError."""
    from jeepney import DBusAddress, MatchRule, message_bus, new_method_call
    from jeepney.io.blocking import Proxy, open_dbus_connection
    conn = (connect or open_dbus_connection)(bus="SESSION")
    try:
        token = "dictate" + secrets.token_hex(6)
        handle = request_path(conn.unique_name, token)
        rule = MatchRule(type="signal", interface=REQUEST, member="Response", path=handle)
        Proxy(message_bus, conn).AddMatch(rule)
        with conn.filter(rule) as answers:
            options = {"handle_token": ("s", token), "interactive": ("b", False)}
            reply = conn.send_and_get_reply(new_method_call(DBusAddress(PATH, SERVICE, SCREENSHOT), "Screenshot", "sa{sv}", ("", options)), timeout=timeout)
            if reply.header.message_type.name == "error":
                raise ScreenshotError(f"screenshot portal: {reply.body[0] if reply.body else 'error'}")
            try:
                signal = conn.recv_until_filtered(answers, timeout=timeout)
            except TimeoutError as e:
                raise ScreenshotError("screenshot portal did not answer") from e
        code, results = signal.body
        if code != 0:
            raise ScreenshotError("screenshot was cancelled or denied" if code == 1 else f"screenshot failed ({code})")
        return uri_to_path(results["uri"][1])
    finally:
        conn.close()


def read_and_remove(path):
    """The PNG's bytes; the file is deleted so screenshots never pile up in ~/Pictures."""
    try:
        with open(path, "rb") as f:
            return f.read()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
