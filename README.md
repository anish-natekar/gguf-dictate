# gguf-dictate

Hold a hotkey, talk, release — the transcription is typed into whatever window is focused.
A tiny (~130 lines), single-file, fully local push-to-talk dictation tool for Linux/X11 that runs
**any speech-to-text GGUF model** (Parakeet, Whisper, ...) through [transcribe.cpp](https://github.com/handy-computer/transcribe.cpp).

> **Status: early / experimental.** Model loading, transcription and mic capture are tested.
> Only tested on Ubuntu (GNOME, X11) with an NVIDIA laptop GPU via Vulkan.

## What it does

- **Push-to-talk dictation** into any text box: hold the hotkey, speak, release.
- **Bring your own model**: point `--model` at any `.gguf` file. The path is remembered.
- **Fast**: the model stays loaded on the GPU (Vulkan, CPU fallback); a short phrase transcribes in tens of milliseconds once warm.
- **Private**: everything runs on your machine; no network access after install.
- **Minimal**: one Python file, three pip dependencies.

It does **not** (yet) do Wayland, streaming/partial results, text post-processing, or a GUI.

## Install

System packages (Debian/Ubuntu):

```bash
sudo apt install xdotool alsa-utils
```

Python (3.9+):

```bash
git clone https://github.com/anish-natekar/gguf-dictate.git
cd gguf-dictate
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Get a model

Any speech-to-text GGUF supported by transcribe.cpp works. Examples:

- Parakeet TDT 0.6B v3 and others under [`handy-computer` on Hugging Face](https://huggingface.co/handy-computer)
- [Underdog Bark 3.0 Plus (unofficial Q8_0 GGUF)](https://huggingface.co/joshthomasdev/underdog-bark-3.0-plus-gguf) — Parakeet-based English model, ~740 MB, CC-BY-4.0 (see the model's own page for attribution terms)

Models are not included in this repo.

## Run

```bash
.venv/bin/python dictate.py --model /path/to/model.gguf
```

Wait for `model ready`, click into any text box, then **hold `f9`**, talk, and release.
On later runs you can omit `--model` (the path is saved in `~/.config/dictate/config.json`).

| Flag | Meaning |
| --- | --- |
| `--model PATH` | Path to a `.gguf` model (remembered). |
| `--hotkey KEYS` | Hold-to-talk keys joined with `+`, e.g. `f9`, `ctrl_r`. Default `f9`. |
| `--lazy-mic` | Open the microphone only while the key is held (adds ~100 ms; avoids the always-on mic indicator). |
| `--no-space` | Don't append a space after each phrase. |

## Top-bar icon (GNOME)

```bash
/usr/bin/python3 tray.py
```

Adds a microphone icon to the top bar (uses the system Python's GTK + AppIndicator, stock on Ubuntu; the
AppIndicator shell extension must be enabled). The menu has Start/Stop, **Model** (choose a `.gguf`, or pick a recent one),
**Settings** (model path, hotkey, mic and spacing options), **How to use / shortcuts**, and **About**.
It starts and restarts `dictate.py` for you.

The tray also shows a click-through, transparent **waveform pill** at the bottom of the screen: bars move with your
voice while the key is held, then a spinner loops while the model transcribes. It needs
`sudo apt install python3-gi-cairo`. Without the tray, `dictate.py` still works (no overlay).

## Snip + annotate + voice notes (for bug reports to chatbots)

Press **`ctrl+alt+s`** (or tray menu -> Take snip). The screen freezes and a toolbar appears:

| Control | Action |
| --- | --- |
| **Box** (`0`, default) | No colour selected: drag to choose the capture area. Drag again to redo it. |
| **Colours** (`1`-`5`) | Pen in that colour. Draw on the shot. Colours are editable in Settings. |
| **Speak** / hold the dictate key | Voice note, saved under the selected colour's heading (**General** if none). |
| **Full screen** (`F`) | Capture the whole screen. |
| **Undo** (`Ctrl+Z`) | Undoes strokes and box changes, in order. |
| **Clear pen**, **Save** (`Enter`), **Cancel** (`Esc`) | |

Saved snips go into a queue (`~/.local/share/dictate/queue`). Click into a chatbot box and press **`ctrl+alt+v`**:
every queued image is pasted in order, each followed by its notes (`## Red` / `- note`), then the queue is cleared.
Hotkeys and colours are in Settings.

## How it works

1. `arecord` streams 16 kHz mono audio; a rolling 0.25 s buffer keeps the first syllable from being clipped.
2. [`pynput`](https://pypi.org/project/pynput/) watches for the hotkey (it observes keys, it does not grab them).
3. On release, the audio goes to transcribe.cpp (`transcribe-cpp` on PyPI, bundled CPU + Vulkan).
4. `xdotool type` types the result into the focused window.

## Notes

- By default the microphone stays open while the program runs (that is what makes it fast). Use `--lazy-mic` if that bothers you.
- X11 only: `pynput` key listening and `xdotool` typing don't work the same on Wayland.
- On Linux the first GPU run compiles shaders, so startup includes a warm-up pass.

## License

MIT for this code. transcribe.cpp and each model have their own licenses.
