"""Проверка прав администратора и запуск elevated-helper."""

from __future__ import annotations

import ctypes
import subprocess
import sys


def is_admin() -> bool:
    """True, если текущий процесс запущен с повышенными правами."""
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def exec_self_elevated(args: list[str], *, wait: bool = True) -> int | None:
    """Перезапускает текущий исполняемый файл через `runas`.

    Возвращает код выхода при `wait=True`; иначе None.
    """
    if sys.platform != "win32":
        raise OSError("Elevation доступна только в Windows")

    if getattr(sys, "frozen", False):
        executable = sys.executable
        params = subprocess.list2cmdline(args)
    else:
        executable = sys.executable
        params = subprocess.list2cmdline(["-m", "autohostupdate", *args])

    try:
        rc = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            executable,
            params,
            None,
            5,  # SW_SHOW
        )
    except OSError:
        return None
    if rc <= 32:  # ShellExecuteW вернул ошибку
        return None
    return 0 if wait else None
