"""Always-on-top recorder pill for a meeting. It appears ready (a record button and 0:00); after Record it shows a blinking dot,
the elapsed time, pause and save. Drag it anywhere; it snaps to the corners."""
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from gguf_dictate.core.pill_model import MARGIN, clamp, format_elapsed, snap

BLINK_MS = 600
DOT_R = 5
RED, AMBER = QColor("#ff3b30"), QColor("#ffd60a")


def glyph(kind, size=16):
    """White pause / play / record / save / cancel icon drawn by hand: theme icons are dark and vanish on the dark pill."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("white"))
    if kind == "pause":
        p.drawRoundedRect(QRectF(3.5, 2.5, 3, 11), 1, 1)
        p.drawRoundedRect(QRectF(9.5, 2.5, 3, 11), 1, 1)
    elif kind == "play":
        p.drawPolygon(QPolygonF([QPointF(4.5, 2.5), QPointF(13, 8), QPointF(4.5, 13.5)]))
    elif kind == "record":
        p.setBrush(RED)
        p.drawEllipse(QRectF(2.5, 2.5, 11, 11))
    elif kind == "cancel":
        p.setPen(QPen(QColor("white"), 2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(4, 4), QPointF(12, 12))
        p.drawLine(QPointF(12, 4), QPointF(4, 12))
    elif kind == "save":
        p.setPen(QPen(QColor("white"), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline(QPolygonF([QPointF(3, 8.5), QPointF(6.5, 12), QPointF(13, 4.5)]))
    else:
        p.drawRoundedRect(QRectF(3.5, 3.5, 9, 9), 1.5, 1.5)
    p.end()
    return QIcon(pm)


class MeetingPill(QWidget):
    record_clicked = Signal()
    pause_clicked = Signal()
    stop_clicked = Signal()
    cancel_clicked = Signal()
    moved = Signal(int, int)

    def __init__(self, pos=None):
        super().__init__()
        self.paused, self.dot_on, self.grab_offset, self.recording = False, True, None, False
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setCursor(Qt.OpenHandCursor)
        self.setStyleSheet("QLabel { color: white; font-weight: 600; font-size: 14px; }"
                           "QToolButton { border: none; border-radius: 12px; padding: 3px; }"
                           "QToolButton:hover { background: rgba(255, 255, 255, 40); }")
        self.time = QLabel(format_elapsed(0))
        self.record_btn, self.pause_btn, self.stop_btn = self.button("Start recording", "record"), self.button("Pause", "pause"), self.button("Save", "save")
        self.cancel_btn = self.button("Cancel and discard", "cancel")
        self.record_btn.clicked.connect(self.record_clicked)
        self.pause_btn.clicked.connect(self.pause_clicked)
        self.stop_btn.clicked.connect(self.stop_clicked)
        self.cancel_btn.clicked.connect(self.cancel_clicked)
        row = QHBoxLayout(self)
        row.setContentsMargins(26, 5, 8, 5)
        row.setSpacing(6)
        for w in (self.record_btn, self.time, self.pause_btn, self.stop_btn, self.cancel_btn):
            row.addWidget(w)
        self.set_recording(False)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.blink)
        self.timer.start(BLINK_MS)
        self.place(pos)

    @staticmethod
    def button(tip, kind):
        b = QToolButton()
        b.setIcon(glyph(kind))
        b.setToolTip(tip)
        b.setCursor(Qt.ArrowCursor)
        return b

    def screen_rect(self, point=None):
        screen = (QGuiApplication.screenAt(point) if point is not None else None) or QGuiApplication.primaryScreen()
        g = screen.availableGeometry()
        return g.left(), g.top(), g.left() + g.width(), g.top() + g.height()

    def place(self, pos=None):
        if pos is None:
            left, top, right, _ = self.screen_rect()
            self.move(right - self.width() - MARGIN, top + MARGIN)
        else:
            self.move(*clamp(pos[0], pos[1], self.width(), self.height(), self.screen_rect(QPoint(*pos))))

    def set_recording(self, recording):
        """Ready (record button) or recording (pause and save)."""
        self.recording = recording
        self.layout().setContentsMargins(26 if recording else 8, 5, 8, 5)
        self.cancel_btn.setToolTip("Cancel and discard" if recording else "Close")
        self.record_btn.setVisible(not recording)
        self.pause_btn.setVisible(recording)
        self.stop_btn.setVisible(recording)
        self.dot_on = True
        self.adjustSize()
        self.update()

    def set_elapsed(self, seconds):
        self.time.setText(format_elapsed(seconds))

    def set_paused(self, paused):
        self.paused = paused
        self.dot_on = True
        self.pause_btn.setIcon(glyph("play" if paused else "pause"))
        self.pause_btn.setToolTip("Resume" if paused else "Pause")
        self.update()

    def blink(self):
        if self.recording and not self.paused:
            self.dot_on = not self.dot_on
            self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(22, 22, 25, 235))
        p.drawRoundedRect(QRectF(self.rect()), self.height() / 2, self.height() / 2)
        if self.recording:
            dot = QColor(AMBER if self.paused else RED)
            if not self.dot_on:
                dot.setAlpha(70)
            p.setBrush(dot)
            p.drawEllipse(QPoint(15, self.height() // 2), DOT_R, DOT_R)
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.grab_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self.grab_offset is not None and e.buttons() & Qt.LeftButton:
            there = e.globalPosition().toPoint()
            target = there - self.grab_offset
            self.move(*clamp(target.x(), target.y(), self.width(), self.height(), self.screen_rect(there)))

    def mouseReleaseEvent(self, e):
        if self.grab_offset is None:
            return
        self.grab_offset = None
        self.setCursor(Qt.OpenHandCursor)
        screen = self.screen_rect(e.globalPosition().toPoint())
        x, y = snap(self.x(), self.y(), self.width(), self.height(), screen)
        x, y = clamp(x, y, self.width(), self.height(), screen)
        self.move(x, y)
        self.moved.emit(x, y)
