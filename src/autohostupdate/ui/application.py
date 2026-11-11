"""WinUI 3 Application: метаданные XAML, окно, единственный экземпляр."""

from __future__ import annotations

import datetime
import os
import sys

from winrt.microsoft.ui.xaml import Application, ApplicationInitializationCallbackParams
from winrt.microsoft.ui.xaml.controls import XamlControlsResources
from winrt.microsoft.ui.xaml.markup import IXamlMetadataProvider, IXamlType, XmlnsDefinition
from winrt.microsoft.ui.xaml.xamltypeinfo import XamlControlsXamlMetaDataProvider
from winrt.system import Array
from winrt.windows.ui.xaml.interop import TypeKind, TypeName

from autohostupdate.config.store import load_settings
from autohostupdate.services.logging import setup_logging
from autohostupdate.services.single_instance import SingleInstance


class AutoHostUpdateApp(Application, IXamlMetadataProvider):
    """Application обязана реализовать IXamlMetadataProvider, иначе WinUI не
    находит ресурсы контролов (XamlControlsResources падает с missing key)."""

    def __init__(self) -> None:
        super().__init__()
        self._provider = XamlControlsXamlMetaDataProvider()

    def _on_launched(self, args) -> None:
        from autohostupdate.ui.main_window import MainWindow

        self.resources.merged_dictionaries.append(XamlControlsResources())

        settings = load_settings()
        setup_logging(settings)
        self.ui = MainWindow(settings)
        self.ui.show()

        if os.environ.get("AUTOHOSTUPDATE_UI_SMOKE_PAGES"):
            self.ui.smoke_exercise()

        smoke_seconds = float(os.environ.get("AUTOHOSTUPDATE_UI_SMOKE", "0") or 0)
        if smoke_seconds > 0:
            timer = self.ui.window.dispatcher_queue.create_timer()
            timer.interval = datetime.timedelta(seconds=smoke_seconds)
            timer.is_repeating = False

            def tick(sender, event_args) -> None:
                timer.stop()
                self.ui.window.close()

            timer.add_tick(tick)
            timer.start()

    def get_xaml_type(self, type: TypeName | tuple[str, TypeKind]) -> IXamlType:
        return self._provider.get_xaml_type(type)

    def get_xaml_type_by_full_name(self, full_name: str) -> IXamlType:
        return self._provider.get_xaml_type_by_full_name(full_name)

    def get_xmlns_definitions(self) -> Array[XmlnsDefinition]:
        return self._provider.get_xmlns_definitions()


def start() -> int:
    """Запускает приложение. Вызывается после bootstrap Windows App SDK."""
    single = SingleInstance("Local\\AutoHostUpdate_UI")
    if not single.acquire():
        print("AutoHostUpdate уже запущен.", file=sys.stderr)
        return 0

    def init(_: ApplicationInitializationCallbackParams) -> None:
        AutoHostUpdateApp()

    Application.start(init)
    single.release()
    return 0
