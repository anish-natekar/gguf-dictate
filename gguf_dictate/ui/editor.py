"""Frozen-screen annotation editor (Qt). All rules live in core.editor_model; this file is painting, input and layout."""
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..core.editor_model import EditorModel

BLUE = QColor(10, 133, 255)

STYLE = """
QFrame#bar { background: rgba(24,24,28,235); border-radius: 24px; }
QFrame#panel { background: rgba(24,24,28,235); border-radius: 14px; }
QLabel { color: white; font-size: 12px; }
QLabel#hint { background: rgba(24,24,28,205); border-radius: 12px; padding: 3px 12px; color: #ddd; }
QLabel#queue { background: #0a85ff; border-radius: 10px; padding: 3px 10px; font-weight: bold; }
QPushButton { background: transparent; color: white; border: 2px solid transparent; border-radius: 16px; padding: 4px 10px; }
QPushButton:hover { background: rgba(255,255,255,40); }
QPushButton:checked { border-color: white; }
QPushButton[kb="true"] { background: rgba(255,255,255,56); }
QPushButton#swatch { min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px; padding: 0; border-radius: 13px;
                     border: 2px solid rgba(255,255,255,77); }
QPushButton#swatch:checked { border: 3px solid white; }
QPushButton#save { background: #30d158; color: #111; font-weight: bold; padding: 4px 14px; }
QPushButton#speak[rec="true"] { background: #d32f2f; }
"""
LABELS = {"size": "Size", "full": "Full", "undo": "Undo", "clear": "Clear", "speak": "Speak", "save": "Save", "cancel": "Cancel"}


class QImageSurface:
    """What notes.Queue.add expects: anything with write_to_png(path)."""

    def __init__(self, image):
        self.image = image

    def write_to_png(self, path):
        if not self.image.save(path, "PNG"):
            raise OSError(f"could not write {path}")


class Canvas(QWidget):
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.setCursor(Qt.CrossCursor)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        v, m = self.view, self.view.model
        p.drawPixmap(0, 0, v.shot)
        W, H = self.width(), self.height()
        if m.rect:
            x, y, w, h = m.rect
            dim = QColor(0, 0, 0, 128)
            for r in ((0, 0, W, y), (0, y + h, W, H - y - h), (0, y, x, h), (x + w, y, W - x - w, h)):
                p.fillRect(*r, dim)                         # dim everything outside the box
            p.save()
            p.setClipRect(x, y, w, h)
            v.paint_strokes(p)
            p.restore()
            p.setPen(QPen(BLUE, 2))
            p.drawRect(x - 1, y - 1, w + 2, h + 2)          # blue capture-box boundary
            self.badge(p, x - 1, max(0, y - 25), f"{w} x {h}")
        else:
            v.paint_strokes(p)
            p.setPen(QPen(BLUE, 6))                         # no box: the whole screen is captured, so frame it
            p.drawRect(3, 3, W - 6, H - 6)
            self.badge(p, 12, 12, "Full screen")
        p.end()

    @staticmethod
    def badge(p, x, y, text):
        f = p.font()
        f.setBold(True)
        f.setPixelSize(13)
        p.setFont(f)
        w = p.fontMetrics().horizontalAdvance(text) + 16
        p.fillRect(QRect(x, y, w, 24), BLUE)
        p.setPen(Qt.white)
        p.drawText(QRect(x, y, w, 24), Qt.AlignCenter, text)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.view.model.press(e.position().x(), e.position().y())
            self.view.sync()

    def mouseMoveEvent(self, e):
        if self.view.model.move(e.position().x(), e.position().y()):
            self.update()

    def mouseReleaseEvent(self, _):
        self.view.model.release()
        self.view.sync()


class EditorView(QWidget):
    def __init__(self, shot, colors, on_done, speak, fullscreen=True, on_close=None):
        super().__init__()
        self.shot, self.on_done, self.speak, self.fullscreen, self.on_close = shot, on_done, speak, fullscreen, on_close
        self.model = EditorModel(colors)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setStyleSheet(STYLE)
        self.setFocusPolicy(Qt.StrongFocus)
        self.resize(int(shot.width() / shot.devicePixelRatio()), int(shot.height() / shot.devicePixelRatio()))
        self.canvas = Canvas(self)

        self.buttons = []
        bar = QFrame(objectName="bar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 6, 12, 6)
        for i, (label, kind, action) in enumerate(self.model.items):
            self.buttons.append(self._button(i, label, kind, action, row))
        self.speak_btn = self.buttons[[a for _, _, a in self.model.items].index("speak")]
        self.hint = QLabel(objectName="hint")
        self.dock = QWidget(self)
        col = QVBoxLayout(self.dock)
        col.setContentsMargins(0, 0, 0, 0)
        col.addWidget(self.hint, 0, Qt.AlignHCenter)
        col.addWidget(bar)

        self.panel = QFrame(self, objectName="panel")
        self.panel_layout = QVBoxLayout(self.panel)
        self.panel_title = QLabel()
        self.queue_badge = QLabel(self, objectName="queue")
        self.queue_badge.hide()
        self.sync()

    def _button(self, i, label, kind, action, row):
        if kind == "tool":
            b = QPushButton("Box" if i == 0 else "", objectName="" if i == 0 else "swatch")
            b.setCheckable(True)
            if i:
                b.setStyleSheet(f"background: {self.model.colors[i - 1][1]};")
            b.clicked.connect(lambda _=False, i=i: self.pick(None if i == 0 else i - 1))
        else:
            b = QPushButton(LABELS[action], objectName=action if action in ("save", "speak") else "")
            b.clicked.connect(lambda _=False, a=action: self.run(a))
        b.setToolTip(label)
        b.setFocusPolicy(Qt.NoFocus)
        row.addWidget(b)
        return b

    # ---- lifecycle --------------------------------------------------------
    def open(self):
        """Show over the whole screen and take the keyboard so Esc / Ctrl+Z / 1-5 always reach us."""
        self.showFullScreen() if self.fullscreen else self.show()
        self.raise_()
        self.activateWindow()
        self.grabKeyboard()

    def closeEvent(self, e):
        self.releaseKeyboard()
        super().closeEvent(e)
        if self.on_close:
            self.on_close()

    def resizeEvent(self, e):
        self.canvas.setGeometry(0, 0, self.width(), self.height())
        self.layout_overlays()
        super().resizeEvent(e)

    def layout_overlays(self):
        W, H = self.width(), self.height()
        self.dock.adjustSize()
        self.dock.move((W - self.dock.width()) // 2, H - self.dock.height() - 20)
        self.panel.adjustSize()
        self.panel.move(W - self.panel.width() - 18, H - self.panel.height() - 20)
        self.queue_badge.adjustSize()
        self.queue_badge.move(12, 44)
        for w in (self.dock, self.panel, self.queue_badge):
            w.raise_()

    # ---- actions ----------------------------------------------------------
    def sync(self):
        m = self.model
        cur = 0 if m.sel is None else m.sel + 1
        for i, b in enumerate(self.buttons):
            if self.model.items[i][1] == "tool":
                b.setChecked(i == cur)
            b.setProperty("kb", i == m.focus)
            b.style().unpolish(b)
            b.style().polish(b)
        self.speak_btn.setProperty("rec", m.talking)
        self.speak_btn.style().unpolish(self.speak_btn)
        self.speak_btn.style().polish(self.speak_btn)
        self.hint.setText(m.hint)
        self.refresh_panel()
        self.canvas.update()

    def refresh_panel(self):
        m = self.model
        self.panel_title.setText(m.panel_title())
        lay = self.panel_layout
        while lay.count():
            w = lay.takeAt(0).widget()
            if w and w is not self.panel_title:
                w.deleteLater()
        lay.addWidget(self.panel_title)
        for name, hexv, notes in m.panel_rows():
            head = QLabel(f'<b><span style="color:{hexv}">{name}</span></b>')
            lay.addWidget(head)
            for t in notes:
                lab = QLabel("- " + t)
                lab.setWordWrap(True)
                lab.setMaximumWidth(280)
                lay.addWidget(lab)
        self.panel.setVisible(m.panel_visible())
        self.layout_overlays()

    def panel_text(self):
        return " ".join(w.text() for w in self.panel.findChildren(QLabel))

    def set_queued(self, n):
        self.queue_badge.setText(f"Queue: {n} saved")
        self.queue_badge.setVisible(n > 0)
        self.layout_overlays()

    def pick(self, i):
        self.model.pick(i)
        self.sync()

    def run(self, action):
        getattr(self, {"size": "cycle_size", "full": "full_screen", "undo": "undo", "clear": "clear",
                       "speak": "toggle_speak", "save": "save", "cancel": "cancel"}[action])()

    def cycle_size(self):
        self.model.cycle_size()
        self.sync()

    def full_screen(self):
        self.model.full_screen()
        self.sync()

    def undo(self):
        self.model.undo()
        self.sync()

    def clear(self):
        self.model.clear()
        self.sync()

    def add_note(self, text):
        self.model.add_note(text)
        self.sync()

    def set_talking(self, on):
        self.model.talking = on
        self.sync()

    def toggle_speak(self):
        self.set_talking(not self.model.talking)
        self.speak("start" if self.model.talking else "stop")

    def stop_recording(self):
        if self.model.talking:
            self.set_talking(False)
            self.speak("stop")

    def cancel(self):
        self.stop_recording()
        self.close()

    def save(self):
        surface, notes = QImageSurface(self.render_snip()), self.model.notes_for_save()
        self.stop_recording()
        self.close()
        self.on_done(surface, notes)

    # ---- drawing ----------------------------------------------------------
    def paint_strokes(self, p):
        for s in self.model.strokes:
            p.setPen(QPen(QColor(self.model.colors[s["color"]][1]), s.get("w", 4), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            pts = s["pts"]
            path = QPainterPath()
            path.moveTo(*pts[0])
            if len(pts) == 1:
                path.lineTo(pts[0][0] + 0.1, pts[0][1])
            for pt in pts[1:]:
                path.lineTo(*pt)
            p.drawPath(path)

    def render_snip(self):
        r = self.shot.devicePixelRatio()
        lw, lh = int(self.shot.width() / r), int(self.shot.height() / r)
        x, y, w, h = self.model.rect or (0, 0, lw, lh)
        img = QImage(int(w * r), int(h * r), QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(r, r)
        p.translate(-x, -y)
        p.drawPixmap(0, 0, self.shot)
        self.paint_strokes(p)
        p.end()
        return img

    # ---- keyboard ---------------------------------------------------------
    def keyPressEvent(self, e):
        k, ctrl = e.key(), bool(e.modifiers() & Qt.ControlModifier)
        if k == Qt.Key_Escape:
            self.cancel()
        elif k in (Qt.Key_Left, Qt.Key_Right):
            self.model.move_focus(-1 if k == Qt.Key_Left else 1)
            self.sync()
        elif k in (Qt.Key_Return, Qt.Key_Enter):
            if ctrl:
                self.save()
            else:
                action = self.model.activate_focus()
                if action:
                    self.run(action)
        elif k == Qt.Key_Z and ctrl:
            self.undo()
        elif k in (Qt.Key_B, Qt.Key_0):
            self.pick(None)
        elif k == Qt.Key_F:
            self.full_screen()
        elif Qt.Key_1 <= k <= Qt.Key_9:
            self.pick(k - Qt.Key_1)
        elif k == Qt.Key_Backspace:
            self.model.remove_last_note()
            self.sync()
        else:
            super().keyPressEvent(e)
