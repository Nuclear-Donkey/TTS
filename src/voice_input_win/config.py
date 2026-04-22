"""TOML config loader for Windows voice input.

Separate from the Linux voice_ibus config because:
- different default paths (%LOCALAPPDATA% vs ~/.local/share)
- different hotkey semantics ("right alt" vs keyval 0xffe5)
- no IBus-specific [ui] options
"""
from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from voice_input_win.paths import CONFIG_FILE, MODEL_DIR

log = logging.getLogger(__name__)


@dataclass
class HotkeyConfig:
    # Any keyboard lib key name. Common: "right alt", "caps lock", "f9", "right ctrl"
    ptt: str = "right alt"


@dataclass
class AudioConfig:
    # sounddevice device index (int) or name substring, or empty for system default
    device: str = ""
    sample_rate: int = 16_000


@dataclass
class SttConfig:
    model_dir: str = str(MODEL_DIR)
    num_threads: int = 4


@dataclass
class InjectConfig:
    # "paste" = clipboard + Ctrl+V (recommended)
    # "type"  = simulated keystrokes (kept for future, less reliable for CJK)
    method: str = "paste"
    # After pasting, restore the user's original clipboard (best-effort).
    restore_clipboard: bool = True
    # Small delay (seconds) between setting clipboard and sending Ctrl+V so
    # Windows has time to update the clipboard for the target app.
    paste_delay: float = 0.05


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
            _apply(section_obj, raw[section_name])
    log.info("loaded config from %s", path)
    return cfg


def _apply(section_obj, values: dict) -> None:
    for k, v in values.items():
        if hasattr(section_obj, k):
            setattr(section_obj, k, v)
        else:
            log.warning("unknown config key %s.%s", type(section_obj).__name__, k)
