# Changelog

## 0.3.0
- UI ported from GTK to Qt (PySide6); one process instead of tray + dictation subprocess. No system GTK packages needed.
- Microphone via sounddevice (`libportaudio2`) instead of `arecord`.
- Config/data paths via platformdirs; single-instance lock; `dictate` and `dictate-tray` are now the same app.
- Logic split into `core/` (tested without a GUI) and `platform/` adapters; test suite grew from 26 to 245 tests.

## 0.2.0
- Package layout (`gguf_dictate`), `dictate` and `dictate-tray` commands, pipx install.
- Snip editor: box/pen tools, per-colour voice notes, queue, paste-all (`Ctrl+Alt+V`), latest-snip `Ctrl+V`.
- Waveform/spinner overlay, tray settings, blue capture-box frame, arrow-key toolbar.
- Runtime files moved from `/tmp` to a private per-user directory; config writes are atomic.
- Tests, lint and CI.
