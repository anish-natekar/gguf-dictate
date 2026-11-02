"""Smoke test: every module of the Qt app imports (offscreen) and the entry point exists."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")


def test_modules_import_and_entry_point_is_callable():
    from gguf_dictate import app, model
    from gguf_dictate.platform import audio, keys, linux, qt
    from gguf_dictate.ui import dialogs, editor, overlay, settings, snip, tray

    assert callable(app.main) and callable(model.load_session) and callable(keys.start_listener)
    assert all([audio, linux, qt, dialogs, editor, overlay, settings, snip, tray])
