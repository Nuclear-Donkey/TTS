"""Config loader tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from voice_ibus.config import Config, load


def test_missing_file_returns_defaults(tmp_path: Path):
    cfg = load(tmp_path / "does-not-exist.toml")
    assert cfg.hotkey.ptt == "CapsLock"
    assert cfg.audio.sample_rate == 16_000


def test_partial_override(tmp_path: Path):
    f = tmp_path / "c.toml"
    f.write_text(
        """
[hotkey]
ptt = "F9"

[stt]
num_threads = 8
"""
    )
    cfg = load(f)
    assert cfg.hotkey.ptt == "F9"
    assert cfg.hotkey.cancel == "Escape"       # default kept
    assert cfg.stt.num_threads == 8
    assert cfg.audio.device == "default"       # default kept


def test_unknown_key_is_ignored(tmp_path: Path):
    f = tmp_path / "c.toml"
    f.write_text(
        """
[hotkey]
ptt = "CapsLock"
bogus_key = 123
"""
    )
    cfg = load(f)
    assert cfg.hotkey.ptt == "CapsLock"


def test_malformed_toml_falls_back_to_defaults(tmp_path: Path, caplog):
    f = tmp_path / "c.toml"
    f.write_text("this is [not valid TOML")
    cfg = load(f)
    assert isinstance(cfg, Config)
    assert cfg.hotkey.ptt == "CapsLock"
