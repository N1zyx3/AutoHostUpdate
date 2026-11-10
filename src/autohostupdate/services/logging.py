"""Настройка логирования: ротация, формат, редакция URL."""

from __future__ import annotations

import json
import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from autohostupdate.config.schema import AppSettings, LogFormat

LOGGER_NAME = "autohostupdate"
_URL_RE = re.compile(r"(https?://[^\s?]+)\?[^\s]*")


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
