from __future__ import annotations

from autohostupdate.ui.viewmodels.app_controller import AppController, AppState


def test_load_local(tmp_path) -> None:
    import shutil
    from pathlib import Path

    from autohostupdate.config.schema import AppSettings

    fixtures = Path(__file__).parent.parent / "fixtures"
    hosts = tmp_path / "hosts"
    shutil.copy(fixtures / "hosts_local.txt", hosts)
    settings = AppSettings()
    settings.update.hosts_path = hosts

    controller = AppController(settings)
    state = controller.load_local()

    assert state.local_date == "2026-10-01 08:00:00"
    assert {row.name for row in state.groups} >= {"Google", "YouTube", "Моя локальная группа"}
    assert state.last_error is None


def test_subscribe_receives_state(tmp_path) -> None:
    import shutil
    from pathlib import Path

    from autohostupdate.config.schema import AppSettings

    fixtures = Path(__file__).parent.parent / "fixtures"
    hosts = tmp_path / "hosts"
    shutil.copy(fixtures / "hosts_local.txt", hosts)
    settings = AppSettings()
    settings.update.hosts_path = hosts

    controller = AppController(settings)
    seen: list[AppState] = []
    controller.subscribe(seen.append)
    controller.load_local()
    assert seen
    assert seen[-1].hosts_path == str(hosts)


async def test_check_uses_cached_source(tmp_path) -> None:
    import shutil
    from pathlib import Path

    from autohostupdate.config.schema import AppSettings

    fixtures = Path(__file__).parent.parent / "fixtures"
    hosts = tmp_path / "hosts"
    shutil.copy(fixtures / "hosts_local.txt", hosts)
    settings = AppSettings()
    settings.update.hosts_path = hosts
    source_text = (fixtures / "source.txt").read_text(encoding="utf-8")

    controller = AppController(settings)
    controller._updater = lambda: _updater_with(settings, controller, source_text)  # type: ignore[method-assign]

    state = await controller.check()
    assert state.update_available
    assert state.source_date == "2026-11-09 10:00:00"
    assert state.status_text.startswith("Доступно обновление")


def _updater_with(settings, controller, text):
    from autohostupdate.services.updater import Updater

    return Updater(settings, controller.client, fetcher_text=text)  # type: ignore[arg-type]
