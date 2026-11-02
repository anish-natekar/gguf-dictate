"""Transparent, click-through waveform pill at the bottom of the screen."""
import math

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget

from gguf_dictate.core.overlay_model import BARS, BUSY_W, PILL_H, REC_W, OverlayModel, aurora

W, H = 150, 40
BOTTOM_GAP = 8
TICK_MS = 33
SPINNER_DOTS = 8


class Overlay(QWidget):
    message = Signal(str)

    def __init__(self, extra=None):
        super().__init__()
        self.extra = extra or (lambda _msg: None)
        self.model = OverlayModel()
        self.timer = None
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.resize(W, H)
        self.message.connect(self.handle, Qt.QueuedConnection)
        self.place()

    def place(self):
        screen = QGuiApplication.primaryScreen() or self.screen()
        g = screen.availableGeometry()
        self.move(g.center().x() - W // 2, g.bottom() - H - BOTTOM_GAP + 1)

    def post(self, msg):
        """Thread-safe entry point."""
        self.message.emit(msg)

    def handle(self, msg):
        out = self.model.handle(msg)
        if out is None:
            return
        if out[0] == "extra":
            self.extra(out[1])
        elif self.timer is None:
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.step)
            self.timer.start(TICK_MS)

    def step(self):
        if not self.model.tick() and self.timer is not None:
            self.timer.stop()
            self.timer.deleteLater()
            self.timer = None
        self.update()

    def paintEvent(self, _event):
        m = self.model
        if m.alpha <= 0.0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = m.pill_w
        x0, y0 = (W - w) / 2, (H - PILL_H) / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor.fromRgbF(0.06, 0.06, 0.07, 0.62 * m.alpha))
        p.drawRoundedRect(QRectF(x0, y0, w, PILL_H), PILL_H / 2, PILL_H / 2)
        if m.state == "busy":
            self.paint_spinner(p)
        else:
            self.paint_bars(p, x0, y0, w)
        p.end()

    def paint_bars(self, p, x0, y0, w):
        m = self.model
        pad = 12
        step = (w - 2 * pad) / BARS
        bw = step * 0.55
        mid = y0 + PILL_H / 2
        for i, v in enumerate(m.disp):
            taper = 0.35 + 0.65 * math.sin(math.pi * (i + 0.5) / BARS)
            h = max(2.0, v * (PILL_H - 10) * taper)
            r, g, b = aurora((m.phase + i / BARS) % 1.0)
            p.setBrush(QColor.fromRgbF(r, g, b, m.alpha))
            p.drawRoundedRect(QRectF(x0 + pad + i * step + (step - bw) / 2, mid - h / 2, bw, h), bw / 2, bw / 2)

    def paint_spinner(self, p):
        m = self.model
        n = SPINNER_DOTS
        head = (m.phase * 1.6) % 1.0 * n
        for i in range(n):
            ang = 2 * math.pi * i / n
            fade = 1.0 - ((head - i) % n) / n
            r, g, b = aurora(i / n)
            p.setBrush(QColor.fromRgbF(r, g, b, m.alpha * (0.25 + 0.75 * fade)))
            p.drawEllipse(QRectF(W / 2 + 7 * math.cos(ang) - 2, H / 2 + 7 * math.sin(ang) - 2, 4, 4))


__all__ = ["Overlay", "BUSY_W", "REC_W"]
