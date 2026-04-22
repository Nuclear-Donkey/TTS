"""Tests for macOS config loader."""
from __future__ import annotations

from pathlib import Path

from voice_input_macos.config import Config, InjectConfig, HotkeyConfig, load


def test_defaults():
    cfg = Config()
    assert cfg.hotkey.ptt == "caps_lock"
    assert cfg.audio.device == ""
    assert cfg.audio.sample_rate == 16_000
    assert cfg.inject.method == "paste"
    assert cfg.inject.restore_clipboard is True
    assert cfg.inject.paste_delay == 0.08
    assert cfg.stt.num_threads == 4


def test_missing_file_returns_defaults(tmp_path: Path):
    cfg = load(tmp_path / "nonexistent.toml")
    assert cfg.hotkey.ptt == "caps_lock"
    assert cfg.inject.paste_delay == 0.08


def test_partial_override(tmp_path: Path):
    f = tmp_path / "c.toml"
    f.write_text('[hotkey]\nptt = "f9"\n')
    cfg = load(f)
    assert cfg.hotkey.ptt == "f9"
    assert cfg.inject.paste_delay == 0.08  # unchanged


def test_unknown_key_is_ignored(tmp_path: Path):
    f = tmp_path / "c.toml"
    f.write_text('[hotkey]\nptt = "f12"\nnonexistent = true\n')
    cfg = load(f)
    assert cfg.hotkey.ptt == "f12"


def test_malformed_toml_falls_back_to_defaults(tmp_path: Path):
    f = tmp_path / "bad.toml"
    f.write_text("this is not valid toml {{{")
    cfg = load(f)
    assert cfg.hotkey.ptt == "caps_lock"
