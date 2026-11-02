# Contributing

Thanks for helping! This is a small project; keep changes small and focused.

## Dev setup

```bash
sudo apt install xdotool libportaudio2
git clone https://github.com/anish-natekar/gguf-dictate.git && cd gguf-dictate
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/dictate-tray                           # run the app from source
```

## Before opening a PR

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest
```

CI runs the same two commands on Python 3.9-3.12 (Ubuntu) and a non-blocking Windows job. Qt tests run headless via `QT_QPA_PLATFORM=offscreen`.

Workflow for changes: write the failing test first, then the code. Keep GUI-free logic in `core/` with fakes for the mic, model, keys and clipboard.

## Layout

| Package | Role | Needs a display? |
| --- | --- | --- |
| `core/` | Pure logic: dictation state, recorder, paste-all, editor/overlay/settings models, lock | no |
| `platform/` | OS-specific adapters: mic (sounddevice), xdotool, notify-send, Qt clipboard/clock, pynput hotkeys | partly |
| `ui/` | Qt widgets: tray, settings, waveform overlay, snip editor, snip controller | yes (tests use `QT_QPA_PLATFORM=offscreen`) |
| `app.py` | Wires everything into one process (`dictate-tray`) | yes |

Put new logic in `core/` where you can, and add a test first. Qt code is tested headless with pytest-qt; hotkeys, the real mic
and clipboard timing are checked by hand, so say in the PR what you tried (distro, X11 session).

## Scope

Linux/X11 is the tested platform. Windows code paths exist (`pynput` keys, Qt toasts, `platformdirs` paths) but have never been run on
real hardware: test reports and fixes are the most useful contribution. Wayland and macOS would be welcome as separate, well-scoped PRs.
Please open an issue first for large changes.
