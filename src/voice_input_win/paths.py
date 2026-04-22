"""Windows-appropriate application paths.

Uses %LOCALAPPDATA% for model cache (same as Microsoft Store apps),
%APPDATA% for user config, %LOCALAPPDATA%\\<app>\\logs for logs.
"""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "voice-input"


def _env_path(var: str, fallback: Path) -> Path:
    v = os.environ.get(var)
    return Path(v) if v else fallback


def local_appdata() -> Path:
    return _env_path("LOCALAPPDATA", Path.home() / "AppData" / "Local")


def roaming_appdata() -> Path:
    return _env_path("APPDATA", Path.home() / "AppData" / "Roaming")


CONFIG_DIR = roaming_appdata() / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.toml"

DATA_DIR = local_appdata() / APP_NAME
MODEL_DIR = DATA_DIR / "models" / "paraformer-zh"

LOG_DIR = DATA_DIR / "logs"
LOG_FILE = LOG_DIR / "service.log"
