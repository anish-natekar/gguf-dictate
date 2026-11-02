import json
from datetime import date, datetime

import pytest

from gguf_dictate.core.meetings import Library

T = datetime(2026, 11, 3, 14, 30, 5)


def seg(text, speaker="Them", t0=0.0):
    return {"t0": t0, "t1": t0 + 2, "speaker": speaker, "text": text}


def test_create_names_folder_by_start_date_and_time(tmp_path):
    m = Library(tmp_path).create(T)
    assert m.dir.name == "2026-11-03_1430"
    assert m.title == "Meeting 2026-11-03 14:30"
    assert m.status == "recording" and m.start == T


def test_create_in_same_minute_gets_a_distinct_folder(tmp_path):
    lib = Library(tmp_path)
    a, b = lib.create(T), lib.create(T)
    assert a.dir != b.dir and b.dir.name == "2026-11-03_1430-2"


def test_meta_is_persisted_and_reloaded(tmp_path):
    lib = Library(tmp_path)
    m = lib.create(T)
    lib.finish(m, 61.5)
    again = Library(tmp_path).get(m.id)
    assert again.status == "saved" and again.duration == 61.5 and again.start == T


def test_list_day_and_month_newest_first(tmp_path):
    lib = Library(tmp_path)
    a = lib.create(datetime(2026, 11, 3, 9, 0))
    b = lib.create(datetime(2026, 11, 3, 15, 0))
    lib.create(datetime(2026, 11, 20, 10, 0))
    lib.create(datetime(2026, 12, 1, 10, 0))
    assert [m.id for m in lib.on_day(date(2026, 11, 3))] == [b.id, a.id]
    assert lib.days_with_meetings(2026, 11) == {3, 20}


def test_search_finds_title_notes_and_transcript(tmp_path):
    lib = Library(tmp_path)
    a, b, c = lib.create(T), lib.create(datetime(2026, 11, 4, 9, 0)), lib.create(datetime(2026, 11, 5, 9, 0))
    lib.set_title(a, "Budget review")
    lib.set_notes(b, "talk about the roadmap")
    lib.set_transcript(c, [seg("we need a hiring plan")])
    assert [m.id for m in lib.search("budget")] == [a.id]
    assert [m.id for m in lib.search("roadmap")] == [b.id]
    assert [m.id for m in lib.search("hiring")] == [c.id]
    assert lib.search("nothing-matches") == []


def test_search_matches_prefix_and_survives_odd_input(tmp_path):
    lib = Library(tmp_path)
    m = lib.create(T)
    lib.set_transcript(m, [seg("quarterly planning")])
    assert [x.id for x in lib.search("plann")] == [m.id]
    for q in ['"', "a AND", "(", "*", "x:y", ""]:
        assert isinstance(lib.search(q), list)


def test_set_transcript_updates_status_and_roundtrips(tmp_path):
    lib = Library(tmp_path)
    m = lib.create(T)
    lib.finish(m, 10)
    lib.set_transcript(m, [seg("hello", "Me", 0), seg("hi", "Them", 2)])
    assert lib.get(m.id).status == "transcribed"
    assert [s["text"] for s in lib.transcript(m)] == ["hello", "hi"]
    assert lib.transcript(lib.create(datetime(2026, 11, 9, 9, 0))) == []


def test_replacing_text_removes_old_hits(tmp_path):
    lib = Library(tmp_path)
    m = lib.create(T)
    lib.set_notes(m, "alpha")
    lib.set_notes(m, "beta")
    assert lib.search("alpha") == [] and [x.id for x in lib.search("beta")] == [m.id]


def test_rebuild_index_from_folders_after_db_loss(tmp_path):
    lib = Library(tmp_path)
    m = lib.create(T)
    lib.set_transcript(m, [seg("rebuild me")])
    lib.close()
    (tmp_path / "index.db").unlink()
    fresh = Library(tmp_path)
    assert [x.id for x in fresh.search("rebuild")] == [m.id]


def test_delete_removes_folder_and_index_entry(tmp_path):
    lib = Library(tmp_path)
    m = lib.create(T)
    lib.set_notes(m, "gone soon")
    lib.delete(m)
    assert not m.dir.exists() and lib.search("gone") == [] and lib.all() == []


def test_unfinished_recordings_are_listed_for_recovery(tmp_path):
    lib = Library(tmp_path)
    a, b = lib.create(T), lib.create(datetime(2026, 11, 4, 9, 0))
    lib.finish(b, 5)
    assert [m.id for m in lib.unfinished()] == [a.id]


def test_corrupt_meta_is_skipped_not_fatal(tmp_path):
    lib = Library(tmp_path)
    good = lib.create(T)
    bad = lib.create(datetime(2026, 11, 4, 9, 0))
    (bad.dir / "meeting.json").write_text("{nope")
    assert [m.id for m in Library(tmp_path).all()] == [good.id]


def test_unknown_id_raises(tmp_path):
    with pytest.raises(KeyError):
        Library(tmp_path).get("nope")


def test_audio_paths_live_in_the_meeting_folder(tmp_path):
    m = Library(tmp_path).create(T)
    assert m.mic_path == m.dir / "mic.wav" and m.system_path == m.dir / "system.wav"
    assert json.loads((m.dir / "meeting.json").read_text())["status"] == "recording"


def test_library_accepts_a_string_path(tmp_path):
    assert Library(str(tmp_path / "x")).all() == []


def test_set_status_does_not_overwrite_a_title_edited_meanwhile(tmp_path):
    lib = Library(tmp_path)
    stale = lib.create(datetime(2026, 11, 3, 9, 0))
    lib.set_title(lib.get(stale.id), "Renamed while transcribing")
    lib.set_transcript(stale, [{"t0": 0, "t1": 1, "speaker": "Me", "text": "hi"}])
    assert lib.get(stale.id).title == "Renamed while transcribing" and lib.get(stale.id).status == "transcribed"
    assert stale.title == "Renamed while transcribing"


def test_a_meeting_json_of_the_wrong_shape_is_skipped(tmp_path):
    lib = Library(tmp_path)
    (tmp_path / "junk").mkdir()
    (tmp_path / "junk" / "meeting.json").write_text("[1, 2]")
    assert lib.all() == []
