from datetime import datetime

from gguf_dictate.core.meeting_view import export_markdown, format_transcript, row_text, status_label
from gguf_dictate.core.meetings import Meeting

M = Meeting(None, "Budget review", datetime(2026, 11, 3, 14, 30), 3725.0, "transcribed")
SEGS = [
    {"t0": 0.0, "t1": 4.0, "speaker": "Me", "text": "Shall we begin?"},
    {"t0": 65.4, "t1": 70.0, "speaker": "Them", "text": "Yes, go ahead."},
]


def test_status_labels_are_plain_words():
    assert status_label("saved") == "not transcribed"
    assert status_label("transcribing") == "transcribing..."
    assert status_label("transcribed") == "transcribed"
    assert status_label("recording") == "interrupted"
    assert status_label("anything else") == "anything else"


def test_row_text_has_time_title_length_and_status():
    assert row_text(M) == "14:30   Budget review   1:02:05   transcribed"


def test_format_transcript_has_timestamp_and_speaker_per_line():
    assert format_transcript(SEGS) == "[0:00] Me: Shall we begin?\n[1:05] Them: Yes, go ahead."
    assert format_transcript([]) == ""


def test_export_markdown_has_title_date_notes_and_transcript():
    md = export_markdown(M, "Decide the budget.", SEGS)
    assert md.startswith("# Budget review\n\n*2026-11-03 14:30, 1:02:05*")
    assert "## Notes\n\nDecide the budget." in md
    assert "## Transcript\n\n**Me** [0:00] Shall we begin?\n\n**Them** [1:05] Yes, go ahead." in md


def test_export_markdown_skips_empty_sections():
    md = export_markdown(M, "  ", [])
    assert "## Notes" not in md and "## Transcript" not in md
    assert md.rstrip().endswith("1:02:05*")
