"""Per-user paths (platformdirs) and the single-instance lock."""
from pathlib import Path

from gguf_dictate import config
from gguf_dictate.core.lock import SingleInstance
from gguf_dictate.notes import Queue


def test_config_file_follows_xdg_config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config.config_file() == tmp_path / "dictate" / "config.json"


def test_queue_dir_follows_xdg_data_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert config.queue_dir() == tmp_path / "dictate" / "queue"


def test_defaults_match_the_locations_existing_installs_use(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert config.config_file() == tmp_path / ".config" / "dictate" / "config.json"
    assert config.queue_dir() == tmp_path / ".local" / "share" / "dictate" / "queue"


def test_save_and_load_default_to_config_file_at_call_time(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config.save_config({"model": "m.gguf"})
    assert (tmp_path / "dictate" / "config.json").is_file()
    assert config.load_config() == {"model": "m.gguf"}


def test_queue_default_directory_is_resolved_at_call_time(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert Queue().dir == tmp_path / "dictate" / "queue" and Queue().dir.is_dir()


def test_lock_is_exclusive_until_released(tmp_path):
    a, b = SingleInstance(tmp_path / "tray.lock"), SingleInstance(tmp_path / "tray.lock")
    assert a.acquire() is True
    assert b.acquire() is False
    a.release()
    assert b.acquire() is True
    b.release()


def test_release_is_idempotent_and_safe_without_acquire(tmp_path):
    lock = SingleInstance(tmp_path / "x.lock")
    lock.release()
    assert lock.acquire() and (tmp_path / "x.lock").exists()
    lock.release()
    lock.release()


def test_acquire_twice_on_same_object_stays_true(tmp_path):
    lock = SingleInstance(tmp_path / "x.lock")
    assert lock.acquire() and lock.acquire()
    lock.release()


def test_lock_creates_parent_directory(tmp_path):
    lock = SingleInstance(Path(tmp_path) / "deep" / "er" / "x.lock")
    assert lock.acquire()
    lock.release()
