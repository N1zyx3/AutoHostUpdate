"""Слой настроек."""

from __future__ import annotations

from autohostupdate.config.schema import (
    SCHEMA_VERSION,
    AppSettings,
    GeneralSettings,
    GroupSettings,
    LoggingSettings,
    NotificationSettings,
    ScheduleSettings,
    SourceSettings,
    UpdateSettings,
)
from autohostupdate.config.store import SettingsError, load_settings, save_settings

__all__ = [
    "SCHEMA_VERSION",
    "AppSettings",
    "GeneralSettings",
    "GroupSettings",
    "LoggingSettings",
    "NotificationSettings",
    "ScheduleSettings",
    "SettingsError",
    "SourceSettings",
    "UpdateSettings",
    "load_settings",
    "save_settings",
]
