"""WinUI 3 Application: главное окно и контроллер."""

from __future__ import annotations

import datetime
import os
import sys

from autohostupdate.config.store import load_settings
from autohostupdate.services.logging import setup_logging
from autohostupdate.services.single_instance import SingleInstance


def start() -> int:
    """Создаёт Application и запускает цикл сообщений WinUI."""
    from winui3.microsoft.ui.xaml import Application

    from autohostupdate.ui.main_window import MainWindow

    single = SingleInstance("Local\\AutoHostUpdate_UI")
    if not single.acquire():
        print("AutoHostUpdate уже запущен.", file=sys.stderr)
        return 0

    smoke_seconds = float(os.environ.get("AUTOHOSTUPDATE_UI_SMOKE", "0") or 0)

    class AutoHostUpdateApp(Application):
        def _on_launched(self, args) -> None:
            settings = load_settings()
            setup_logging(settings)
            self.ui = MainWindow(settings)
            self.ui.show()
            if smoke_seconds > 0:
                timer = self.ui.window.dispatcher_queue.create_timer()
                timer.interval = datetime.timedelta(seconds=smoke_seconds)
                timer.is_repeating = False

                def tick(sender, event_args) -> None:
                    timer.stop()
                    self.ui.window.close()

                timer.add_tick(tick)
                timer.start()

    Application.start(lambda params: AutoHostUpdateApp())
    single.release()
    return 0
