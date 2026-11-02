"""Waveform / spinner animation state for the overlay pill (no toolkit)."""
import colorsys
import math
from collections import deque

BARS = 16
REC_W = 124
BUSY_W = 44
PILL_H = 28
EXTRA_MESSAGES = {"snip", "paste", "cancel", "ctrlv", "note", "meeting"}
NOISE_FLOOR = 0.004
REF_INIT = 0.03
REF_MIN = 0.02
REF_DECAY = 0.985
EASE = 0.25
ATTACK = 0.85
RELEASE = 0.35
PHASE_STEP = 0.033


def aurora(t):
    """Drifting teal-to-violet colour for t in [0, 1); periodic."""
    hue = 0.50 + 0.38 * (0.5 - 0.5 * math.cos(2 * math.pi * t))
    return colorsys.hsv_to_rgb(hue, 0.62, 1.0)


class OverlayModel:
    def __init__(self):
        self.state = "idle"
        self.hist = deque([0.0] * BARS, maxlen=BARS)
        self.disp = [0.0] * BARS
        self.ref = REF_INIT
        self.alpha = 0.0
        self.pill_w = float(BUSY_W)
        self.phase = 0.0

    def handle(self, msg):
        """Apply a message. Returns ("extra", msg), ("animate", None) or None."""
        kind, _, arg = msg.partition(" ")
        if kind in EXTRA_MESSAGES:
            return ("extra", msg)
        if kind == "rec":
            self.state = "rec"
            self.hist = deque([0.0] * BARS, maxlen=BARS)
            self.ref = REF_INIT
            return ("animate", None)
        if kind == "lvl":
            try:
                v = float(arg)
            except ValueError:
                return None
            woke = self.state != "rec"
            self.state = "rec"
            self.ref = max(self.ref * REF_DECAY, v, REF_MIN)
            self.hist.append(0.0 if v < NOISE_FLOOR else min(1.0, v / self.ref))
            return ("animate", None) if woke else None
        if kind == "busy":
            self.state = "busy"
            return ("animate", None)
        if kind == "idle":
            self.state = "idle"
        return None

    def tick(self):
        """Advance one frame. True while the timer should keep running."""
        active = self.state != "idle"
        self.alpha += ((1.0 if active else 0.0) - self.alpha) * EASE
        if not active and self.alpha < 0.01:
            self.alpha = 0.0
        target_w = REC_W if self.state == "rec" else BUSY_W
        self.pill_w += (target_w - self.pill_w) * EASE
        for i, h in enumerate(self.hist):
            self.disp[i] += (h - self.disp[i]) * (ATTACK if h > self.disp[i] else RELEASE)
        self.phase = (self.phase + PHASE_STEP) % 1.0
        return active or self.alpha > 0.0
