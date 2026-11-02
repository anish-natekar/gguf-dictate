"""Paths, config file and constants shared by the dictation process and the tray."""
import json
import os
from pathlib import Path

CONFIG = Path.home() / ".config" / "dictate" / "config.json"
QUEUE_DIR = Path.home() / ".local" / "share" / "dictate" / "queue"

DEFAULT_COLORS = [["Red", "#ff3b30"], ["Blue", "#0a84ff"], ["Green", "#30d158"], ["Yellow", "#ffd60a"], ["Purple", "#bf5af2"]]
MAX_COLORS = 9


def runtime_dir():
    """Per-user 0700 directory for the log, lock and flag files (never a shared, predictable /tmp name)."""
    base = os.environ.get("XDG_RUNTIME_DIR")
    d = Path(base) / "dictate" if base else Path(f"/tmp/dictate-{os.getuid()}")
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    return d


def log_path():
    return runtime_dir() / "dictate.log"


def lock_path():
    return runtime_dir() / "tray.lock"


def editor_flag():
    """Exists while the snip editor is open: dictated text then becomes a voice note instead of being typed."""
    return runtime_dir() / "editor-open"


def load_config(path=None):
    try:
        return json.loads((path or CONFIG).read_text())
    except (OSError, ValueError):
        return {}


def save_config(cfg, path=None):
    path = path or CONFIG
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2))
    tmp.replace(path)     # atomic: a crash can't leave a half-written config
