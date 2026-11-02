#!/usr/bin/env python3
"""Hold a hotkey, talk, release: the text is typed into the focused window.

Local STT via transcribe.cpp on any GGUF (Parakeet / Whisper / ...). X11 only.

    dictate --model /path/to/model.gguf
"""
import argparse
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import transcribe_cpp
from pynput import keyboard

from . import ipc
from .config import editor_flag, load_config, save_config
from .core.state import RATE, DictationState, HotkeyRouter, prepare_audio, route_text


def notify(msg):
    """Tell the tray's waveform overlay what's happening; harmless if it isn't running."""
    ipc.send(msg, ipc.OVERLAY)


def key_name(key):
    return key.char.lower() if isinstance(key, keyboard.KeyCode) and key.char else getattr(key, "name", str(key))


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

    flag, busy = editor_flag(), threading.Lock()

    def process(audio):
        with busy:
            audio, why = prepare_audio(audio)
            if audio is None:
                print(why if why == "too short" else f"mic is {why}: check input device / volume / mute", flush=True)
                return
            t0 = time.time()
            text = session.run(audio).text.strip()
            print(f"[{len(audio) / RATE:.1f}s audio -> {(time.time() - t0) * 1000:.0f}ms] {text}", flush=True)
            routed = route_text(text, flag.exists(), args.no_space)   # editor open: a voice note, not typing
            if routed and routed[0] == "note":
                notify("note " + routed[1])
            elif routed:
                type_text(routed[1])

    def notify_and_log(msg):
        if msg == "rec":
            print("recording...", flush=True)
        notify(msg)

    state = DictationState(Mic(args.lazy_mic), notify_and_log, process)
    router = HotkeyRouter(args.hotkey, args.snip_hotkey, args.paste_hotkey, state, notify, flag.exists)

    ctl = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)   # the snip editor's Speak button talks to us here
    try:
        ctl.bind(ipc.CONTROL)
    except OSError:
        pass

    def listen():
        while True:
            state.begin("button") if ctl.recv(16) == b"start" else state.end()

    threading.Thread(target=listen, daemon=True).start()

    with keyboard.Listener(on_press=lambda k: router.press(key_name(k)), on_release=lambda k: router.release(key_name(k))) as listener:
        try:
            listener.join()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
