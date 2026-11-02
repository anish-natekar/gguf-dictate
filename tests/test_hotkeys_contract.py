"""Hotkey behaviour the Qt port must preserve."""
import pytest

from gguf_dictate import hotkeys


def test_normalize_strips_spaces_and_lowercases():
    assert hotkeys.normalize("  Ctrl + ALT + S ") == "ctrl+alt+s"


@pytest.mark.parametrize("hk", ["F9", "Ctrl+Alt+S", " ctrl + v "])
def test_valid_accepts_mixed_case_and_spaces(hk):
    assert hotkeys.valid(hk)


@pytest.mark.parametrize("hk", ["ctrl+alt+", "+f9", "ctrl alt s!", "f9+", "ctrl+-"])
def test_invalid_shapes(hk):
    assert not hotkeys.valid(hk)


def test_held_empty_combo_is_vacuously_true():
    assert hotkeys.held(set(), set())


@pytest.mark.parametrize("side,generic", [("alt_l", "alt"), ("alt_r", "alt"), ("alt_gr", "alt"), ("shift_r", "shift"), ("cmd_l", "cmd")])
def test_held_alias_table(side, generic):
    assert hotkeys.held({generic}, {side})


def test_held_extra_keys_down_do_not_matter():
    assert hotkeys.held({"f9"}, {"f9", "ctrl_l", "a"})


def test_default_talk_snip_paste_combos_parse():
    for hk, expected in [("f9", {"f9"}), ("ctrl+alt+s", {"ctrl", "alt", "s"}), ("ctrl+alt+v", {"ctrl", "alt", "v"})]:
        assert hotkeys.valid(hk) and hotkeys.parse(hk) == expected


def test_ctrl_v_with_right_ctrl_and_with_extra_shift():
    assert hotkeys.is_ctrl_v("v", {"ctrl_r", "v"})
    assert hotkeys.is_ctrl_v("v", {"ctrl_l", "shift_l", "v"})     # current behaviour: shift does not block it


def test_ctrl_v_not_triggered_by_alt_gr_combo():
    assert not hotkeys.is_ctrl_v("v", {"ctrl_l", "alt_gr", "v"})
