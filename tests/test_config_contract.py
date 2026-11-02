"""Config behaviour the Qt port must preserve (the port moves paths to platformdirs but not these contracts)."""
import json
import stat

from gguf_dictate import config


def test_save_overwrites_existing_and_preserves_unicode(tmp_path):
    p = tmp_path / "config.json"
    config.save_config({"a": 1}, p)
    config.save_config({"model": "é.gguf"}, p)
    assert config.load_config(p) == {"model": "é.gguf"}
    assert json.loads(p.read_text())["model"] == "é.gguf"


def test_load_empty_file_is_empty_dict(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("")
    assert config.load_config(p) == {}


def test_runtime_dir_falls_back_to_private_tmp_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(config.os, "getuid", lambda: 424242)
    monkeypatch.setattr(config, "Path", lambda p: tmp_path / "fallback" if str(p).startswith("/tmp/dictate-") else config.Path(p))
    d = config.runtime_dir()
    assert d.name == "fallback" and stat.S_IMODE(d.stat().st_mode) == 0o700


def test_runtime_files_share_one_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert {config.log_path().parent, config.lock_path().parent, config.editor_flag().parent} == {tmp_path / "dictate"}
    assert (config.log_path().name, config.lock_path().name, config.editor_flag().name) == ("dictate.log", "tray.lock", "editor-open")


def test_default_colors_unique_named_and_within_max():
    names = [n for n, _ in config.DEFAULT_COLORS]
    assert names == ["Red", "Blue", "Green", "Yellow", "Purple"]
    assert len(set(names)) == len(names) <= config.MAX_COLORS
    assert all(len(h) == 7 and h.startswith("#") for _, h in config.DEFAULT_COLORS)
