"""Типизированные исключения приложения."""

from __future__ import annotations


class AutoHostUpdateError(Exception):
    """Базовое исключение приложения."""


class SourceUnavailableError(AutoHostUpdateError):
    """Источник недоступен или вернул некорректный ответ."""


class SourceFormatError(SourceUnavailableError):
    """Ответ источника не удалось разобрать."""


class HostsReadError(AutoHostUpdateError):
    """Не удалось прочитать локальный hosts."""


class HostsWriteError(AutoHostUpdateError):
    """Не удалось записать локальный hosts."""


class ElevationRequiredError(AutoHostUpdateError):
    """Операция требует прав администратора."""


class AlreadyRunningError(AutoHostUpdateError):
    """Уже работает другой экземпляр."""


class TaskSchedulerError(AutoHostUpdateError):
    """Ошибка при работе с Планировщиком задач."""
