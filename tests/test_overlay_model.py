"""Waveform / spinner overlay animation state (no toolkit)."""
import pytest

from gguf_dictate.core.overlay_model import BARS, BUSY_W, EXTRA_MESSAGES, REC_W, OverlayModel, aurora


def settle(m, n=60):
    for _ in range(n):
        m.tick()


def test_aurora_is_valid_rgb_and_wraps():
    for i in range(20):
        assert all(0.0 <= c <= 1.0 for c in aurora(i / 20))
    assert aurora(0.0) == pytest.approx(aurora(1.0))


@pytest.mark.parametrize("msg", ["snip", "paste", "cancel", "ctrlv", "note red button overlaps"])
def test_non_animation_messages_are_passed_through_untouched(msg):
    m = OverlayModel()
    assert m.handle(msg) == ("extra", msg)
    assert m.state == "idle" and msg.split()[0] in EXTRA_MESSAGES


def test_rec_resets_bars_and_loudness_reference():
    m = OverlayModel()
    m.handle("rec")
    m.handle("lvl 0.3")
    m.handle("rec")
    assert m.state == "rec" and list(m.hist) == [0.0] * BARS and m.ref == 0.03


def test_rec_requests_animation_timer():
    assert OverlayModel().handle("rec") == ("animate", None)


def test_level_normalised_to_adaptive_reference_and_floor():
    m = OverlayModel()
    m.handle("rec")
    m.handle("lvl 0.002")                  # below the room-noise floor
    assert m.hist[-1] == 0.0
    m.handle("lvl 0.2")                    # new loudest: reference follows it, bar is full
    assert m.hist[-1] == pytest.approx(1.0) and m.ref == pytest.approx(0.2)
    m.handle("lvl 0.1")
    assert 0.0 < m.hist[-1] < 1.0


def test_reference_decays_but_never_below_floor_of_0_02():
    m = OverlayModel()
    m.handle("rec")
    for _ in range(2000):
        m.handle("lvl 0.0")
    assert m.ref == pytest.approx(0.02)


def test_late_idle_does_not_stop_levels_stream_self_heal():
    """Levels only stream while recording: if idle arrived late, a level message revives rec."""
    m = OverlayModel()
    m.handle("lvl 0.1")
    assert m.state == "rec"


def test_busy_then_idle_states():
    m = OverlayModel()
    m.handle("busy")
    assert m.state == "busy"
    m.handle("idle")
    assert m.state == "idle"


def test_fades_in_while_active_and_out_when_idle_then_stops_timer():
    m = OverlayModel()
    m.handle("rec")
    settle(m)
    assert m.alpha > 0.95
    m.handle("idle")
    results = [m.tick() for _ in range(80)]
    assert m.alpha == 0.0 and results[-1] is False and results[0] is True


def test_pill_is_wider_when_recording_than_when_transcribing():
    m = OverlayModel()
    m.handle("rec")
    settle(m)
    assert m.pill_w == pytest.approx(REC_W, abs=1)
    m.handle("busy")
    settle(m)
    assert m.pill_w == pytest.approx(BUSY_W, abs=1)


def test_bars_rise_fast_and_fall_slower():
    m = OverlayModel()
    m.handle("rec")
    for _ in range(BARS):
        m.handle("lvl 0.2")
    m.tick()
    rise = m.disp[-1]
    assert rise > 0.8
    for _ in range(BARS):
        m.handle("lvl 0.0")
    m.tick()
    assert 0.3 < m.disp[-1] < rise
