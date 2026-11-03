# Changelog

## Unreleased
- Meeting recorder: floating, draggable pill that appears ready (record button), then shows time, pause and save; mic and system audio saved as two tracks (system audio on Linux via PipeWire).
- Meetings window from the tray: month calendar, day list, full-text search, notes, and an on-demand "Generate transcript" labelled Me / Them.
- New `meeting_hotkey` setting (default `f8`); interrupted recordings are recovered on the next start.
- Dictation and meeting transcription share one model session safely.
- GNOME Wayland support for dictation and meetings: hotkeys read through evdev (add yourself to the `input` group and log in again), text pasted via `wl-copy` plus Ctrl+V sent through mutter RemoteDesktop, and the UI runs through XWayland so the overlay and pill stay positioned. The session is detected automatically; X11 is unchanged. Snip captures through the xdg-desktop-portal Screenshot API and crops the monitor under the cursor.

## 0.3.0
- UI ported from GTK to Qt (PySide6); one process instead of tray + dictation subprocess. No system GTK packages needed.
- Microphone via sounddevice (`libportaudio2`) instead of `arecord`.
- Config/data paths via platformdirs; single-instance lock; `dictate` and `dictate-tray` are now the same app.
- Windows code paths (pynput typing/paste, Qt toasts, platformdirs runtime dir); not yet tested on real hardware. CI has a non-blocking Windows job.
- Removed the unused editor flag file; README now has a support/tested matrix and per-OS setup.
- Logic split into `core/` (tested without a GUI) and `platform/` adapters; test suite grew from 26 to 245 tests.

## 0.2.0
- Package layout (`gguf_dictate`), `dictate` and `dictate-tray` commands, pipx install.
- Snip editor: box/pen tools, per-colour voice notes, queue, paste-all (`Ctrl+Alt+V`), latest-snip `Ctrl+V`.
- Waveform/spinner overlay, tray settings, blue capture-box frame, arrow-key toolbar.
- Runtime files moved from `/tmp` to a private per-user directory; config writes are atomic.
- Tests, lint and CI.
