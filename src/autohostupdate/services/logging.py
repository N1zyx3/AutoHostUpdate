"""Настройка логирования: ротация, формат, редакция URL, чтение журнала."""

from __future__ import annotations

import json
import logging
import platform
import re
import sys
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from autohostupdate.config.schema import AppSettings, LogFormat

LOGGER_NAME = "autohostupdate"
_URL_RE = re.compile(r"(https?://[^\s?]+)\?[^\s]*")
_LEVEL_RE = re.compile(
    r"^(?:\d{4}-\d{2}-\d{2}[ T][\d:,.]+)?\s*(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\b"
)
_JSON_LEVEL_RE = re.compile(r'"level":\s*"(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)"')

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


class _RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _URL_RE.sub(r"\1?<redacted>", record.msg)
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(settings: AppSettings, *, console: bool = False) -> logging.Logger:
    log_settings = settings.logging
    log_dir = Path(log_settings.directory)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / log_settings.file_name

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(log_settings.level.value)
    logger.handlers.clear()
    logger.propagate = False

    handler = RotatingFileHandler(
        log_path,
        maxBytes=log_settings.max_size_mb * 1024 * 1024,
        backupCount=log_settings.backup_count,
        encoding="utf-8",
    )
    if log_settings.format is LogFormat.JSON:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s"))
    if log_settings.redact_urls:
        handler.addFilter(_RedactionFilter())
    logger.addHandler(handler)

    if console:
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(stream)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


# --- чтение и обслуживание журнала -------------------------------------------
def _line_level(line: str) -> str | None:
    match = _JSON_LEVEL_RE.search(line) if line.lstrip().startswith("{") else None
    if match is None:
        match = _LEVEL_RE.match(line)
    return match.group("level") if match else None


@dataclass(frozen=True, slots=True)
class LogQuery:
    """Фильтр для страницы «Журнал»."""

    limit: int = 500
    level: str | None = None
    search: str = ""


def read_log_tail(path: str | Path, query: LogQuery | None = None) -> list[str]:
    """Последние строки журнала с фильтром по уровню и подстроке."""
    query = query or LogQuery()
    log_path = Path(path)
    try:
        raw = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return []
    except OSError as exc:
        return [f"Не удалось прочитать журнал: {exc}"]

    needle = query.search.strip().lower()
    filtered: list[str] = []
    for line in raw:
        if query.level:
            level = _line_level(line)
            if level is not None and level != query.level:
                continue
        if needle and needle not in line.lower():
            continue
        filtered.append(line)

    limit = max(1, query.limit)
    return filtered[-limit:]


def clear_log(path: str | Path) -> None:
    """Очищает журнал. Файл пересоздаётся пустым (открытый handler продолжит писать)."""
    log_path = Path(path)
    if not log_path.exists():
        return
    with log_path.open("w", encoding="utf-8"):
        pass


def diagnostics_summary(settings: AppSettings, *, version: str | None = None) -> str:
    """Текстовая сводка окружения без секретов и содержимого hosts."""
    lines = [
        f"version: {version or 'unknown'}",
        f"python: {sys.version.split()[0]}",
        f"platform: {platform.platform()}",
        f"hosts_path: {settings.update.hosts_path}",
        f"source_url: {settings.source.url}",
        f"log_level: {settings.logging.level.value}",
        f"schema_version: {settings.schema_version}",
        f"generated_utc: {datetime.now(UTC).isoformat(timespec='seconds')}",
    ]
    return "\n".join(lines)


def export_diagnostics(
    destination: str | Path,
    log_path: str | Path,
    settings: AppSettings,
    *,
    version: str | None = None,
) -> Path:
    """Складывает журналы и сводку окружения в zip для отправки в поддержку."""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    log_file = Path(log_path)
    candidates = [log_file, *(log_file.parent.glob(f"{log_file.name}.*"))]

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for candidate in candidates:
            if candidate.is_file():
                archive.write(candidate, arcname=candidate.name)
        archive.writestr("environment.txt", diagnostics_summary(settings, version=version))
    return target


def redact(text: str) -> str:
    """Убирает query-параметры из URL в произвольном тексте."""
    return _URL_RE.sub(r"\1?<redacted>", text)
