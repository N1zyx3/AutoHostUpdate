"""Схема настроек приложения (Pydantic)."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from autohostupdate.infrastructure import paths

SCHEMA_VERSION = 1


class Theme(StrEnum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


class Language(StrEnum):
    RU = "ru"
    EN = "en"


class ScheduleTrigger(StrEnum):
    AT_LOGON = "at_logon"
    DAILY = "daily"
    INTERVAL = "interval"
    MANUAL = "manual"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class LogFormat(StrEnum):
    TEXT = "text"
    JSON = "json"


class ProxyMode(StrEnum):
    SYSTEM = "system"
    NONE = "none"
    MANUAL = "manual"


class UpdateMode(StrEnum):
    """Как сравнивать актуальность."""

    DATE = "date"
    HASH = "hash"


class _Section(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)


class GeneralSettings(_Section):
    language: Language = Language.RU
    theme: Theme = Theme.SYSTEM
    run_at_logon: bool = True
    start_minimized: bool = False
    close_to_tray: bool = False
    single_instance: bool = True
    run_ui_as_admin: bool = False


class SourceSettings(_Section):
    url: str = "https://geohide.ru/eu/hosts"
    fallback_urls: list[str] = Field(default_factory=list)
    timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    retries: int = Field(default=2, ge=0, le=10)
    proxy_mode: ProxyMode = ProxyMode.SYSTEM
    proxy_url: str | None = None
    verify_tls: bool = True
    user_agent: str = "AutoHostUpdate"
    max_response_kb: int = Field(default=2048, ge=16, le=65536)
    encoding: str = "auto"
    marker_prefix: str = "Последнее обновление:"
    marker_line_index: int = Field(default=2, ge=1, le=10)


class GroupSettings(_Section):
    update_existing_only: bool = True
    disabled_groups: list[str] = Field(default_factory=list)
    force_add_groups: list[str] = Field(default_factory=list)
    ignore_case: bool = False
    keep_user_comments: bool = True


class UpdateSettings(_Section):
    check_on_start: bool = True
    auto_check_interval_minutes: int = Field(default=0, ge=0, le=1440)
    compare_mode: UpdateMode = UpdateMode.DATE
    dry_run_by_default: bool = False
    atomic_write: bool = True
    create_backup: bool = True
    backup_dir: Path = Field(default_factory=paths.backups_dir)
    backup_keep_count: int = Field(default=10, ge=1, le=500)
    backup_keep_days: int = Field(default=30, ge=1, le=3650)
    hosts_path: Path = Field(default_factory=paths.system_hosts_path)
    encoding: str = "utf-8-sig"
    newline: Literal["\r\n", "\n"] = "\r\n"
    final_newline: bool = False
    clear_readonly: bool = True
    flush_dns: bool = True
    validate_before_replace: bool = True
    restore_backup_on_error: bool = True


class ScheduleSettings(_Section):
    trigger: ScheduleTrigger = ScheduleTrigger.AT_LOGON
    daily_time: str = "09:00"
    interval_minutes: int = Field(default=60, ge=5, le=10080)
    start_delay_seconds: int = Field(default=30, ge=0, le=3600)
    allow_on_battery: bool = True
    stop_on_battery: bool = False
    run_missed_start: bool = True
    time_limit_minutes: int = Field(default=0, ge=0)
    task_name: str = "AutoHostUpdate"
    hidden: bool = True
    run_level: Literal["highest", "limited"] = "highest"

    @field_validator("daily_time")
    @classmethod
    def _validate_time(cls, value: str) -> str:
        parts = value.split(":")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise ValueError("Время должно быть в формате HH:MM")
        hours, minutes = int(parts[0]), int(parts[1])
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            raise ValueError("Некорректное время")
        return f"{hours:02d}:{minutes:02d}"


class NotificationSettings(_Section):
    enabled: bool = True
    notify_success: bool = True
    notify_no_update: bool = True
    notify_errors: bool = True
    sound: bool = True
    duration_seconds: int = Field(default=10, ge=1, le=120)
    show_critical_dialog: bool = True


class LoggingSettings(_Section):
    level: LogLevel = LogLevel.INFO
    directory: Path = Field(default_factory=paths.logs_dir)
    file_name: str = "AutoHostUpdate.log"
    max_size_mb: int = Field(default=5, ge=1, le=100)
    backup_count: int = Field(default=5, ge=1, le=50)
    format: LogFormat = LogFormat.TEXT
    redact_urls: bool = True


class AdvancedSettings(_Section):
    settings_path: Path = Field(default_factory=paths.settings_path)
    developer_mode: bool = False
    telemetry: Literal["off"] = "off"


class AppSettings(_Section):
    schema_version: int = SCHEMA_VERSION
    general: GeneralSettings = Field(default_factory=GeneralSettings)
    source: SourceSettings = Field(default_factory=SourceSettings)
    groups: GroupSettings = Field(default_factory=GroupSettings)
    update: UpdateSettings = Field(default_factory=UpdateSettings)
    schedule: ScheduleSettings = Field(default_factory=ScheduleSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    advanced: AdvancedSettings = Field(default_factory=AdvancedSettings)
