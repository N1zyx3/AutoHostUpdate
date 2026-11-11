"""Инициализация Windows App SDK и запуск UI.

PyWinRT 3.2.1 собран против Windows App SDK 1.7, но bootstrap умеет грузить
любую установленную совместимую версию. Перебираем известные версии, чтобы
приложение работало и с 1.6, и с 1.8+.
"""

from __future__ import annotations

import os
import sys

FALLBACK_VERSIONS: tuple[tuple[str, str], ...] = (
    ("1.8", "8000.0.0.0"),
    ("1.7", "7000.0.0.0"),
    ("1.6", "6000.0.0.0"),
)


class RuntimeInitError(RuntimeError):
    """Не удалось инициализировать Windows App Runtime."""


def initialize_runtime():
    """Возвращает контекст bootstrap Windows App SDK."""
    from winui3.microsoft.windows.applicationmodel.dynamicdependency import bootstrap

    options = bootstrap.InitializeOptions.NONE
    explicit = os.environ.get("AUTOHOSTUPDATE_WINAPPSDK_VERSION")

    attempts: list[tuple[str | None, str | None]] = []
    if explicit:
        attempts.append((explicit, None))
    attempts.append((None, None))
    attempts.extend(FALLBACK_VERSIONS)

    errors: list[str] = []
    for version, min_version in attempts:
        try:
            if version is None:
                return bootstrap.initialize(options=options)
            if min_version is None:
                return bootstrap.initialize(version, options=options)
            return bootstrap.initialize(version, min_version, options)
        except OSError as exc:
            errors.append(f"{version or 'default'}: {exc}")

    raise RuntimeInitError(
        "Windows App Runtime не найден. Установите Windows App SDK 1.8 "
        "(https://aka.ms/windowsappsdk). Детали: " + "; ".join(errors)
    )


def run_application() -> int:
    if sys.platform != "win32":
        raise RuntimeError("WinUI 3 доступен только в Windows")

    from autohostupdate.ui.application import start

    with initialize_runtime():
        return start()
