#!/usr/bin/env python3
"""Hold a hotkey, talk, release: the text is typed into the focused window.

Local STT via transcribe.cpp on any GGUF (Parakeet / Whisper / ...). X11 only.

    .venv/bin/python dictate.py --model /path/to/model.gguf
"""
import argparse
import json
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import transcribe_cpp
from pynput import keyboard

RATE = 16000
EDITOR_FLAG = Path("/tmp/dictate-editor")
CONFIG = Path.home() / ".config" / "dictate" / "config.json"
ALIASES = {"ctrl_l": "ctrl", "ctrl_r": "ctrl", "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt",
           "shift_l": "shift", "shift_r": "shift", "cmd_l": "cmd", "cmd_r": "cmd"}


_overlay = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
_overlay.setblocking(False)


def notify(msg):
    """Tell the tray's waveform overlay what's happening; harmless if it isn't running."""
    try:
        _overlay.sendto(msg.encode(), b"\0dictate-overlay")
    except OSError:
        pass


def load_config():
    try:
        return json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2))


def key_name(key):
    return key.char.lower() if isinstance(key, keyboard.KeyCode) and key.char else getattr(key, "name", str(key))


def held(combo, down):
    """Every wanted key is down; 'ctrl' matches either side, 'ctrl_r' only the right one."""
    return all(k in down or any(ALIASES.get(d) == k for d in down) for k in combo)


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
            data = proc.stdout.read(1280)  # 20 ms
            if not data:
                return
            chunk = np.frombuffer(data[: len(data) // 4 * 4], np.float32)
            with self.lock:
                if self.recording:
                    self.buf.append(chunk)
                    notify(f"lvl {float(np.sqrt(np.mean(chunk * chunk))):.5f}")
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
    ap.add_argument("--hotkey", default=cfg.get("hotkey", "f9"),
                    help="hold to talk, e.g. f9, ctrl+shift+space, ctrl_r (default: %(default)s)")
    ap.add_argument("--lazy-mic", action="store_true", default=cfg.get("lazy_mic", False), help="open the mic only while the key is held (adds ~100ms)")
    ap.add_argument("--snip-hotkey", default=cfg.get("snip_hotkey", "ctrl+alt+s"), help="open the snip/annotate editor (default: %(default)s)")
    ap.add_argument("--paste-hotkey", default=cfg.get("paste_hotkey", "ctrl+alt+v"), help="paste every queued snip (default: %(default)s)")
    ap.add_argument("--no-space", action="store_true", default=cfg.get("no_space", False), help="don't append a space after each phrase")
    args = ap.parse_args()
    if not args.model or not Path(args.model).expanduser().is_file():
        sys.exit("pass --model /path/to/model.gguf")
    model_path = str(Path(args.model).expanduser().resolve())
    save_config({**cfg, "model": model_path, "hotkey": args.hotkey})

    transcribe_cpp.set_log_callback(lambda lvl, msg: print(msg, file=sys.stderr) if lvl >= 3 else None)
    t = time.time()
    model = transcribe_cpp.Model(model_path)
    session = model.session()
    session.run(np.zeros(RATE, np.float32))  # warm up: first GPU run compiles shaders
    print(f"{Path(model_path).name} ready in {time.time() - t:.1f}s | hold [{args.hotkey}] to talk | Ctrl+C to quit", flush=True)

    def parse(hk):
        return set(hk.lower().replace(" ", "").split("+"))

    combo, snip_combo, paste_combo, fired = parse(args.hotkey), parse(args.snip_hotkey), parse(args.paste_hotkey), set()
    mic, down, busy = Mic(args.lazy_mic), set(), threading.Lock()
    state = {"active": False, "source": "key", "pending": 0}

    plock = threading.Lock()

    def work(audio):
        try:
            transcribe(audio)
        finally:
            with plock:     # hide the overlay only when nothing is recording or still queued
                state["pending"] -= 1
                if not state["pending"] and not state["active"]:
                    notify("idle")

    def transcribe(audio):
        with busy:
            if len(audio) < 0.2 * RATE:
                print("too short, ignored", flush=True)
                return
            peak = float(np.abs(audio).max())
            if peak < 0.005:
                print(f"mic is silent (peak {peak:.4f}): check input device / volume / mute", flush=True)
                return
            if peak < 0.5:  # quiet mic: normalise so the model gets a healthy level
                audio = audio * (0.7 / peak)
            t0 = time.time()
            text = session.run(audio).text.strip()
            print(f"[{len(audio) / RATE:.1f}s audio -> {(time.time() - t0) * 1000:.0f}ms] {text}", flush=True)
            if text and EDITOR_FLAG.exists():   # snip editor is open: this is a voice note, not typing
                notify("note " + text)
            elif text:
                type_text(text if args.no_space else text + " ")

    def begin(source):
        if not state["active"]:
            state.update(active=True, source=source)
            print("recording...", flush=True)
            notify("rec")
            mic.start()

    def end():
        if state["active"]:
            state["active"] = False
            audio = mic.stop()
            with plock:
                state["pending"] += 1
            notify("busy")
            threading.Thread(target=work, args=(audio,), daemon=True).start()

    ctl = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)   # the snip editor's Speak button talks to us here
    try:
        ctl.bind(b"\0dictate-control")
    except OSError:
        pass

    def listen():
        while True:
            begin("button") if ctl.recv(16) == b"start" else end()

    threading.Thread(target=listen, daemon=True).start()

    def on_press(key):
        down.add(key_name(key))
        if key == keyboard.Key.esc and EDITOR_FLAG.exists():
            notify("cancel")   # Esc closes the snip editor even if it never got keyboard focus
        if held(combo, down):
            begin("key")
        for name, c in (("snip", snip_combo), ("paste", paste_combo)):
            if name not in fired and held(c, down):
                fired.add(name)
                if name == "snip":
                    notify(name)       # paste waits for key release: our synthetic Ctrl+V would clash with the held keys

    def on_release(key):
        down.discard(key_name(key))
        for n, c in (("snip", snip_combo), ("paste", paste_combo)):
            if n in fired and not held(c, down):
                fired.discard(n)
                if n == "paste":
                    time.sleep(0.15)   # let the physical keys fully settle
                    notify("paste")
        if state["active"] and state["source"] == "key" and not held(combo, down):
            end()

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        try:
            listener.join()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
