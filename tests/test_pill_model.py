import pytest

from gguf_dictate.core.pill_model import MARGIN, SNAP_DIST, clamp, format_elapsed, snap

SCREEN = (0, 0, 1920, 1080)
W, H = 170, 36


@pytest.mark.parametrize("seconds,text", [(0, "0:00"), (5.9, "0:05"), (65, "1:05"), (3599, "59:59"), (3600, "1:00:00"), (3725.9, "1:02:05"), (-4, "0:00")])
def test_format_elapsed(seconds, text):
    assert format_elapsed(seconds) == text


def test_clamp_keeps_a_position_that_already_fits():
    assert clamp(100, 200, W, H, SCREEN) == (100, 200)


def test_clamp_pulls_the_pill_back_inside_every_edge():
    assert clamp(-50, -50, W, H, SCREEN) == (0, 0)
    assert clamp(5000, 5000, W, H, SCREEN) == (1920 - W, 1080 - H)


def test_clamp_respects_a_screen_that_does_not_start_at_zero():
    assert clamp(10, 10, W, H, (1920, 0, 3840, 1080)) == (1920, 10)


def test_clamp_on_a_screen_smaller_than_the_pill_aligns_top_left():
    assert clamp(50, 50, W, H, (0, 0, 100, 20)) == (0, 0)


def test_snap_to_each_corner():
    near = SNAP_DIST - 1
    assert snap(near, near, W, H, SCREEN) == (MARGIN, MARGIN)
    assert snap(1920 - W - near, near, W, H, SCREEN) == (1920 - W - MARGIN, MARGIN)
    assert snap(near, 1080 - H - near, W, H, SCREEN) == (MARGIN, 1080 - H - MARGIN)
    assert snap(1920 - W - near, 1080 - H - near, W, H, SCREEN) == (1920 - W - MARGIN, 1080 - H - MARGIN)


def test_snap_leaves_a_pill_in_open_space_alone():
    assert snap(800, 400, W, H, SCREEN) == (800, 400)


def test_snap_works_per_axis():
    assert snap(5, 400, W, H, SCREEN) == (MARGIN, 400)
    assert snap(800, 3, W, H, SCREEN) == (800, MARGIN)


def test_snap_ignores_a_pill_just_outside_the_range():
    assert snap(MARGIN + SNAP_DIST + 1, 400, W, H, SCREEN)[0] == MARGIN + SNAP_DIST + 1
