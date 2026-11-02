"""Geometry and formatting for the meeting recording pill (pure logic, no GUI). A screen is (left, top, right, bottom)."""

MARGIN = 16        # gap kept between the pill and a screen edge it snaps to
SNAP_DIST = 48     # how close to an edge a drop has to be to snap


def format_elapsed(seconds):
    s = max(0, int(seconds))
    hours, rest = divmod(s, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def clamp(x, y, w, h, screen):
    left, top, right, bottom = screen
    return max(left, min(x, right - w)), max(top, min(y, bottom - h))


def snap(x, y, w, h, screen, margin=MARGIN, dist=SNAP_DIST):
    """Pull each axis to the nearest screen edge (plus margin) when dropped within `dist` of it, so corners are easy to hit."""
    left, top, right, bottom = screen

    def axis(pos, size, lo, hi):
        if abs(pos - (lo + margin)) <= dist:
            return lo + margin
        if abs(pos + size - (hi - margin)) <= dist:
            return hi - margin - size
        return pos

    return axis(x, w, left, right), axis(y, h, top, bottom)
