"""Защита от параллельного запуска через named mutex."""

from __future__ import annotations

import ctypes
import sys

MUTEX_NAME = "Global\\AutoHostUpdate_RunOnce"
ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    """Контекстный менеджер: удерживает mutex, пока жив объект."""

    def __init__(self, name: str = MUTEX_NAME) -> None:
        self.name = name
        self._handle: int | None = None
        self.acquired = False

    def __enter__(self) -> SingleInstance:
        self.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()

    def acquire(self) -> bool:
        if sys.platform != "win32":
            self.acquired = True
            return True
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, self.name)
        if not handle:
            self.acquired = True
            return True
        self._handle = handle
        already = ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS
        self.acquired = not already
        if already:
            ctypes.windll.kernel32.CloseHandle(handle)
            self._handle = None
        return self.acquired

    def release(self) -> None:
        if self._handle and sys.platform == "win32":
            ctypes.windll.kernel32.CloseHandle(self._handle)
        self._handle = None
        self.acquired = False
