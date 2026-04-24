"""Config loader — TOML-based, with sane defaults."""
from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

CONFIG_PATH = Path(os.path.expanduser("~/.config/ibus-voice/config.toml"))
DEFAULT_MODEL_DIR = Path(os.path.expanduser("~/.local/share/ibus-voice/models/paraformer-zh"))


@dataclass
class HotkeyConfig:
    ptt: str = "CapsLock"
    cancel: str = "Escape"


@dataclass
class AudioConfig:
    device: str = "default"
    sample_rate: int = 16_000


@dataclass
class SttConfig:
    model_dir: str = str(DEFAULT_MODEL_DIR)
    num_threads: int = 4


@dataclass
class UiConfig:
    show_aux: bool = True


@dataclass
class Config:
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    stt: SttConfig = field(default_factory=SttConfig)
    ui: UiConfig = field(default_factory=UiConfig)


def load(path: Path = CONFIG_PATH) -> Config:
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

    if "hotkey" in raw:
        _apply(cfg.hotkey, raw["hotkey"])
    if "audio" in raw:
        _apply(cfg.audio, raw["audio"])
    if "stt" in raw:
        _apply(cfg.stt, raw["stt"])
    if "ui" in raw:
        _apply(cfg.ui, raw["ui"])
    log.info("loaded config from %s", path)
    return cfg


def _apply(section_obj, values: dict) -> None:
    for k, v in values.items():
        if hasattr(section_obj, k):
            setattr(section_obj, k, v)
        else:
            log.warning("unknown config key %s.%s", type(section_obj).__name__, k)
