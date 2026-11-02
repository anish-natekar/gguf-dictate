"""Text shown for meetings in the library window and copied out of it (pure logic, no GUI)."""
from .pill_model import format_elapsed

STATUS = {"saved": "not transcribed", "transcribing": "transcribing...", "transcribed": "transcribed", "recording": "interrupted"}


def status_label(status):
    return STATUS.get(status, status)


def row_text(m):
    return f"{m.start:%H:%M}   {m.title}   {format_elapsed(m.duration)}   {status_label(m.status)}"


def format_transcript(segments):
    return "\n".join(f"[{format_elapsed(s['t0'])}] {s['speaker']}: {s['text']}" for s in segments)


def export_markdown(m, notes, segments):
    out = [f"# {m.title}", f"*{m.start:%Y-%m-%d %H:%M}, {format_elapsed(m.duration)}*"]
    if notes.strip():
        out.append(f"## Notes\n\n{notes.strip()}")
    if segments:
        lines = "\n\n".join(f"**{s['speaker']}** [{format_elapsed(s['t0'])}] {s['text']}" for s in segments)
        out.append(f"## Transcript\n\n{lines}")
    return "\n\n".join(out) + "\n"
