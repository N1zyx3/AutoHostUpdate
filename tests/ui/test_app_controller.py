from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from autohostupdate.config.schema import AppSettings, ProxyMode
from autohostupdate.core.models import GroupStatus
from autohostupdate.services.logging import LogQuery
from autohostupdate.ui.viewmodels.app_controller import AppController, build_client

FIXTURES = Path(__file__).parent.parent / "fixtures"


def make_settings(tmp_path: Path) -> AppSettings:
    hosts = tmp_path / "hosts"
    shutil.copy(FIXTURES / "hosts_local.txt", hosts)
    settings = AppSettings()
    settings.update.hosts_path = hosts
    settings.update.backup_dir = tmp_path / "backups"
    settings.logging.directory = tmp_path / "logs"
    settings.advanced.settings_path = tmp_path / "settings.json"
    return settings


def test_load_local(tmp_path) -> None:
    settings = make_settings(tmp_path)

    controller = AppController(settings)
    state = controller.load_local()

    assert state.local_date == "2026-10-01 08:00:00"
    assert {row.name for row in state.groups} >= {"Google", "YouTube", "Моя локальная группа"}
    assert state.last_error is None


def test_subscribe_receives_state(tmp_path) -> None:
    settings = make_settings(tmp_path)

    controller = AppController(settings)
    seen: list = []
    controller.subscribe(seen.append)
    controller.load_local()

    assert seen
    assert seen[-1].hosts_path == str(settings.update.hosts_path)


def test_build_client_uses_source_settings() -> None:
    settings = AppSettings()
    settings.source.url = "https://example.com/hosts"
    settings.source.timeout_seconds = 12.0
    settings.source.retries = 4
    settings.source.max_response_kb = 64
    settings.source.verify_tls = False
    settings.source.user_agent = "Agent"

    client = build_client(settings)

    assert client.url == "https://example.com/hosts"
    assert client.timeout == 12.0
    assert client.retries == 4
    assert client.max_bytes == 64 * 1024
    assert client.verify_tls is False
    assert client.user_agent.startswith("Agent/")


def test_build_client_respects_proxy_mode() -> None:
    settings = AppSettings()
    settings.source.proxy_mode = ProxyMode.NONE

    client = build_client(settings)

    assert client.trust_env is False
    assert client.proxy is None

    settings.source.proxy_mode = ProxyMode.MANUAL
    settings.source.proxy_url = "http://127.0.0.1:8888"
    manual = build_client(settings)
    assert manual.proxy == "http://127.0.0.1:8888"
    assert manual.trust_env is False


def test_set_group_enabled_persists_and_updates_state(tmp_path) -> None:
    settings = make_settings(tmp_path)
    controller = AppController(settings)
    controller.load_local()

    controller.set_group_enabled("Google", False)

    assert "Google" in controller.settings.groups.disabled_groups
    reloaded = AppSettings.model_validate_json(
        (tmp_path / "settings.json").read_text(encoding="utf-8")
    )
    assert "Google" in reloaded.groups.disabled_groups
    row = next(row for row in controller.state.groups if row.name == "Google")
    assert row.enabled is False

    controller.set_group_enabled("Google", True)
    assert "Google" not in controller.settings.groups.disabled_groups
    row = next(row for row in controller.state.groups if row.name == "Google")
    assert row.enabled is True


def test_set_group_enabled_is_idempotent(tmp_path) -> None:
    settings = make_settings(tmp_path)
    controller = AppController(settings)

    controller.set_group_enabled("Google", False)
    controller.set_group_enabled("Google", False)

    assert controller.settings.groups.disabled_groups == ["Google"]


async def test_plan_marks_disabled_groups(tmp_path) -> None:
    settings = make_settings(tmp_path)
    controller = AppController(settings)
    controller.load_local()
    controller.set_group_enabled("Google", False)
    source_text = (FIXTURES / "source.txt").read_text(encoding="utf-8")
    controller._updater = lambda: _updater_with(settings, controller, source_text)  # type: ignore[method-assign]

    state = await controller.check()

    statuses = {row.name: row.status for row in state.groups}
    assert statuses["Google"] is GroupStatus.DISABLED
    assert statuses["YouTube"] is GroupStatus.OUTDATED
    google = next(row for row in state.groups if row.name == "Google")
    assert google.enabled is False


async def test_probe_source_returns_preview(tmp_path) -> None:
    settings = make_settings(tmp_path)
    source_text = (FIXTURES / "source.txt").read_text(encoding="utf-8")

    class FakeClient:
        url = settings.source.url

        async def fetch(self, *, etag=None):
            from autohostupdate.infrastructure.http import FetchResult

            return FetchResult(text=source_text)

    controller = AppController(settings, client=FakeClient())  # type: ignore[arg-type]

    probe = await controller.probe_source()

    assert probe.group_count == 4
    assert probe.date == "2026-11-09 10:00:00"
    assert probe.preview[0].startswith("# GeoHide DNS hosts")
    assert controller.state.source_groups == 4


def test_read_and_clear_logs(tmp_path) -> None:
    settings = make_settings(tmp_path)
    log_dir = Path(settings.logging.directory)
    log_dir.mkdir(parents=True)
    log_file = log_dir / settings.logging.file_name
    log_file.write_text(
        "2026-11-11 10:00:00,000  INFO  ok\n2026-11-11 10:00:01,000  ERROR  bad\n",
        encoding="utf-8",
    )
    controller = AppController(settings)

    assert len(controller.read_logs()) == 2
    assert controller.read_logs(LogQuery(level="ERROR")) == ["2026-11-11 10:00:01,000  ERROR  bad"]

    controller.clear_logs()
    assert controller.read_logs() == []


def test_export_diagnostics_creates_zip(tmp_path) -> None:
    settings = make_settings(tmp_path)
    log_dir = Path(settings.logging.directory)
    log_dir.mkdir(parents=True)
    (log_dir / settings.logging.file_name).write_text("line\n", encoding="utf-8")
    controller = AppController(settings)

    target = controller.export_diagnostics(tmp_path / "diag.zip")

    assert target.is_file()
    assert target.stat().st_size > 0


def test_task_snapshot_reports_failure_without_windows_api(tmp_path, monkeypatch) -> None:
    settings = make_settings(tmp_path)
    controller = AppController(settings)

    def boom(name: str):
        from autohostupdate.errors import TaskSchedulerError

        raise TaskSchedulerError("нет доступа")

    monkeypatch.setattr("autohostupdate.services.scheduler.task_info", boom)

    snapshot = controller.task_snapshot()

    assert snapshot.exists is False
    assert "нет доступа" in snapshot.state_text


@pytest.mark.parametrize("name", ["Google", "YouTube"])
def test_is_enabled_uses_case_insensitive_keys(tmp_path, name: str) -> None:
    settings = make_settings(tmp_path)
    settings.groups.ignore_case = True
    settings.groups.disabled_groups = ["google"]
    controller = AppController(settings)

    state = controller.load_local()

    row = next(row for row in state.groups if row.name == name)
    assert row.enabled is (name != "Google")


def _updater_with(settings, controller, text):
    from autohostupdate.services.updater import Updater

    return Updater(settings, controller.client, fetcher_text=text)  # type: ignore[arg-type]
