"""Bottom-of-screen waveform / spinner overlay, driven by datagrams from dictate.py.

A click-through, non-focusable, transparent window: bars follow your voice while the key
is held, a spinner loops while the model transcribes, then it fades away.
Messages (abstract unix socket "dictate-overlay"): rec | lvl <rms> | busy | idle
"""
import colorsys
import math
import socket
from collections import deque

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import ipc  # noqa: E402

W, H = 150, 40          # window size (pill is drawn centred inside)
BARS = 16
REC_W, BUSY_W, PILL_H = 124, 44, 28
BOTTOM_GAP = 8


def aurora(t):
    """Cyan -> violet -> pink gradient; t in [0, 1) wraps around smoothly."""
    return colorsys.hsv_to_rgb(0.50 + 0.38 * (0.5 - 0.5 * math.cos(2 * math.pi * (t % 1.0))), 0.62, 1.0)


class Overlay:
    def __init__(self):
        self.state, self.alpha, self.pill_w, self.phase = "idle", 0.0, float(REC_W), 0.0
        self.hist = deque([0.0] * BARS, maxlen=BARS)
        self.disp = [0.0] * BARS
        self.ref = 0.03            # adaptive loudness reference so quiet mics still move the bars
        self.timer = None
        self.extra = None          # callback for non-animation messages (snip / paste / note ...)

        win = self.win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        win.set_title("dictate-overlay")
        win.set_decorated(False)
        win.set_app_paintable(True)
        win.set_accept_focus(False)
        win.set_focus_on_map(False)
        win.set_skip_taskbar_hint(True)
        win.set_skip_pager_hint(True)
        win.set_keep_above(True)
        win.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        win.set_default_size(W, H)
        win.set_size_request(W, H)
        win.set_resizable(False)
        visual = win.get_screen().get_rgba_visual()
        if visual:
            win.set_visual(visual)
        win.connect("draw", self.draw)
        win.connect("realize", self.on_realize)
        win.show_all()  # stays mapped but fully transparent while idle (re-mapping could steal focus)

        sock = self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.setblocking(False)
        try:
            sock.bind(ipc.OVERLAY)
        except OSError:
            pass  # another tray already owns it
        GLib.io_add_watch(sock.fileno(), GLib.IO_IN, self.on_data)

    def on_realize(self, win):
        gdk = win.get_window()
        gdk.input_shape_combine_region(cairo.Region(), 0, 0)   # click-through
        mon = Gdk.Display.get_default().get_primary_monitor() or Gdk.Display.get_default().get_monitor(0)
        area = mon.get_workarea()
        win.move(area.x + (area.width - W) // 2, area.y + area.height - H - BOTTOM_GAP)

    # ---- events -----------------------------------------------------------
    def on_data(self, *_):
        while True:
            try:
                msg = self.sock.recv(65536).decode()
            except (BlockingIOError, OSError):
                break
            self.handle(msg)
        return True

    def handle(self, msg):
        if msg in ("snip", "paste", "cancel", "ctrlv") or msg.startswith("note "):
            if self.extra:
                self.extra(msg)
            return
        if msg == "rec":
            self.state = "rec"
            self.hist.extend([0.0] * BARS)
            self.ref = 0.03
        elif msg.startswith("lvl "):
            if self.state == "idle":     # levels only stream while recording: self-heal if an idle arrived late
                self.state = "rec"
            rms = float(msg[4:])
            self.ref = max(self.ref * 0.985, rms, 0.02)
            floor = 0.004                                   # ignore room noise
            self.hist.append(min(1.0, max(0.0, (rms - floor) / (self.ref - floor))))
        elif msg == "busy":
            self.state = "busy"
        elif msg == "idle":
            self.state = "idle"
        if self.timer is None:
            self.timer = GLib.timeout_add(33, self.tick)

    # ---- animation --------------------------------------------------------
    def tick(self):
        target_a = 0.0 if self.state == "idle" else 1.0
        self.alpha += (target_a - self.alpha) * 0.25
        target_w = REC_W if self.state == "rec" else BUSY_W
        self.pill_w += (target_w - self.pill_w) * 0.25
        self.phase += 0.033
        for i, v in enumerate(self.hist):
            self.disp[i] += (v - self.disp[i]) * (0.85 if v > self.disp[i] else 0.35)  # fast attack, slower release
        self.win.queue_draw()
        if self.state == "idle" and self.alpha < 0.01:
            self.alpha, self.timer = 0.0, None
            self.win.queue_draw()
            return False
        return True

    def draw(self, widget, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        if self.alpha <= 0.01:
            return
        a, cx, cy, pw = self.alpha, widget.get_allocated_width() / 2, widget.get_allocated_height() / 2, self.pill_w
        x0, y0, r = cx - pw / 2, cy - PILL_H / 2, PILL_H / 2
        cr.new_sub_path()
        cr.arc(x0 + pw - r, y0 + r, r, -math.pi / 2, math.pi / 2)
        cr.arc(x0 + r, y0 + r, r, math.pi / 2, 3 * math.pi / 2)
        cr.close_path()
        cr.set_source_rgba(0.06, 0.06, 0.07, 0.62 * a)
        cr.fill()

        if self.state == "busy":
            self.draw_spinner(cr, cx, cy, a)
        else:
            self.draw_bars(cr, cx, cy, a)

    def draw_bars(self, cr, cx, cy, a):
        pitch, bw = (REC_W - 24) / BARS, 3.0
        left = cx - (BARS * pitch) / 2
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(bw)
        for i, v in enumerate(self.disp):
            h = 3 + v * (PILL_H - 8)
            x = left + pitch * (i + 0.5)
            edge = min(i, BARS - 1 - i) / 4.0           # taper the ends
            red, grn, blu = aurora(i / BARS * 0.8 + self.phase * 0.25)   # colours drift slowly
            cr.set_source_rgba(red, grn, blu, a * (0.45 + 0.55 * min(1.0, edge)))
            cr.move_to(x, cy - h / 2)
            cr.line_to(x, cy + h / 2)
            cr.stroke()

    def draw_spinner(self, cr, cx, cy, a):
        n, radius = 8, 7
        head = (self.phase * 1.6) % 1.0 * n              # loops once every ~0.6s
        for i in range(n):
            ang = i / n * 2 * math.pi - math.pi / 2
            fade = ((head - i) % n) / n                    # 0 at the head, 1 at the tail
            red, grn, blu = aurora(i / n)
            cr.set_source_rgba(red, grn, blu, a * (1.0 - 0.85 * fade))
            cr.arc(cx + radius * math.cos(ang), cy + radius * math.sin(ang), 1.9 - 0.9 * fade, 0, 2 * math.pi)
            cr.fill()
