"""Пути приложения и системные пути."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "AutoHostUpdate"


def app_data_dir() -> Path:
    """%LOCALAPPDATA%\\AutoHostUpdate."""
    return Path(user_data_dir(APP_NAME, appauthor=False, roaming=False))


def logs_dir() -> Path:
    return app_data_dir() / "logs"


def backups_dir() -> Path:
    return app_data_dir() / "backups"


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def default_log_path() -> Path:
    return logs_dir() / f"{APP_NAME}.log"


def system_hosts_path() -> Path:
    """%SystemRoot%\\System32\\drivers\\etc\\hosts."""
    root = os.environ.get("SYSTEMROOT") or os.environ.get("WINDIR") or r"C:\Windows"
    return Path(root) / "System32" / "drivers" / "etc" / "hosts"


def is_windows() -> bool:
    return sys.platform == "win32"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
