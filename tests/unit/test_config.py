from __future__ import annotations

import json
from pathlib import Path

import pytest

from autohostupdate.config.schema import AppSettings, LogFormat, ScheduleSettings
from autohostupdate.config.store import SettingsError, load_settings, save_settings


def test_defaults_are_stable() -> None:
    settings = AppSettings()
    assert settings.source.url == "https://geohide.ru/eu/hosts"
    assert settings.update.encoding == "utf-8-sig"
    assert settings.update.newline == "\r\n"
    assert settings.advanced.telemetry == "off"
    assert settings.logging.format is LogFormat.TEXT


def test_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    settings = AppSettings()
    settings.general.language = "en"
    settings.update.backup_keep_count = 3
    save_settings(settings, path)

    loaded = load_settings(path)
    assert loaded.general.language == "en"
    assert loaded.update.backup_keep_count == 3
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 1


def test_missing_file_returns_defaults(tmp_path: Path) -> None:
    assert load_settings(tmp_path / "absent.json") == AppSettings()


def test_invalid_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{nope", encoding="utf-8")
    with pytest.raises(SettingsError):
        load_settings(path)


def test_future_schema_rejected(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"schema_version": 99}', encoding="utf-8")
    with pytest.raises(SettingsError):
        load_settings(path)


def test_unknown_keys_ignored(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        '{"schema_version": 1, "unknown": 1, "general": {"theme": "dark"}}', encoding="utf-8"
    )
    settings = load_settings(path)
    assert settings.general.theme == "dark"


@pytest.mark.parametrize("value", ["25:00", "abc", "12-00", "99:99"])
def test_daily_time_validation(value: str) -> None:
    with pytest.raises(ValueError):
        ScheduleSettings(daily_time=value)


def test_daily_time_normalized() -> None:
    assert ScheduleSettings(daily_time="9:05").daily_time == "09:05"
