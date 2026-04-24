"""macOS-appropriate application paths.

Uses ~/Library/Application Support for data/models,
~/Library/Logs for logs.
"""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "voice-input"


def _env_path(var: str, fallback: Path) -> Path:
    v = os.environ.get(var)
    return Path(v) if v else fallback


DATA_DIR = _env_path(
    "VOICE_INPUT_DATA_DIR",
    Path.home() / "Library" / "Application Support" / APP_NAME,
)
CONFIG_DIR = DATA_DIR
CONFIG_FILE = CONFIG_DIR / "config.toml"
MODEL_DIR = DATA_DIR / "models" / "paraformer-zh"

LOG_DIR = _env_path(
    "VOICE_INPUT_LOG_DIR",
    Path.home() / "Library" / "Logs" / APP_NAME,
)
LOG_FILE = LOG_DIR / "service.log"
