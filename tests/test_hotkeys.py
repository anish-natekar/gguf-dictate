import pytest

from gguf_dictate import hotkeys


def test_parse_normalizes_case_and_spaces():
    assert hotkeys.parse("Ctrl + Alt+S") == {"ctrl", "alt", "s"}


@pytest.mark.parametrize("hk", ["f9", "ctrl+shift+space", "ctrl_r", "ctrl+alt+s"])
def test_valid(hk):
    assert hotkeys.valid(hk)


@pytest.mark.parametrize("hk", ["", "+", "ctrl+", "ctrl++s", "ctrl+!"])
def test_invalid(hk):
    assert not hotkeys.valid(hk)


def test_held_generic_modifier_matches_either_side():
    assert hotkeys.held({"ctrl", "s"}, {"ctrl_l", "s"})
    assert hotkeys.held({"ctrl", "s"}, {"ctrl_r", "s"})


def test_held_side_specific_modifier_is_strict():
    assert hotkeys.held({"ctrl_r"}, {"ctrl_r"})
    assert not hotkeys.held({"ctrl_r"}, {"ctrl_l"})


def test_held_needs_every_key():
    assert not hotkeys.held({"ctrl", "alt", "s"}, {"ctrl_l", "s"})


def test_ctrl_v_vs_paste_all_hotkey():
    assert hotkeys.is_ctrl_v("v", {"ctrl_l", "v"})
    assert not hotkeys.is_ctrl_v("v", {"ctrl_l", "alt_l", "v"})   # Ctrl+Alt+V is paste-all
    assert not hotkeys.is_ctrl_v("v", {"v"})
    assert not hotkeys.is_ctrl_v("c", {"ctrl_l", "c"})
