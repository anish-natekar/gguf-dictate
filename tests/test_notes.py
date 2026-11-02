from gguf_dictate.notes import Queue, format_notes


class FakeSurface:
    def write_to_png(self, path):
        open(path, "wb").write(b"png")


def test_format_notes_groups_by_color_in_first_seen_order():
    notes = [{"color": "Red", "text": "a"}, {"color": "Blue", "text": "b"}, {"color": "Red", "text": "c"}]
    assert format_notes(2, notes) == "\nScreenshot 2\n\n## Red\n- a\n- c\n\n## Blue\n- b"


def test_format_notes_starts_on_new_line_and_is_empty_without_notes():
    assert format_notes(1, [{"color": "General", "text": "x"}]).startswith("\nScreenshot 1")
    assert format_notes(1, []) == ""


def test_queue_roundtrip_order_and_clear(tmp_path):
    q = Queue(tmp_path)
    q.add(FakeSurface(), [{"color": "Red", "text": "first"}])
    q.add(FakeSurface(), [])
    items = q.items()
    assert [n for _, n in items] == [[{"color": "Red", "text": "first"}], []]
    q.clear()
    assert q.items() == [] and list(tmp_path.iterdir()) == []


def test_queue_survives_corrupt_notes(tmp_path):
    q = Queue(tmp_path)
    q.add(FakeSurface(), [])
    next(tmp_path.glob("*.json")).write_text("{not json")
    assert [n for _, n in q.items()] == [[]]
