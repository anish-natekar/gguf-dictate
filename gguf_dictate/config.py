"""Paths, config file and constants shared by the app."""
import json
import os
from pathlib import Path

from platformdirs import user_config_path, user_data_path, user_runtime_path

DEFAULT_COLORS = [["Red", "#ff3b30"], ["Blue", "#0a84ff"], ["Green", "#30d158"], ["Yellow", "#ffd60a"], ["Purple", "#bf5af2"]]
MAX_COLORS = 9


def config_file():
    return user_config_path("dictate", appauthor=False) / "config.json"


def queue_dir():
    return user_data_path("dictate", appauthor=False) / "queue"


def meetings_dir():
    return user_data_path("dictate", appauthor=False) / "meetings"


def runtime_dir():
    """Per-user 0700 directory for the log and lock files (never a shared, predictable /tmp name)."""
    if os.name == "nt":
        d = user_runtime_path("dictate", appauthor=False)
    else:
        base = os.environ.get("XDG_RUNTIME_DIR")
        d = Path(base) / "dictate" if base else Path(f"/tmp/dictate-{os.getuid()}")
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    return d


def log_path():
    return runtime_dir() / "dictate.log"


def lock_path():
    return runtime_dir() / "tray.lock"


def load_config(path=None):
    try:
        return json.loads((path or config_file()).read_text())
    except (OSError, ValueError):
        return {}


def save_config(cfg, path=None):
    path = path or config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2))
    tmp.replace(path)     # atomic: a crash can't leave a half-written config
