"""Sprint 0 / R1 spike (вариант B): UI строится программно, без XamlReader."""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main() -> int:
    from winui3.microsoft.windows.applicationmodel.dynamicdependency import bootstrap

    options = bootstrap.InitializeOptions.NONE
    try:
        context = bootstrap.initialize(options=options)
        print("runtime: default", flush=True)
    except OSError as exc:
        print("runtime: default failed:", exc, flush=True)
        context = bootstrap.initialize("1.8", "8000.0.0.0", options)
        print("runtime: 1.8 fallback", flush=True)

    with context:
        from winrt import system
        from winui3.microsoft.ui.xaml import Application, Thickness, Window
        from winui3.microsoft.ui.xaml.controls import (
            NavigationView,
            NavigationViewItem,
            ProgressRing,
            StackPanel,
            TextBlock,
        )

        class App(Application):
            def _on_launched(self, args) -> None:
                window = Window()
                window.title = "AutoHostUpdate spike"

                nav = NavigationView()
                nav.pane_display_mode = 0  # Left
                nav.is_settings_visible = False

                def make_item(text: str, tag: str):
                    label = TextBlock()
                    label.text = text
                    item = NavigationViewItem()
                    item.content = label
                    item.tag = system.box_string(tag)
                    return item

                nav.menu_items.append(make_item("Обзор", "dashboard"))
                nav.menu_items.append(make_item("Группы", "groups"))

                panel = StackPanel()
                panel.padding = Thickness(24, 24, 24, 24)
                title = TextBlock()
                title.text = "AutoHostUpdate — программный UI OK"
                title.font_size = 28
                ring = ProgressRing()
                ring.is_active = True
                ring.width = 24
                ring.height = 24
                panel.children.append(title)
                panel.children.append(ring)
                nav.content = panel

                window.content = nav
                window.activate()
                print("SPIKE: window activated", flush=True)

                timer = window.dispatcher_queue.create_timer()
                timer.interval = datetime.timedelta(seconds=3)
                timer.is_repeating = False

                def tick(sender, args) -> None:
                    timer.stop()
                    window.close()
                    Application.exit()

                timer.add_tick(tick)
                timer.start()

        Application.start(lambda params: App())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
