"""Smoke test: the GTK modules import and expose what the tray expects (skipped without PyGObject)."""
import pytest

gi = pytest.importorskip("gi")
pytest.importorskip("cairo")
try:
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GdkPixbuf", "2.0")
except ValueError:
    pytest.skip("GTK 3 typelibs not installed", allow_module_level=True)


def test_gui_modules_import():
    from gguf_dictate import overlay, snip

    assert callable(overlay.aurora)
    assert hasattr(snip, "Snip") and snip.Pasting.__name__ == "Pasting"


def test_aurora_colors_are_valid_rgb():
    from gguf_dictate.overlay import aurora

    for i in range(20):
        assert all(0.0 <= c <= 1.0 for c in aurora(i / 20))
