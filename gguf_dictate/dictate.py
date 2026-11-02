#!/usr/bin/env python3
"""Hold a hotkey, talk, release: the text is typed into the focused window.

Local STT via transcribe.cpp on any GGUF (Parakeet / Whisper / ...). X11 only.

    dictate --model /path/to/model.gguf
"""
import argparse
import socket
import sys
import threading
import time
from pathlib import Path

import numpy as np
import transcribe_cpp
from pynput import keyboard

from . import ipc
from .config import editor_flag, load_config, save_config
from .core.dictation import Dictation
from .core.recorder import Recorder
from .core.state import RATE
from .platform.audio import SoundDeviceSource
from .platform.linux import XdotoolKeys


def notify(msg):
    """Tell the tray's waveform overlay what's happening; harmless if it isn't running."""
    ipc.send(msg, ipc.OVERLAY)


def key_name(key):
    return key.char.lower() if isinstance(key, keyboard.KeyCode) and key.char else getattr(key, "name", str(key))


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

    flag = editor_flag()
    mic = Recorder(SoundDeviceSource(), on_level=lambda lvl: notify(f"lvl {lvl:.5f}"), lazy=args.lazy_mic)
    dictation = Dictation(session, mic, XdotoolKeys(), notify, flag.exists, args.hotkey, args.snip_hotkey, args.paste_hotkey,
                          no_space=args.no_space, log=lambda m: print(m, flush=True))
    state, router = dictation.state, dictation.router

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
