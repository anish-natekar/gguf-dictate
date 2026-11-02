"""Behaviour of notes/Queue that the Qt port must preserve (the editor and paste-all depend on it)."""
import json

from gguf_dictate.notes import Queue, format_notes


class FakeSurface:
    def __init__(self, data=b"png"):
        self.data = data

    def write_to_png(self, path):
        with open(path, "wb") as f:
            f.write(self.data)


def test_format_notes_multiple_colors_and_notes_exact():
    notes = [
        {"color": "General", "text": "overall"},
        {"color": "Red", "text": "one"},
        {"color": "Blue", "text": "two"},
        {"color": "Red", "text": "three"},
    ]
    assert format_notes(3, notes) == "\nScreenshot 3\n\n## General\n- overall\n\n## Red\n- one\n- three\n\n## Blue\n- two"


def test_format_notes_keeps_unicode_and_multiline_text_verbatim():
    out = format_notes(1, [{"color": "Red", "text": "naïve → 例"}])
    assert out.endswith("- naïve → 例")


def test_queue_creates_missing_directory(tmp_path):
    d = tmp_path / "a" / "b"
    Queue(d)
    assert d.is_dir()


def test_queue_items_are_oldest_first(tmp_path):
    q = Queue(tmp_path)
    for i in range(5):
        q.add(FakeSurface(), [{"color": "Red", "text": str(i)}])
    assert [n[0]["text"] for _, n in q.items()] == ["0", "1", "2", "3", "4"]


def test_queue_png_holds_surface_bytes_and_json_holds_notes(tmp_path):
    q = Queue(tmp_path)
    notes = [{"color": "Red", "text": "x"}]
    q.add(FakeSurface(b"\x89PNGdata"), notes)
    (png, got), = q.items()
    assert png.read_bytes() == b"\x89PNGdata"
    assert got == notes
    assert json.loads(png.with_suffix(".json").read_text()) == notes


def test_queue_ignores_json_without_png(tmp_path):
    """A half-written snip (json first, png last) must never show up."""
    q = Queue(tmp_path)
    (tmp_path / "123.json").write_text("[]")
    assert q.items() == []


def test_queue_png_without_json_has_empty_notes(tmp_path):
    q = Queue(tmp_path)
    (tmp_path / "123.png").write_bytes(b"x")
    assert [n for _, n in q.items()] == [[]]


def test_queue_clear_is_idempotent_and_keeps_directory(tmp_path):
    q = Queue(tmp_path)
    q.clear()
    q.add(FakeSurface(), [])
    q.clear()
    q.clear()
    assert tmp_path.is_dir() and q.items() == []


def test_queue_keeps_order_and_every_item_even_with_a_coarse_clock(tmp_path, monkeypatch):
    """Windows' clock ticks every ~15 ms: identical timestamps must not overwrite or reorder snips."""
    monkeypatch.setattr("gguf_dictate.notes.time.time_ns", lambda: 1_000_000)
    q = Queue(tmp_path)
    for i in range(5):
        q.add(FakeSurface(), [{"color": "Red", "text": str(i)}])
    assert [n[0]["text"] for _, n in q.items()] == ["0", "1", "2", "3", "4"]
    assert len(list(tmp_path.glob("*.png"))) == 5


def test_a_new_queue_object_continues_after_existing_snips(tmp_path, monkeypatch):
    monkeypatch.setattr("gguf_dictate.notes.time.time_ns", lambda: 5)
    Queue(tmp_path).add(FakeSurface(), [{"color": "Red", "text": "old"}])
    Queue(tmp_path).add(FakeSurface(), [{"color": "Red", "text": "new"}])
    assert [n[0]["text"] for _, n in Queue(tmp_path).items()] == ["old", "new"]
