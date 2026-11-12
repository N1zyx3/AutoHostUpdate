"""Проверка прав администратора и запуск elevated-helper."""

from __future__ import annotations

import ctypes
import subprocess
import sys
from ctypes import wintypes

_SEE_MASK_NOCLOSEPROCESS = 0x00000040
_SEE_MASK_NOASYNC = 0x00000100


class _SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", ctypes.c_ulong),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIconOrMonitor", ctypes.c_void_p),
        ("hProcess", wintypes.HANDLE),
    ]


def is_admin() -> bool:
    """True, если текущий процесс запущен с повышенными правами."""
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def _command(args: list[str]) -> tuple[str, str]:
    if getattr(sys, "frozen", False):
        return sys.executable, subprocess.list2cmdline(args)
    return sys.executable, subprocess.list2cmdline(["-m", "autohostupdate", *args])


def exec_self_elevated(
    args: list[str],
    *,
    wait: bool = True,
    timeout_ms: int = 10 * 60 * 1000,
) -> int | None:
    """Перезапускает текущий исполняемый файл через `runas`.

    Возвращает код выхода при `wait=True` (или ``None``, если UAC отклонён,
    запуск не удался либо истёк таймаут); при `wait=False` — 0 после успешного
    запуска.
    """
    if sys.platform != "win32":
        raise OSError("Elevation доступна только в Windows")

    executable, params = _command(args)
    info = _SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(_SHELLEXECUTEINFOW)
    info.fMask = _SEE_MASK_NOCLOSEPROCESS | _SEE_MASK_NOASYNC
    info.lpVerb = "runas"
    info.lpFile = executable
    info.lpParameters = params
    info.nShow = 1  # SW_SHOWNORMAL

    shell32 = ctypes.windll.shell32
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_SHELLEXECUTEINFOW)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL

    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        # UAC отклонён или запуск невозможен.
        return None
    if not wait:
        if info.hProcess:
            ctypes.windll.kernel32.CloseHandle(info.hProcess)
        return 0
    if not info.hProcess:
        return 0

    kernel32 = ctypes.windll.kernel32
    try:
        if kernel32.WaitForSingleObject(info.hProcess, timeout_ms) != 0:
            return None
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code)):
            return None
        return int(code.value)
    finally:
        kernel32.CloseHandle(info.hProcess)
