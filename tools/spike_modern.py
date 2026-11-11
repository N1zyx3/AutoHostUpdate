"""Spike: официальный шаблон PyWinRT WinUI 3 (winrt-runtime 4 / WinAppSDK 2.x)."""

from __future__ import annotations

import datetime
import os

from winrt.microsoft.ui.xaml import (
    Application,
    ApplicationInitializationCallbackParams,
    FrameworkElement,
    LaunchActivatedEventArgs,
    Window,
)
from winrt.microsoft.ui.xaml.controls import Button, XamlControlsResources
from winrt.microsoft.ui.xaml.markup import (
    IXamlMetadataProvider,
    IXamlType,
    XamlReader,
    XmlnsDefinition,
)
from winrt.microsoft.ui.xaml.xamltypeinfo import XamlControlsXamlMetaDataProvider
from winrt.microsoft.windows.applicationmodel.dynamicdependency.bootstrap import (
    InitializeOptions,
    initialize,
)
from winrt.runtime import ApartmentType, init_apartment
from winrt.system import Array
from winrt.windows.ui.xaml.interop import TypeKind, TypeName

XAML = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">
  <Grid Padding="24">
    <StackPanel Spacing="10">
      <TextBlock Text="AutoHostUpdate" FontSize="28"/>
      <Button Name="click" Content="Проверить"/>
      <ProgressRing Name="ring" IsActive="True" Width="24" Height="24"/>
    </StackPanel>
  </Grid>
</Window>
"""


def log(message: str) -> None:
    with open(os.path.join(os.environ["TEMP"], "modern_spike.txt"), "a", encoding="utf-8") as fh:
        fh.write(message + "\n")


class App(Application, IXamlMetadataProvider):
    def __init__(self) -> None:
        super().__init__()
        self._provider = XamlControlsXamlMetaDataProvider()

    def _on_launched(self, args: LaunchActivatedEventArgs) -> None:
        log("launched")
        self.resources.merged_dictionaries.append(XamlControlsResources())

        window = XamlReader.load(XAML).as_(Window)
        content = window.content.as_(FrameworkElement)
        button = content.find_name("click").as_(Button)
        button.add_click(lambda s, e: log("clicked"))

        window.title = "Modern spike"
        window.activate()
        log("activated")

        timer = window.dispatcher_queue.create_timer()
        timer.interval = datetime.timedelta(seconds=3)
        timer.is_repeating = False

        def tick(sender, event_args) -> None:
            timer.stop()
            log("tick")
            window.close()
            log("closed")
            os._exit(0)

        timer.add_tick(tick)
        timer.start()

    def get_xaml_type(self, type: TypeName | tuple[str, TypeKind]) -> IXamlType:
        return self._provider.get_xaml_type(type)

    def get_xaml_type_by_full_name(self, full_name: str) -> IXamlType:
        return self._provider.get_xaml_type_by_full_name(full_name)

    def get_xmlns_definitions(self) -> Array[XmlnsDefinition]:
        return self._provider.get_xmlns_definitions()


def init(_: ApplicationInitializationCallbackParams) -> None:
    App()


def main() -> int:
    init_apartment(ApartmentType.SINGLE_THREADED)
    with initialize(options=InitializeOptions.ON_NO_MATCH_SHOW_UI):
        Application.start(init)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
