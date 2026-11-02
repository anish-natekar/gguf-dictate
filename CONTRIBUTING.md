# Contributing

Thanks for helping! This is a small project; keep changes small and focused.

## Dev setup

```bash
sudo apt install xdotool alsa-utils python3-gi python3-gi-cairo gir1.2-ayatanaappindicator3-0.1
git clone https://github.com/anish-natekar/gguf-dictate.git && cd gguf-dictate
python3 -m venv --system-site-packages .venv      # system site packages = GTK bindings
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m gguf_dictate.tray             # run the tray from source
```

## Before opening a PR

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest
```

CI runs the same two commands on Python 3.9-3.12.

## Layout

| Module | Role | Needs a display? |
| --- | --- | --- |
| `hotkeys.py`, `config.py`, `notes.py`, `ipc.py` | Pure logic, unit tested | no |
| `dictate.py` | Mic, hotkeys, transcription, typing (one process) | no (X11 for keys) |
| `tray.py`, `overlay.py`, `snip.py` | GTK tray, waveform, snip editor (one process) | yes |

The two processes talk over abstract unix datagram sockets (`ipc.py`).
Put new logic in the pure modules where you can, and add a test. GUI code is checked by hand: please say
in the PR what you tried (distro, X11 session).

## Scope

X11 on Linux only for now. Wayland/Windows/macOS support would be welcome as separate, well-scoped PRs.
Please open an issue first for large changes.
