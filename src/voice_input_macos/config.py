"""TOML config loader for macOS voice input."""
from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from voice_input_common.config import apply_section
from voice_input_macos.paths import CONFIG_FILE, MODEL_DIR

log = logging.getLogger(__name__)


@dataclass
class HotkeyConfig:
    # pynput key name: "caps_lock", "right_option", "left_option", "f9", etc.
    ptt: str = "caps_lock"


@dataclass
class AudioConfig:
    # sounddevice device index (int) or name substring, empty for system default
    device: str = ""
    sample_rate: int = 16_000


@dataclass
class SttConfig:
    model_dir: str = str(MODEL_DIR)
    num_threads: int = 4


@dataclass
class InjectConfig:
    # "paste" = clipboard + Cmd+V via pynput (recommended)
    # "applescript" = AppleScript Cmd+V (no Accessibility permission needed)
    method: str = "paste"
    restore_clipboard: bool = True
    # Slightly higher than Windows (0.05) due to macOS clipboard sync
    paste_delay: float = 0.08


@dataclass
class Config:
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    stt: SttConfig = field(default_factory=SttConfig)
    inject: InjectConfig = field(default_factory=InjectConfig)


def load(path: Path = CONFIG_FILE) -> Config:
    cfg = Config()
    if not path.exists():
        log.info("no config at %s, using defaults", path)
        return cfg
    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        log.warning("config %s unreadable (%s), using defaults", path, e)
        return cfg

    for section_name, section_obj in [
        ("hotkey", cfg.hotkey),
        ("audio", cfg.audio),
        ("stt", cfg.stt),
        ("inject", cfg.inject),
    ]:
        if section_name in raw:
            apply_section(section_obj, raw[section_name])
    log.info("loaded config from %s", path)
    return cfg
