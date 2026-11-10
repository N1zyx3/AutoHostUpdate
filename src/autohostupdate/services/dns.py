"""Сброс DNS-кеша."""

from __future__ import annotations

import subprocess
import sys

from autohostupdate.services.logging import get_logger

_log = get_logger()


def flush_dns(timeout: float = 15.0) -> bool:
    """Сбрасывает DNS-кеш. Возвращает True при успехе (не бросает исключений)."""
    if sys.platform != "win32":
        return False
    try:
        result = subprocess.run(
            ["ipconfig", "/flushdns"],
            capture_output=True,
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _log.warning("Не удалось сбросить DNS: %s", exc)
        return False
    if result.returncode != 0:
        _log.warning("ipconfig /flushdns вернул код %s", result.returncode)
        return False
    _log.info("DNS-кеш сброшен")
    return True
