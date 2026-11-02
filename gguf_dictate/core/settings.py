"""Settings-form validation, kept out of the dialog so it is testable without a GUI."""
import re
from pathlib import Path

from .. import hotkeys
from ..config import MAX_COLORS

HEX = re.compile(r"#[0-9a-fA-F]{6}")
MAX_RECENT = 5


class SettingsError(ValueError):
    def __init__(self, title, text):
        super().__init__(title)
        self.title, self.text = title, text


def format_colors(colors):
    return ", ".join(f"{n}={h}" for n, h in colors)


def parse_colors(text):
    """'Red=#ff3b30, Blue=#0a84ff' -> [["Red", "#ff3b30"], ...] (at most MAX_COLORS)."""
    bad = SettingsError("Invalid colours", "Use Name=#rrggbb pairs, e.g. Red=#ff3b30, Blue=#0a84ff")
    pairs = [c for c in text.split(",") if c.strip()][:MAX_COLORS]
    out = []
    for c in pairs:
        parts = c.split("=")
        if len(parts) != 2:
            raise bad
        name, value = parts[0].strip(), parts[1].strip()
        if not name or not HEX.fullmatch(value):
            raise bad
        out.append([name, value])
    if not out:
        raise bad
    return out


def validate(form):
    """Return the config keys to store for a settings form, or raise SettingsError."""
    path = str(form.get("model", "")).strip()
    if not path or not Path(path).expanduser().is_file():
        raise SettingsError("Model file not found", f"{path or '(empty)'} is not a file.")
    keys = {k: hotkeys.normalize(form[k]) for k in ("hotkey", "snip_hotkey", "paste_hotkey")}
    if not all(hotkeys.valid(k) for k in keys.values()):
        raise SettingsError("Invalid hotkey", "Use key names joined with +, e.g. f9 or ctrl+shift+space.")
    return {"model": str(Path(path).expanduser()), **keys, "colors": parse_colors(form["colors"]),
            "lazy_mic": bool(form.get("lazy_mic")), "no_space": bool(form.get("no_space"))}


def remember_model(cfg, path):
    cfg["model"] = path
    cfg["recent"] = [path] + [p for p in cfg.get("recent", []) if p != path][:MAX_RECENT - 1]
    return cfg
