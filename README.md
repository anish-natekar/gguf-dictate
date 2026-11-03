# gguf-dictate

Hold a hotkey, talk, release: the transcription is typed into whatever window is focused.
A small, fully local push-to-talk dictation tool that runs **any speech-to-text GGUF model** (Parakeet, Whisper, ...)
through [transcribe.cpp](https://github.com/handy-computer/transcribe.cpp). It also has a **snip tool**: freeze the screen, draw on it in
several colours, add a voice note per colour, queue several snips and paste them all into a chatbot in one go.

> **Status: early.** Linux (Ubuntu GNOME, X11) is tested. Windows is implemented but **not yet tested on real hardware**; see [Support](#support).

## What it does

- **Push-to-talk dictation** into any text box: hold the hotkey, speak, release.
- **Bring your own model**: pick any `.gguf` in Settings. The path is remembered.
- **Fast**: the model stays loaded on the GPU (Vulkan, CPU fallback); a short phrase transcribes in tens of milliseconds once warm.
- **Meeting recorder**: record a call (your mic and the system audio), keep it in a calendar library, and make a transcript when you want one.
- **Snip + annotate + voice notes**: for showing a chatbot exactly what is wrong in a UI, image, video frame or 3D view.
- **Private**: everything runs on your machine; no network access after install.
- **Hackable**: pure Python (Qt UI), logic separated from the GUI and covered by tests.

Not supported: macOS, other Wayland desktops than GNOME, streaming/partial results, live meeting transcription, text post-processing.

## Support

| | Linux (X11) | Windows 10/11 | macOS | Linux (Wayland) |
| --- | --- | --- | --- | --- |
| Status | **Supported, tested** | Implemented, **untested** | Not supported | **GNOME supported, tested** |
| Tested on | Ubuntu 24.04 GNOME X11, NVIDIA RTX 3050 + AMD iGPU via Vulkan, Python 3.12 | CI runs the unit tests only; never run by hand | | Ubuntu 24.04 GNOME (Wayland session) |
| Dictation typing | `xdotool` | `pynput` | | `wl-copy` + Ctrl+V sent through mutter RemoteDesktop |
| Hotkeys | `pynput` | `pynput` | | evdev (`input` group) |
| Snip capture | Qt screen grab | Qt screen grab | | xdg-desktop-portal Screenshot |
| Microphone | PortAudio (`libportaudio2`) | PortAudio (bundled in the `sounddevice` wheel) | | |
| Tray | GNOME needs the AppIndicator extension (stock on Ubuntu) | system tray | | |
| GPU | Vulkan (works), CPU fallback | unverified: check the `transcribe-cpp` log line for the backend | | |

**What the automated tests cover** (about 250, headless, run on every push): dictation state machine, recorder pre-roll, paste-all sequencing
with fake clipboard/keys, editor behaviour, overlay animation, settings validation, config/queue/lock, the Qt widgets (offscreen), and
an end-to-end run with a fake mic and model.
**What only a human can check** (done on Linux, to do on Windows): real hotkeys, real microphone, GPU backend, transparent click-through overlay,
fullscreen editor, clipboard paste timing in a browser chat box.

Windows testers are very welcome: please open an issue with what worked and what didn't.

## Install

Needs Python 3.9 or newer. The UI is Qt (PySide6), installed by pip; no GTK or system UI packages are needed.

### Linux (Ubuntu / Debian, X11 or GNOME Wayland)

```bash
sudo apt install xdotool libportaudio2 pipx
pipx install git+https://github.com/anish-natekar/gguf-dictate.git
dictate-tray --install-desktop --autostart    # optional: app-menu launcher + start at login
dictate-tray                                  # first run opens Settings: pick your .gguf
```

The session type (X11 or Wayland) is detected automatically. On **GNOME Wayland** also install `wl-clipboard` (`sudo apt install wl-clipboard`)
and add yourself to the `input` group so hotkeys work, then log in again:

```bash
sudo usermod -aG input $USER
```

The `input` group lets any program you run read raw keyboard events, which is how every Wayland dictation tool gets global hotkeys
(GNOME has no global-shortcut API yet). Without it dictate says so and does not start. On Wayland the UI runs through XWayland so the
overlay and meeting pill can position themselves. The first screenshot may ask for permission. Other Wayland desktops (KDE, Sway) are untested.
On GNOME the tray icon needs the
AppIndicator extension (`gnome-shell-extension-appindicator`, enabled by default on Ubuntu). Other distros: install `xdotool`,
PortAudio and `notify-send` (libnotify) with your package manager.

### Windows 10/11 (experimental)

In PowerShell, with Python from [python.org](https://www.python.org/downloads/) (tick "Add python.exe to PATH"):

```powershell
py -m pip install --user pipx
py -m pipx ensurepath          # then open a new terminal
pipx install git+https://github.com/anish-natekar/gguf-dictate.git
dictate-tray                   # first run opens Settings: pick your .gguf
```

Keys are injected with `pynput`. `--install-desktop` / `--autostart` only write Linux `.desktop` files; on Windows put a shortcut to
`dictate-tray.exe` in `shell:startup` instead. Config lives in `%LOCALAPPDATA%\dictate`.

### From source (any OS)

```bash
git clone https://github.com/anish-natekar/gguf-dictate.git && cd gguf-dictate
python3 -m venv .venv                      # Windows: py -m venv .venv
.venv/bin/pip install -e ".[dev]"          # Windows: .venv\Scripts\pip install -e ".[dev]"
.venv/bin/dictate-tray                     # Windows: .venv\Scripts\dictate-tray
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for tests and project layout.

## Get a model

Any speech-to-text GGUF supported by transcribe.cpp works. Examples:

- Parakeet TDT 0.6B v3 and others under [`handy-computer` on Hugging Face](https://huggingface.co/handy-computer)
- [Underdog Bark 3.0 Plus (unofficial Q8_0 GGUF)](https://huggingface.co/joshthomasdev/underdog-bark-3.0-plus-gguf) — Parakeet-based English model, ~740 MB, CC-BY-4.0 (see the model's own page for attribution terms)

Models are not included in this repo.

## Run

```bash
dictate-tray                                   # from source: .venv/bin/dictate-tray
dictate-tray --model /path/to/model.gguf       # set the model from the command line (remembered)
```

One process: a tray icon, the waveform pill, the snip editor and dictation. The first run opens **Settings**; pick a `.gguf`.
When the menu says **Ready**, click into any text box, **hold `f9`**, talk, and release.
Settings are saved in `~/.config/dictate/config.json` (Windows: `%LOCALAPPDATA%\dictate\config.json`).

Settings has the model, the hold-to-talk hotkey (e.g. `f9`, `ctrl+shift+space`, `ctrl_r`), the snip and paste-all hotkeys,
snip colours, "open the mic only while the key is held" (adds ~100 ms, avoids the always-on mic indicator) and "no space after each phrase".

## Tray icon

Adds a microphone icon to the top bar / system tray. The menu has
Start/Stop, **Model** (choose a `.gguf`, or pick a recent one), snip actions, **Open meeting recorder**, **Meetings...**, **Settings**, **How to use / shortcuts**, and **About**.

The app also shows a click-through, transparent **waveform pill** at the bottom of the screen: bars move with your
voice while the key is held, then a spinner loops while the model transcribes.

## Snip + annotate + voice notes (for bug reports to chatbots)

Press **`ctrl+alt+s`** (or tray menu -> Take snip). The screen freezes and a toolbar appears:

| Control | Action |
| --- | --- |
| **Box** (`0`, default) | No colour selected: drag to choose the capture area. Drag again to redo it. |
| **Colours** (`1`-`5`) | Pen in that colour. Draw on the shot. Colours are editable in Settings. |
| **Speak** / hold the dictate key | Voice note, saved under the selected colour's heading (**General** if none). |
| **Full screen** (`F`) | Capture the whole screen. |
| **Undo** (`Ctrl+Z`) | Undoes strokes and box changes, in order. |
| **Undo note** (`Backspace`) | Removes the most recent voice note, whichever colour it is under. Repeat to remove earlier ones. |
| **Clear pen**, **Save** (`Ctrl+Enter`), **Cancel** (`Esc`) | |
| **Arrow keys** | Move along the bottom toolbar. Colours select as you pass them; `Enter` activates the focused button. |

The capture area is outlined in blue with a size badge (`900 x 450`). With no box, a blue frame and a
"Full screen" badge mark the whole screen. `Esc` closes the editor even if it lost keyboard focus.

Saving a snip also puts it on the clipboard: **`Ctrl+V`** pastes the latest snip's image, then its notes follow automatically.
The editor shows a `Queue: N saved` badge and a toast confirms each save.

Saved snips go into a queue (`~/.local/share/dictate/queue`). Click into a chatbot box and press **`ctrl+alt+v`**:
every queued image is pasted in order, each followed by its notes (`## Red` / `- note`), then the queue is cleared.
The paste fires when you release the keys, so hold-and-release the combo once.
Hotkeys and colours are in Settings.

## Meeting recorder

Records a meeting to disk, then turns it into a transcript when you ask. Nothing is transcribed live.

- Press the hotkey (default `F8`, changeable in Settings) or pick **Open meeting recorder** in the tray. A small **recorder pill**
  appears on top of everything. Nothing is recorded yet: press its red **record** button to start. The hotkey works while the model is loaded; the tray always works.
- While recording the pill shows a blinking dot, the elapsed time, **pause** and **save**. Drag it anywhere; it snaps to the corners
  and remembers where you left it. The **X** closes the pill (while recording it asks, then discards the audio). Once recording, the hotkey does nothing, so the pill cannot disappear by accident: save from the pill. Before recording, the hotkey again dismisses the pill.
- Two tracks are saved: your **microphone** ("Me") and the **system audio** ("Them": the other people on the call). Linux needs
  PipeWire (`wpctl` and `pw-record`: `sudo apt install wireplumber pipewire-bin`). Where system audio cannot be captured, the meeting
  records the mic alone and says so.
- **Tray > Meetings...** opens a month calendar (days with meetings are marked), the day's list, full-text search across titles,
  notes and transcripts, editable title and notes, and **Generate transcript**. Transcripts are labelled Me / Them with timestamps and can be copied as Markdown.
- Each meeting is a folder, `YYYY-MM-DD_HHMM`, in your user data directory (`meetings/`): `mic.wav`, `system.wav`, `meeting.json`,
  `transcript.json`, `notes.md`. The search index is rebuilt from the folders if it is lost. A crash or power cut leaves a playable
  recording that is recovered on the next start.

Tips and limits: use headphones, otherwise your mic also picks up the other side from your speakers and they appear twice.
Speakers inside the system track are not told apart ("Them" is everyone else). The system audio source is the default output when the
meeting starts; switching output devices mid-meeting ends that track. **Tell people you are recording**: consent rules differ by place.

## How it works

1. PortAudio (`sounddevice`) streams 16 kHz mono audio; a rolling 0.25 s buffer keeps the first syllable from being clipped.
2. [`pynput`](https://pypi.org/project/pynput/) watches for the hotkey (it observes keys, it does not grab them).
3. On release, the audio goes to transcribe.cpp (`transcribe-cpp` on PyPI, bundled CPU + Vulkan).
4. The result is typed into the focused window (`xdotool` on X11, mutter RemoteDesktop on Wayland, `pynput` elsewhere).

## Notes

- By default the microphone stays open while the program runs (that is what makes it fast). Turn on "open the mic only while the key is held" in Settings if that bothers you.
- Linux: X11 and GNOME Wayland are supported (see Install). Other Wayland compositors are untested.
- The first GPU run compiles shaders, so startup includes a warm-up pass.
- The queue and log are plain local files; see [SECURITY.md](SECURITY.md).

## Contributing

Issues and PRs are welcome, especially Windows test reports and a macOS port. Read [CONTRIBUTING.md](CONTRIBUTING.md) first.

## License

MIT for this code. transcribe.cpp and each model have their own licenses.
