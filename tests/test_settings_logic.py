"""Pure settings validation (was inline in the GTK dialog)."""
import pytest

from gguf_dictate.config import DEFAULT_COLORS, MAX_COLORS
from gguf_dictate.core.settings import SettingsError, format_colors, parse_colors, remember_model, validate


@pytest.fixture
def model(tmp_path):
    p = tmp_path / "m.gguf"
    p.write_bytes(b"x")
    return str(p)


def form(model, **kw):
    base = dict(model=model, hotkey="F9", snip_hotkey="Ctrl + Alt + S", paste_hotkey="ctrl+alt+v",
                colors="Red=#ff3b30, Blue=#0a84ff", lazy_mic=False, no_space=True)
    base.update(kw)
    return base


def test_colors_round_trip_default():
    assert parse_colors(format_colors(DEFAULT_COLORS)) == [list(c) for c in DEFAULT_COLORS]


def test_colors_capped_and_whitespace_trimmed():
    text = ", ".join(f" C{i} = #00000{i} " for i in range(MAX_COLORS + 3))
    got = parse_colors(text)
    assert len(got) == MAX_COLORS and got[0] == ["C0", "#000000"]


@pytest.mark.parametrize("bad", ["", "Red", "Red=notacolor", "Red=#12", "=#ffffff", "Red=#ff0000=x"])
def test_bad_colors_rejected(bad):
    with pytest.raises(SettingsError):
        parse_colors(bad)


def test_valid_form_normalises_hotkeys_and_expands_model(model):
    out = validate(form(model))
    assert out["hotkey"] == "f9" and out["snip_hotkey"] == "ctrl+alt+s" and out["model"] == model
    assert out["colors"] == [["Red", "#ff3b30"], ["Blue", "#0a84ff"]] and out["no_space"] is True and out["lazy_mic"] is False


def test_missing_model_file(tmp_path):
    with pytest.raises(SettingsError, match="Model file not found"):
        validate(form(str(tmp_path / "nope.gguf")))


def test_empty_model(model):
    with pytest.raises(SettingsError, match="Model file not found"):
        validate(form(""))


@pytest.mark.parametrize("field", ["hotkey", "snip_hotkey", "paste_hotkey"])
def test_invalid_hotkey_in_any_field(model, field):
    with pytest.raises(SettingsError, match="Invalid hotkey"):
        validate(form(model, **{field: "ctrl+"}))


def test_remember_model_puts_it_first_dedups_and_caps_at_five():
    cfg = {"recent": ["a", "b", "c", "d", "e"]}
    remember_model(cfg, "c")
    assert cfg["model"] == "c" and cfg["recent"] == ["c", "a", "b", "d", "e"]
    remember_model(cfg, "z")
    assert cfg["recent"] == ["z", "c", "a", "b", "d"]
