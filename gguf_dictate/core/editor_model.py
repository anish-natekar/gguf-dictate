"""State and rules of the annotation editor (tools, strokes, capture box, undo, notes, toolbar focus). No GUI toolkit."""

WIDTHS = [("Thin", 3), ("Medium", 5), ("Thick", 9)]
MIN_BOX = 8     # a smaller drag is a click, not a new box
GENERAL = ("General", "#cccccc")
ACTIONS = [("Pen size", "size"), ("Full screen (F)", "full"), ("Undo (Ctrl+Z)", "undo"), ("Clear pen strokes", "clear"),
           ("Speak a note (or hold the dictate key)", "speak"), ("Undo last note (Backspace)", "unnote"),
           ("Save (Ctrl+Enter)", "save"), ("Cancel (Esc)", "cancel")]
HINT_BOX = "Drag to choose the area, then pick a colour to draw"


class EditorModel:
    """sel is None -> box tool (no colour: drag sets the capture box); otherwise the pen in colour `sel`. rect None = whole screen."""

    def __init__(self, colors):
        self.colors = [tuple(c) for c in colors]
        self.rect, self.drag, self.before, self.cur = None, None, None, None
        self.strokes, self.history, self.sel, self.talking = [], [], None, False
        self.notes = [[] for _ in range(len(self.colors) + 1)]        # last list = "General" (no colour selected)
        self.note_order = []      # slot of each note, oldest first, so undo removes the latest note whatever colour it is in
        self.width, self.focus, self.hint = 5, 0, HINT_BOX
        self.items = [("Box tool (0): drag to choose the capture area", "tool", None)]
        self.items += [(f"{name} pen ({i + 1})", "tool", None) for i, (name, _) in enumerate(self.colors)]
        self.items += [(label, "action", action) for label, action in ACTIONS]

    # ---- tools / notes ----------------------------------------------------
    def pick(self, i):
        if i is not None and i >= len(self.colors):
            return
        self.sel = i
        self.focus = 0 if i is None else i + 1
        self.hint = HINT_BOX if i is None else f"Drawing in {self.colors[i][0]}  -  speak to add a note"

    def note_slot(self):
        return len(self.colors) if self.sel is None else self.sel

    def add_note(self, text):
        slot = self.note_slot()
        self.notes[slot].append(text)
        self.note_order.append(slot)
        self.talking = False

    def remove_last_note(self):
        """Take back the most recent note, in whichever colour it was spoken; None when there are none."""
        if not self.note_order:
            return None
        return self.notes[self.note_order.pop()].pop()

    def notes_for_save(self):
        names = [n for n, _ in self.colors] + [GENERAL[0]]
        return [{"color": names[i], "text": t} for i in range(len(names)) for t in self.notes[i]]

    def panel_title(self):
        return "Recording..." if self.talking else f"Notes -> {([n for n, _ in self.colors] + [GENERAL[0]])[self.note_slot()]}"

    def panel_rows(self):
        names = self.colors + [GENERAL]
        return [(names[i][0], names[i][1], list(self.notes[i])) for i in range(len(names)) if self.notes[i]]

    def panel_visible(self):
        return self.talking or any(self.notes)

    def cycle_size(self):
        names = [w for _, w in WIDTHS]
        label, self.width = WIDTHS[(names.index(self.width) + 1) % len(WIDTHS)] if self.width in names else WIDTHS[0]
        self.hint = f"Pen size: {label}"

    # ---- pointer ----------------------------------------------------------
    def press(self, x, y):
        if self.sel is None:
            self.drag, self.before = (x, y), self.rect
        else:
            self.cur = {"color": self.sel, "w": self.width, "pts": [(x, y)]}
            self.strokes.append(self.cur)
            self.history.append(("stroke", None))

    def move(self, x, y):
        """True when something changed and the canvas needs a repaint."""
        if self.sel is None and self.drag:
            x0, y0 = self.drag
            self.rect = (int(min(x0, x)), int(min(y0, y)), int(abs(x - x0)), int(abs(y - y0)))
        elif self.cur:
            self.cur["pts"].append((x, y))
        else:
            return False
        return True

    def release(self):
        if self.drag:
            self.drag = None
            if self.rect and self.rect != self.before and self.rect[2] > MIN_BOX and self.rect[3] > MIN_BOX:
                self.history.append(("rect", self.before))      # undo restores the previous box
            else:
                self.rect = self.before                         # a click or tiny drag changes nothing
        self.cur = None

    # ---- edits ------------------------------------------------------------
    def undo(self):
        if not self.history:
            return
        kind, old = self.history.pop()
        if kind == "rect":
            self.rect = old
        elif self.strokes:
            self.strokes.pop()

    def clear(self):
        self.strokes.clear()
        self.history = [h for h in self.history if h[0] == "rect"]

    def full_screen(self):
        if self.rect is not None:
            self.history.append(("rect", self.rect))
            self.rect = None

    # ---- toolbar keyboard navigation -------------------------------------
    def move_focus(self, step):
        self.focus = (self.focus + step) % len(self.items)
        label, kind, _ = self.items[self.focus]
        if kind == "tool":
            self.pick(None if self.focus == 0 else self.focus - 1)    # arrowing over a colour selects it
            return "select", self.sel
        self.hint = f"{label}  -  Enter to use"
        return "hint", None

    def activate_focus(self):
        _, kind, action = self.items[self.focus]
        return action if kind == "action" else None
