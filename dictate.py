#!/usr/bin/env python3
"""Hold a hotkey, talk, release: the text is typed into the focused window.

Local STT via transcribe.cpp on any GGUF (Parakeet / Whisper / ...). X11 only.

    .venv/bin/python dictate.py --model /path/to/model.gguf
"""
import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import transcribe_cpp
from pynput import keyboard

RATE = 16000
CONFIG = Path.home() / ".config" / "dictate" / "config.json"
ALIASES = {"ctrl_l": "ctrl", "ctrl_r": "ctrl", "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt",
           "shift_l": "shift", "shift_r": "shift", "cmd_l": "cmd", "cmd_r": "cmd"}


def load_config():
    try:
        return json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2))


def key_name(key):
    name = key.char.lower() if isinstance(key, keyboard.KeyCode) and key.char else getattr(key, "name", str(key))
    return ALIASES.get(name, name)


class Mic:
    """arecord piped as raw float32; keeps a rolling buffer so the first syllable isn't lost."""

    PREROLL = int(0.25 * RATE)

    def __init__(self, lazy):
        self.lazy, self.proc, self.buf, self.lock = lazy, None, [], threading.Lock()
        self.recording, self.pre = False, np.zeros(0, np.float32)
        if not lazy:
            self._spawn()

    def _spawn(self):
        self.proc = subprocess.Popen(
            ["arecord", "-q", "-t", "raw", "-f", "FLOAT_LE", "-r", str(RATE), "-c", "1"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()

    def _read(self, proc):
        while True:
            data = proc.stdout.read(3200)  # 50 ms
            if not data:
                return
            chunk = np.frombuffer(data[: len(data) // 4 * 4], np.float32)
            with self.lock:
                if self.recording:
                    self.buf.append(chunk)
                else:
                    self.pre = np.concatenate([self.pre, chunk])[-self.PREROLL:]

    def start(self):
        if self.lazy:
            self._spawn()
        with self.lock:
            self.buf, self.recording = [self.pre], True

    def stop(self):
        with self.lock:
            self.recording = False
            audio = np.concatenate(self.buf) if self.buf else np.zeros(0, np.float32)
            self.buf = []
        if self.lazy and self.proc:
            self.proc.terminate()
        return audio


def type_text(text):
    subprocess.run(["xdotool", "type", "--clearmodifiers", "--delay", "1", "--", text], check=False)


def main():
    cfg = load_config()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=cfg.get("model"), help="path to a .gguf model (remembered after first use)")
    ap.add_argument("--hotkey", default=cfg.get("hotkey", "ctrl+alt+space"),
                    help="hold to talk, e.g. ctrl+alt+space, f9, ctrl_r (default: %(default)s)")
    ap.add_argument("--lazy-mic", action="store_true", help="open the mic only while the key is held (adds ~100ms)")
    ap.add_argument("--no-space", action="store_true", help="don't append a space after each phrase")
    args = ap.parse_args()
    if not args.model or not Path(args.model).expanduser().is_file():
        sys.exit("pass --model /path/to/model.gguf")
    model_path = str(Path(args.model).expanduser().resolve())
    save_config({"model": model_path, "hotkey": args.hotkey})

    transcribe_cpp.set_log_callback(lambda lvl, msg: print(msg, file=sys.stderr) if lvl >= 3 else None)
    t = time.time()
    model = transcribe_cpp.Model(model_path)
    session = model.session()
    session.run(np.zeros(RATE, np.float32))  # warm up: first GPU run compiles shaders
    print(f"model ready in {time.time() - t:.1f}s | hold [{args.hotkey}] to talk | Ctrl+C to quit", flush=True)

    combo = {ALIASES.get(k, k) for k in args.hotkey.lower().replace(" ", "").split("+")}
    mic, down, busy = Mic(args.lazy_mic), set(), threading.Lock()
    state = {"active": False}

    def work(audio):
        with busy:
            if len(audio) < 0.2 * RATE:
                return
            t0 = time.time()
            text = session.run(audio).text.strip()
            print(f"[{len(audio) / RATE:.1f}s audio -> {(time.time() - t0) * 1000:.0f}ms] {text}", flush=True)
            if text:
                type_text(text if args.no_space else text + " ")

    def on_press(key):
        down.add(key_name(key))
        if not state["active"] and combo <= down:
            state["active"] = True
            mic.start()

    def on_release(key):
        down.discard(key_name(key))
        if state["active"] and not combo <= down:
            state["active"] = False
            threading.Thread(target=lambda a=mic.stop(): work(a), daemon=True).start()

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        try:
            listener.join()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
