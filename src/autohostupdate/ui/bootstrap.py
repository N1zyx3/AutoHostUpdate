"""Инициализация Windows App SDK и запуск UI."""

from __future__ import annotations

import sys

from winrt.microsoft.windows.applicationmodel.dynamicdependency.bootstrap import (
    InitializeOptions,
    initialize,
)
from winrt.runtime import ApartmentType, init_apartment


def initialize_runtime():
    """Входит в контекст bootstrap Windows App SDK (нужен установленный runtime)."""
    return initialize(options=InitializeOptions.ON_NO_MATCH_SHOW_UI)


def run_application() -> int:
    if sys.platform != "win32":
        raise RuntimeError("WinUI 3 доступен только в Windows")

    from autohostupdate.ui.application import start

    init_apartment(ApartmentType.SINGLE_THREADED)
    with initialize_runtime():
        return start()
