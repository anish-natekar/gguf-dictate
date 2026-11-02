import stat

from gguf_dictate import config


def test_load_missing_or_corrupt_returns_empty(tmp_path):
    assert config.load_config(tmp_path / "nope.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    assert config.load_config(bad) == {}


def test_save_roundtrip_is_atomic(tmp_path):
    p = tmp_path / "sub" / "config.json"
    config.save_config({"model": "m.gguf"}, p)
    assert config.load_config(p) == {"model": "m.gguf"}
    assert [f.name for f in p.parent.iterdir()] == ["config.json"]   # no leftover temp file


def test_runtime_dir_is_private(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    d = config.runtime_dir()
    assert d == tmp_path / "dictate"
    assert stat.S_IMODE(d.stat().st_mode) == 0o700
    assert config.editor_flag().parent == d and config.log_path().parent == d


def test_default_colors_are_name_hex_pairs():
    assert all(len(c) == 2 and c[1].startswith("#") for c in config.DEFAULT_COLORS)
