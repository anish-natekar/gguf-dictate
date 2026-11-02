"""Snip + annotate + voice notes + paste-all queue. Runs inside the tray process.

Flow: snip hotkey -> frozen screen, drag a region (or Enter/F for full screen) -> draw in one of the
colours (keys 1-5), hold the dictate key to add a voice note under the selected colour's heading ->
Enter queues it. The paste hotkey then pastes every queued image + its notes, in order.
"""
import json
import subprocess
import time
from pathlib import Path

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

QUEUE_DIR = Path.home() / ".local" / "share" / "dictate" / "queue"
FLAG = Path("/tmp/dictate-editor")      # exists while the editor is open: dictate.py then sends notes here
DEFAULT_COLORS = [["Red", "#ff3b30"], ["Blue", "#0a84ff"], ["Green", "#30d158"], ["Yellow", "#ffd60a"], ["Purple", "#bf5af2"]]
KEYS = "0 box   1-5 colour   F full screen   Ctrl+Z undo   hold dictate key or Speak = voice note   Enter save   Esc cancel"


def rgb(hexv):
    c = Gdk.RGBA()
    c.parse(hexv)
    return c.red, c.green, c.blue


def format_notes(n, notes):
    """'Screenshot 2' + one '## Colour' heading per colour that has notes."""
    out, seen = [], []
    for note in notes:
        if note["color"] not in seen:
            seen.append(note["color"])
    for color in seen:
        out.append(f"## {color}\n" + "\n".join(f"- {x['text']}" for x in notes if x["color"] == color))
    return f"Screenshot {n}\n\n" + "\n\n".join(out) if out else ""


class Queue:
    def __init__(self):
        QUEUE_DIR.mkdir(parents=True, exist_ok=True)

    def items(self):
        out = []
        for png in sorted(QUEUE_DIR.glob("*.png")):
            try:
                out.append((png, json.loads(png.with_suffix(".json").read_text())))
            except (OSError, ValueError):
                out.append((png, []))
        return out

    def add(self, surface, notes):
        base = QUEUE_DIR / str(time.time_ns())
        surface.write_to_png(str(base.with_suffix(".png")))
        base.with_suffix(".json").write_text(json.dumps(notes))

    def clear(self):
        for f in QUEUE_DIR.glob("*"):
            f.unlink()


class Editor:
    """sel is None -> box tool (no colour: drag to set the capture box); otherwise the pen in colour sel."""

    def __init__(self, pixbuf, colors, on_done, speak):
        self.pix, self.colors, self.on_done, self.speak = pixbuf, colors, on_done, speak
        self.rect, self.drag, self.cur = None, None, None      # rect None = whole screen
        self.strokes, self.history, self.sel, self.talking = [], [], None, False
        self.notes = [[] for _ in range(len(colors) + 1)]       # last list = "General" (no colour selected)
        self.install_css()

        win = self.win = Gtk.Window()
        win.set_decorated(False)
        win.set_keep_above(True)
        win.connect("key-press-event", self.on_key)
        win.connect("destroy", lambda *_: (FLAG.unlink(missing_ok=True), self.release_keys()))
        area = self.area = Gtk.DrawingArea()
        area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        area.connect("draw", self.draw)
        area.connect("button-press-event", self.on_press)
        area.connect("motion-notify-event", self.on_motion)
        area.connect("button-release-event", self.on_release)

        bar = Gtk.Box(spacing=4)
        bar.get_style_context().add_class("snipbar")

        def button(icon, tip, cb, cls="snipicon", label=None):
            b = Gtk.Button(can_focus=False, tooltip_text=tip)
            if label:
                b.set_label(label)
            elif Gtk.IconTheme.get_default().has_icon(icon):
                b.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))
            else:
                b.set_label(tip.split()[0])
            for c in cls.split():
                b.get_style_context().add_class(c)
            b.connect("clicked", lambda _b: cb())
            bar.pack_start(b, False, False, 0)
            return b

        def sep():
            bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL, margin=4), False, False, 0)

        self.btns = [button("edit-select-all-symbolic", "Box tool (0): drag to choose the capture area", lambda: self.pick(None), "snipicon snipbox")]
        sep()
        for i, (name, _) in enumerate(colors):
            self.btns.append(button("", f"{name} pen ({i + 1})", lambda i=i: self.pick(i), f"snipsw snipc{i}", label=" "))
        self.width = 5
        size = Gtk.MenuButton(can_focus=False, tooltip_text="Pen size")
        size.get_style_context().add_class("snipicon")
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin=6)
        for label, w in (("Thin", 3), ("Medium", 5), ("Thick", 9)):
            r = Gtk.ModelButton(text=label)
            r.connect("clicked", lambda _b, w=w: setattr(self, "width", w))
            box.pack_start(r, False, False, 0)
        box.show_all()
        pop.add(box)
        size.set_popover(pop)
        size.set_image(Gtk.Image.new_from_icon_name("document-edit-symbolic", Gtk.IconSize.BUTTON))
        bar.pack_start(size, False, False, 0)
        sep()
        button("view-fullscreen-symbolic", "Full screen (F)", self.full_screen)
        button("edit-undo-symbolic", "Undo (Ctrl+Z)", self.undo)
        button("edit-clear-all-symbolic", "Clear pen strokes", self.clear)
        self.speak_btn = button("microphone-sensitivity-high-symbolic", "Speak a note (or hold the dictate key)", self.toggle_speak, "snipicon snipspeak")
        sep()
        button("", "Save (Enter)", self.save, "snipok", label="Save")
        button("window-close-symbolic", "Cancel (Esc)", self.cancel)

        self.hint = Gtk.Label()
        self.hint.get_style_context().add_class("sniphint")
        dock = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, halign=Gtk.Align.CENTER, valign=Gtk.Align.END, margin_bottom=56)
        dock.pack_start(self.hint, False, False, 0)
        dock.pack_start(bar, False, False, 0)
        self.panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, halign=Gtk.Align.END, valign=Gtk.Align.END, margin_end=18, margin_bottom=56)
        self.panel.get_style_context().add_class("snippanel")
        self.panel.set_no_show_all(True)

        ov = Gtk.Overlay()
        ov.add(area)
        for w in (dock, self.panel):
            ov.add_overlay(w)
            ov.set_overlay_pass_through(w, False)
        win.add(ov)
        self.pick(None)
        mon = Gdk.Display.get_default().get_monitor_at_point(*self.pointer())
        g = mon.get_geometry()
        win.move(g.x, g.y)
        win.set_default_size(g.width, g.height)
        win.fullscreen()
        win.show_all()
        win.present_with_time(Gdk.CURRENT_TIME)
        win.get_window().focus(Gdk.CURRENT_TIME)
        # grab the keyboard so Esc / Ctrl+Z / 1-5 always reach us, even if the window manager withholds focus
        GLib.timeout_add(100, self.grab_keys)
        win.get_window().focus(Gdk.CURRENT_TIME)          # window managers often refuse focus to background apps
        GLib.timeout_add(150, lambda: win.get_window() and win.get_window().focus(Gdk.CURRENT_TIME) and False)
        win.get_window().set_cursor(Gdk.Cursor.new_from_name(Gdk.Display.get_default(), "crosshair"))
        FLAG.touch()

    def grab_keys(self):
        gw = self.win.get_window()
        if gw and gw.is_visible():
            Gdk.Display.get_default().get_default_seat().grab(gw, Gdk.SeatCapabilities.KEYBOARD, False, None, None, None)
        return False

    def release_keys(self):
        Gdk.Display.get_default().get_default_seat().ungrab()

    @staticmethod
    def pointer():
        _, x, y = Gdk.Display.get_default().get_default_seat().get_pointer().get_position()[:3]
        return x, y

    def install_css(self):
        css = (".snipbar { background: rgba(24,24,28,.93); border-radius: 24px; padding: 6px 12px; color: white; }\n"
               ".snippanel { background: rgba(24,24,28,.93); border-radius: 14px; padding: 8px 12px; color: white; font-size: 12px; }\n"
               ".sniphint { background: rgba(24,24,28,.8); border-radius: 12px; padding: 3px 12px; color: #ddd; font-size: 12px; }\n"
               ".snipicon { background: none; border: 2px solid transparent; box-shadow: none; border-radius: 16px; padding: 4px 8px; color: white; }\n"
               ".snipicon:hover { background: rgba(255,255,255,.16); }\n.snipicon.sel { border-color: white; }\n"
               ".snipspeak.rec { background: #d32f2f; }\n"
               ".snipok { background-image: none; background: #30d158; color: #111; font-weight: bold; border-radius: 16px; padding: 4px 14px; border: none; }\n"
               ".snipsw { background-image: none; min-width: 22px; min-height: 22px; padding: 0; border-radius: 50%; border: 2px solid rgba(255,255,255,.3); }\n"
               ".snipsw.sel { border: 3px solid white; }\n")
        for i, (_, hexv) in enumerate(self.colors):
            css += f".snipc{i} {{ background: {hexv}; }}\n"
        p = Gtk.CssProvider()
        p.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    # ---- state ------------------------------------------------------------
    def pick(self, i):
        if i is not None and i >= len(self.colors):
            return
        self.sel = i
        for j, b in enumerate(self.btns):
            (b.get_style_context().add_class if j == (0 if i is None else i + 1) else b.get_style_context().remove_class)("sel")
        self.hint.set_text("Drag to choose the area, then pick a colour to draw" if i is None else f"Drawing in {self.colors[i][0]}  -  speak to add a note")
        self.refresh_panel()
        self.area.queue_draw()

    def note_slot(self):
        return len(self.colors) if self.sel is None else self.sel

    def add_note(self, text):
        self.notes[self.note_slot()].append(text)
        self.set_talking(False)
        self.refresh_panel()

    def set_talking(self, on):
        self.talking = on
        (self.speak_btn.get_style_context().add_class if on else self.speak_btn.get_style_context().remove_class)("rec")
        self.refresh_panel()

    def toggle_speak(self):
        self.set_talking(not self.talking)
        self.speak("start" if self.talking else "stop")

    def refresh_panel(self):
        for c in self.panel.get_children():
            c.destroy()
        slot = self.note_slot()
        names = [(n, h) for n, h in self.colors] + [("General", "#cccccc")]
        self.panel.pack_start(Gtk.Label(label="Recording..." if self.talking else f"Notes -> {names[slot][0]}", xalign=0), False, False, 0)
        for i, (nm, hx) in enumerate(names):
            if self.notes[i]:
                h = Gtk.Label(xalign=0)
                h.set_markup(f'<b><span foreground="{hx}">{nm}</span></b>')
                self.panel.pack_start(h, False, False, 0)
                for t in self.notes[i]:
                    self.panel.pack_start(Gtk.Label(label="- " + t, xalign=0, wrap=True, max_width_chars=34), False, False, 0)
        for c in self.panel.get_children():
            c.show()
        self.panel.set_visible(self.talking or any(self.notes))

    def undo(self):
        if not self.history:
            return
        kind, old = self.history.pop()
        if kind == "rect":
            self.rect = old
        elif self.strokes:
            self.strokes.pop()
        self.area.queue_draw()

    def clear(self):
        self.strokes.clear()
        self.history = [h for h in self.history if h[0] == "rect"]
        self.area.queue_draw()

    def full_screen(self):
        if self.rect is not None:
            self.history.append(("rect", self.rect))
            self.rect = None
            self.area.queue_draw()

    def cancel(self):
        if self.talking:
            self.speak("stop")
        self.win.destroy()

    def save(self):
        x, y, w, h = self.rect or (0, 0, self.pix.get_width(), self.pix.get_height())
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        cr = cairo.Context(surf)
        cr.translate(-x, -y)
        Gdk.cairo_set_source_pixbuf(cr, self.pix, 0, 0)
        cr.paint()
        self.paint_strokes(cr)
        names = [n for n, _ in self.colors] + ["General"]
        notes = [{"color": names[i], "text": t} for i in range(len(names)) for t in self.notes[i]]
        if self.talking:
            self.speak("stop")
        self.win.destroy()
        self.on_done(surf, notes)

    # ---- input ------------------------------------------------------------
    def on_key(self, _w, ev):
        key = Gdk.keyval_name(ev.keyval)
        if key == "Escape":
            self.cancel()
        elif key in ("Return", "KP_Enter"):
            self.save()
        elif key in ("z", "Z") and ev.state & Gdk.ModifierType.CONTROL_MASK:
            self.undo()
        elif key in ("b", "B", "0"):
            self.pick(None)
        elif key in ("f", "F"):
            self.full_screen()
        elif key and key.isdigit():
            self.pick(int(key) - 1)
        elif key == "BackSpace" and self.notes[self.note_slot()]:
            self.notes[self.note_slot()].pop()
            self.refresh_panel()
        return True

    def on_press(self, _w, ev):
        if ev.button != 1:
            return
        if self.sel is None:
            self.drag, self.before = (ev.x, ev.y), self.rect
        else:
            self.cur = {"color": self.sel, "w": self.width, "pts": [(ev.x, ev.y)]}
            self.strokes.append(self.cur)
            self.history.append(("stroke", None))

    def on_motion(self, _w, ev):
        if self.sel is None and self.drag:
            x0, y0 = self.drag
            self.rect = (int(min(x0, ev.x)), int(min(y0, ev.y)), int(abs(ev.x - x0)), int(abs(ev.y - y0)))
        elif self.cur:
            self.cur["pts"].append((ev.x, ev.y))
        else:
            return
        self.area.queue_draw()

    def on_release(self, _w, ev):
        if self.drag:
            self.drag = None
            if self.rect and self.rect != self.before and self.rect[2] > 8 and self.rect[3] > 8:
                self.history.append(("rect", self.before))     # Ctrl+Z restores the previous box
            else:
                self.rect = self.before                         # a click or tiny drag changes nothing
        self.cur = None
        self.area.queue_draw()

    # ---- drawing ----------------------------------------------------------
    def paint_strokes(self, cr):
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        for s in self.strokes:
            cr.set_line_width(s.get("w", 4))
            cr.set_source_rgb(*rgb(self.colors[s["color"]][1]))
            pts = s["pts"]
            cr.move_to(*pts[0])
            if len(pts) == 1:
                cr.line_to(pts[0][0] + 0.1, pts[0][1])
            for p in pts[1:]:
                cr.line_to(*p)
            cr.stroke()

    def draw(self, widget, cr):
        W, H = widget.get_allocated_width(), widget.get_allocated_height()
        Gdk.cairo_set_source_pixbuf(cr, self.pix, 0, 0)
        cr.paint()
        if self.rect:
            x, y, w, h = self.rect
            cr.set_source_rgba(0, 0, 0, 0.5)       # dim everything outside the box
            for r in ((0, 0, W, y), (0, y + h, W, H - y - h), (0, y, x, h), (x + w, y, W - x - w, h)):
                cr.rectangle(*r)
            cr.fill()
            cr.set_source_rgba(1, 1, 1, 0.9)
            cr.set_line_width(1)
            cr.rectangle(x + .5, y + .5, w, h)
            cr.stroke()
            cr.save()
            cr.rectangle(x, y, w, h)
            cr.clip()
            self.paint_strokes(cr)
            cr.restore()
        else:
            self.paint_strokes(cr)


class Snip:
    def __init__(self, on_change, speak):
        self.queue, self.on_change, self.speak, self.editor, self.pasting = Queue(), on_change, speak, None, False
        FLAG.unlink(missing_ok=True)

    def count(self):
        return len(self.queue.items())

    def start(self, colors):
        if self.editor or self.pasting:
            return
        d = Gdk.Display.get_default()
        mon = d.get_monitor_at_point(*Editor.pointer())
        g = mon.get_geometry()
        root = Gdk.get_default_root_window()
        pix = Gdk.pixbuf_get_from_window(root, g.x, g.y, g.width, g.height)
        cols = [c for c in (colors or DEFAULT_COLORS) if len(c) == 2][:9] or DEFAULT_COLORS
        self.editor = Editor(pix, cols, self.finished, self.speak)
        self.editor.win.connect("destroy", lambda *_: setattr(self, "editor", None))

    def finished(self, surface, notes):
        self.queue.add(surface, notes)
        self.on_change()

    def note(self, text):
        if self.editor:
            self.editor.add_note(text)

    def clear(self):
        self.queue.clear()
        self.on_change()

    # ---- paste all --------------------------------------------------------
    def paste_all(self):
        items = self.queue.items()
        if self.pasting or self.editor or not items:
            return
        steps = []
        for n, (png, notes) in enumerate(items, 1):
            steps.append(("img", png))
            if notes:
                steps.append(("txt", format_notes(n, notes)))
        self.pasting = True
        self.run(steps)

    def run(self, steps):
        if not steps:
            self.queue.clear()
            self.pasting = False
            self.on_change()
            return False
        kind, val = steps[0]
        cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        if kind == "img":
            cb.set_image(GdkPixbuf.Pixbuf.new_from_file(str(val)))
        else:
            cb.set_text(val, -1)
        GLib.timeout_add(150, self.press, steps)
        return False

    def press(self, steps):
        subprocess.Popen(["xdotool", "key", "--clearmodifiers", "ctrl+v"])
        GLib.timeout_add(1500 if steps[0][0] == "img" else 600, self.run, steps[1:])   # images need time to upload
        return False
