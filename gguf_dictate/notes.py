"""Snip queue on disk and the text format for notes (pure logic, no GTK)."""
import json
import time

from .config import QUEUE_DIR


def format_notes(n, notes):
    """'Screenshot 2' + one '## Colour' heading per colour that has notes."""
    out, seen = [], []
    for note in notes:
        if note["color"] not in seen:
            seen.append(note["color"])
    for color in seen:
        out.append(f"## {color}\n" + "\n".join(f"- {x['text']}" for x in notes if x["color"] == color))
    return f"\nScreenshot {n}\n\n" + "\n\n".join(out) if out else ""


class Queue:
    """Saved snips: <ns>.png plus <ns>.json (the notes), oldest first."""

    def __init__(self, directory=None):
        self.dir = directory or QUEUE_DIR
        self.dir.mkdir(parents=True, exist_ok=True)

    def items(self):
        out = []
        for png in sorted(self.dir.glob("*.png")):
            try:
                out.append((png, json.loads(png.with_suffix(".json").read_text())))
            except (OSError, ValueError):
                out.append((png, []))
        return out

    def add(self, surface, notes):
        """surface: anything with write_to_png(path) (a cairo.ImageSurface)."""
        base = self.dir / str(time.time_ns())
        base.with_suffix(".json").write_text(json.dumps(notes))
        surface.write_to_png(str(base.with_suffix(".png")))      # the png appears last, so items() never sees a half snip

    def clear(self):
        for f in list(self.dir.glob("*.png")) + list(self.dir.glob("*.json")):
            f.unlink(missing_ok=True)
