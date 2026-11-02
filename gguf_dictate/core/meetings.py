"""Meeting library: one folder per meeting plus a rebuildable SQLite full-text index (pure logic, no GUI)."""
import json
import re
import shutil
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from ..config import meetings_dir

META = "meeting.json"


class Meeting:
    """A meeting folder: meeting.json, mic.wav, system.wav, transcript.json, notes.md."""

    def __init__(self, directory, title, start, duration=0.0, status="recording"):
        self.dir, self.title, self.start, self.duration, self.status = directory, title, start, duration, status

    @property
    def id(self):
        return self.dir.name

    @property
    def mic_path(self):
        return self.dir / "mic.wav"

    @property
    def system_path(self):
        return self.dir / "system.wav"

    def meta(self):
        return {"title": self.title, "start": self.start.isoformat(), "duration": self.duration, "status": self.status}


def write_atomic(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)      # a crash can't leave a half-written file


class Library:
    """Folders are the source of truth; index.db only speeds up search and is rebuilt when missing."""

    def __init__(self, directory=None):
        self.dir = Path(directory or meetings_dir())
        self.dir.mkdir(parents=True, exist_ok=True)
        fresh = not (self.dir / "index.db").exists()
        self.lock = threading.RLock()      # the transcription thread writes while the UI reads
        self.db = sqlite3.connect(str(self.dir / "index.db"), check_same_thread=False)
        self.db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5(id UNINDEXED, title, notes, transcript)")
        if fresh:
            self.reindex()

    def close(self):
        with self.lock:
            self.db.close()

    def load(self, folder):
        try:
            m = json.loads((folder / META).read_text())
            return Meeting(folder, m["title"], datetime.fromisoformat(m["start"]), float(m.get("duration", 0)), m.get("status", "saved"))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):      # unreadable or not our JSON: skip the folder
            return None

    def all(self):
        found = (self.load(d) for d in self.dir.iterdir() if d.is_dir())
        return sorted((m for m in found if m), key=lambda m: m.start, reverse=True)

    def get(self, meeting_id):
        m = self.load(self.dir / meeting_id)
        if not m:
            raise KeyError(meeting_id)
        return m

    def create(self, start):
        base = start.strftime("%Y-%m-%d_%H%M")
        folder, n = self.dir / base, 1
        while folder.exists():
            n += 1
            folder = self.dir / f"{base}-{n}"
        folder.mkdir(parents=True)
        m = Meeting(folder, f"Meeting {start:%Y-%m-%d %H:%M}", start)
        self.save(m)
        return m

    def save(self, m):
        with self.lock:      # the transcription thread and the UI both write meeting.json
            write_atomic(m.dir / META, json.dumps(m.meta(), indent=2))
            self.index(m)

    def set_status(self, m, status):
        """Change only the status, on top of what is on disk, so a title edited meanwhile is not overwritten."""
        with self.lock:
            fresh = self.load(m.dir) or m
            fresh.status = status
            self.save(fresh)
            m.title, m.status = fresh.title, status

    def finish(self, m, duration):
        m.duration, m.status = duration, "saved"
        self.save(m)

    def set_title(self, m, title):
        m.title = title
        self.save(m)

    def notes(self, m):
        try:
            return (m.dir / "notes.md").read_text()
        except OSError:
            return ""

    def set_notes(self, m, text):
        write_atomic(m.dir / "notes.md", text)
        self.index(m)

    def transcript(self, m):
        try:
            return json.loads((m.dir / "transcript.json").read_text())
        except (OSError, ValueError):
            return []

    def set_transcript(self, m, segments):
        with self.lock:
            write_atomic(m.dir / "transcript.json", json.dumps(segments))
            self.set_status(m, "transcribed")

    def unfinished(self):
        return [m for m in self.all() if m.status == "recording"]

    def delete(self, m):
        with self.lock:
            shutil.rmtree(m.dir, ignore_errors=True)
            self.db.execute("DELETE FROM docs WHERE id = ?", (m.id,))
            self.db.commit()

    def on_day(self, day):
        return [m for m in self.all() if m.start.date() == day]

    def days_with_meetings(self, year, month):
        return {m.start.day for m in self.all() if (m.start.year, m.start.month) == (year, month)}

    def index(self, m):
        text = " ".join(s["text"] for s in self.transcript(m))
        with self.lock:
            self.db.execute("DELETE FROM docs WHERE id = ?", (m.id,))
            self.db.execute("INSERT INTO docs (id, title, notes, transcript) VALUES (?, ?, ?, ?)", (m.id, m.title, self.notes(m), text))
            self.db.commit()

    def reindex(self):
        with self.lock:
            self.db.execute("DELETE FROM docs")
        for m in self.all():
            self.index(m)

    def search(self, query):
        """Whole words and word prefixes, any order; punctuation in the query is ignored so it can never be a syntax error."""
        words = re.findall(r"\w+", query)
        if not words:
            return []
        match = " ".join(f'"{w}"*' for w in words)
        with self.lock:
            ids = {row[0] for row in self.db.execute("SELECT id FROM docs WHERE docs MATCH ?", (match,))}
        return [m for m in self.all() if m.id in ids]
