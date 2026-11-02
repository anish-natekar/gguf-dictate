"""Hotkey parsing and matching (pure logic, no display needed)."""
import re

ALIASES = {"ctrl_l": "ctrl", "ctrl_r": "ctrl", "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt",
           "shift_l": "shift", "shift_r": "shift", "cmd_l": "cmd", "cmd_r": "cmd"}
HOTKEY_RE = re.compile(r"^[a-z0-9_]+(\+[a-z0-9_]+)*$")


def normalize(hotkey):
    return hotkey.strip().lower().replace(" ", "")


def parse(hotkey):
    """'Ctrl + Alt+S' -> {'ctrl', 'alt', 's'}"""
    return set(normalize(hotkey).split("+"))


def valid(hotkey):
    return bool(HOTKEY_RE.match(normalize(hotkey)))


def held(combo, down):
    """Every wanted key is down; 'ctrl' matches either side, 'ctrl_r' only the right one."""
    return all(k in down or any(ALIASES.get(d) == k for d in down) for k in combo)


def is_ctrl_v(key, down):
    """Plain Ctrl+V (no Alt, which is the paste-all hotkey)."""
    return key == "v" and held({"ctrl"}, down) and not held({"alt"}, down)
