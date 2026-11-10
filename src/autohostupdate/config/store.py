"""Загрузка и атомарное сохранение настроек."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from autohostupdate.config.schema import SCHEMA_VERSION, AppSettings
from autohostupdate.errors import AutoHostUpdateError
from autohostupdate.infrastructure import paths


class SettingsError(AutoHostUpdateError):
    """Настройки повреждены или не могут быть сохранены."""


def _migrate(data: dict) -> dict:
    version = int(data.get("schema_version", 0) or 0)
    if version > SCHEMA_VERSION:
        raise SettingsError(
            f"Настройки новее приложения (schema_version={version} > {SCHEMA_VERSION})."
        )
    # v0 -> v1: раньше версии не было, структура совместима.
    data["schema_version"] = SCHEMA_VERSION
    return data


def load_settings(path: str | os.PathLike[str] | None = None) -> AppSettings:
    settings_path = Path(path) if path is not None else paths.settings_path()
    if not settings_path.exists():
        return AppSettings()

    try:
        raw = settings_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise SettingsError(f"Не удалось прочитать настройки: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SettingsError(f"Настройки не являются корректным JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SettingsError("Корень файла настроек должен быть объектом.")

    try:
        return AppSettings.model_validate(_migrate(data))
    except ValidationError as exc:
        raise SettingsError(f"Некорректные настройки: {exc}") from exc


def save_settings(settings: AppSettings, path: str | os.PathLike[str] | None = None) -> Path:
    target = Path(path) if path is not None else settings.advanced.settings_path
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = settings.model_dump(mode="json")

    fd, tmp_name = tempfile.mkstemp(prefix=".settings-", suffix=".json", dir=target.parent)
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(tmp_path, target)
    except OSError as exc:
        raise SettingsError(f"Не удалось сохранить настройки: {exc}") from exc
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
    return target
