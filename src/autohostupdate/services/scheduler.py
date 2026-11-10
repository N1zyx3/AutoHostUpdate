"""Регистрация задачи в Планировщике заданий через COM (pywin32)."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

from autohostupdate.config.schema import ScheduleSettings, ScheduleTrigger
from autohostupdate.errors import TaskSchedulerError

TASK_FOLDER = "\\"

_TASK_RUNLEVEL = {"highest": 1, "limited": 0}
_TASK_CREATE_OR_UPDATE = 6
_TASK_LOGON_INTERACTIVE_TOKEN = 3
_TASK_TRIGGER_LOGON = 9
_TASK_TRIGGER_DAILY = 2
_TASK_TRIGGER_TIME = 1


@dataclass(frozen=True, slots=True)
class TaskInfo:
    name: str
    path: str
    state: int | None = None
    enabled: bool = False

    @property
    def exists(self) -> bool:
        return self.path != ""


def _service():
    if sys.platform != "win32":
        raise TaskSchedulerError("Планировщик заданий доступен только в Windows")
    try:
        import win32com.client  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - зависит от окружения
        raise TaskSchedulerError("pywin32 не установлен") from exc
    service = win32com.client.Dispatch("Schedule.Service")
    service.Connect()
    return service


def _command_line(executable: str) -> str:
    return subprocess.list2cmdline([executable, "--update", "--quiet"])


def install_task(executable: str, settings: ScheduleSettings) -> None:
    """Создаёт или обновляет задачу по настройкам."""
    service = _service()
    root = service.GetFolder(TASK_FOLDER)

    definition = service.NewTask(0)
    definition.RegistrationInfo.Description = (
        "Автоматическое обновление именованных групп в hosts из GeoHideDNS"
    )
    definition.Settings.Hidden = settings.hidden
    definition.Settings.DisallowStartIfOnBatteries = not settings.allow_on_battery
    definition.Settings.StopIfGoingOnBatteries = settings.stop_on_battery
    definition.Settings.StartWhenAvailable = settings.run_missed_start
    if settings.time_limit_minutes > 0:
        definition.Settings.ExecutionTimeLimit = f"PT{settings.time_limit_minutes}M"
    else:
        definition.Settings.ExecutionTimeLimit = "PT0S"

    if settings.trigger is ScheduleTrigger.AT_LOGON:
        trigger = definition.Triggers.Create(_TASK_TRIGGER_LOGON)
        trigger.Delay = f"PT{settings.start_delay_seconds}S"
    elif settings.trigger is ScheduleTrigger.DAILY:
        trigger = definition.Triggers.Create(_TASK_TRIGGER_DAILY)
        trigger.StartBoundary = f"1970-01-01T{settings.daily_time}:00"
        trigger.DaysInterval = 1
    elif settings.trigger is ScheduleTrigger.INTERVAL:
        trigger = definition.Triggers.Create(_TASK_TRIGGER_TIME)
        trigger.StartBoundary = "1970-01-01T00:00:00"
        trigger.Repetition.Interval = f"PT{settings.interval_minutes}M"
        if settings.interval_minutes:
            trigger.Repetition.Duration = "P1D"
    else:
        raise TaskSchedulerError("Ручной режим не требует задачи в Планировщике")

    principal = definition.Principal
    principal.LogonType = _TASK_LOGON_INTERACTIVE_TOKEN
    principal.RunLevel = _TASK_RUNLEVEL.get(settings.run_level, 1)

    definition.Actions.Create(0).Path = executable
    definition.Actions.Item(1).Arguments = "--update --quiet"

    try:
        root.RegisterTaskDefinition(
            settings.task_name,
            definition,
            _TASK_CREATE_OR_UPDATE,
            None,
            None,
            _TASK_LOGON_INTERACTIVE_TOKEN,
        )
    except Exception as exc:  # COMException
        raise TaskSchedulerError(f"Не удалось зарегистрировать задачу: {exc}") from exc


def uninstall_task(task_name: str = "AutoHostUpdate") -> bool:
    service = _service()
    root = service.GetFolder(TASK_FOLDER)
    try:
        root.DeleteTask(task_name, 0)
        return True
    except Exception:
        return False


def task_info(task_name: str = "AutoHostUpdate") -> TaskInfo:
    service = _service()
    root = service.GetFolder(TASK_FOLDER)
    try:
        task = root.GetTask(task_name)
        return TaskInfo(
            name=task.Name, path=task.Path, state=task.State, enabled=bool(task.Enabled)
        )
    except Exception:
        return TaskInfo(name=task_name, path="")


def run_task(task_name: str = "AutoHostUpdate") -> None:
    service = _service()
    root = service.GetFolder(TASK_FOLDER)
    try:
        root.GetTask(task_name).Run("")
    except Exception as exc:
        raise TaskSchedulerError(f"Не удалось запустить задачу: {exc}") from exc
