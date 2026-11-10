from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from autohostupdate.config.schema import AppSettings
from autohostupdate.infrastructure.http import FetchResult
from autohostupdate.services import backup as backup_service
from autohostupdate.services.updater import Updater

FIXTURES = Path(__file__).parent.parent / "fixtures"


class FakeClient:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    async def fetch(self, *, etag: str | None = None) -> FetchResult:
        self.calls += 1
        return FetchResult(text=self.text, etag='"abc"')


def make_settings(tmp_path: Path, *, dry_run: bool = False) -> AppSettings:
    settings = AppSettings()
    settings.update.hosts_path = tmp_path / "hosts"
    settings.update.backup_dir = tmp_path / "backups"
    settings.update.flush_dns = False
    settings.update.dry_run_by_default = dry_run
    return settings


@pytest.fixture()
def hosts_file(tmp_path: Path) -> Path:
    target = tmp_path / "hosts"
    shutil.copy(FIXTURES / "hosts_local.txt", target)
    return target


@pytest.fixture()
def source_text() -> str:
    return (FIXTURES / "source.txt").read_text(encoding="utf-8")


async def test_update_writes_groups_and_backup(tmp_path, hosts_file, source_text) -> None:
    settings = make_settings(tmp_path)
    updater = Updater(settings, FakeClient(source_text))  # type: ignore[arg-type]

    result = await updater.run()

    assert result.written
    assert set(result.changed_groups) == {"Google", "YouTube"}
    assert result.backup_path is not None
    assert Path(result.backup_path).exists()
    text = hosts_file.read_text(encoding="utf-8-sig")
    assert "142.250.74.46 www.google.com" in text
    assert "2026-11-09 10:00:00" in text
    assert "nas.local" in text


async def test_dry_run_does_not_touch_file(tmp_path, hosts_file, source_text) -> None:
    settings = make_settings(tmp_path, dry_run=True)
    before = hosts_file.read_bytes()
    updater = Updater(settings, FakeClient(source_text))  # type: ignore[arg-type]

    result = await updater.run()

    assert result.dry_run
    assert not result.written
    assert hosts_file.read_bytes() == before
    assert not (tmp_path / "backups").exists()


async def test_second_run_is_skipped(tmp_path, hosts_file, source_text) -> None:
    settings = make_settings(tmp_path)
    updater = Updater(settings, FakeClient(source_text))  # type: ignore[arg-type]
    await updater.run()

    second = await updater.run()
    assert second.skipped
    assert not second.written


async def test_check_mode_plan(tmp_path, hosts_file, source_text) -> None:
    settings = make_settings(tmp_path)
    updater = Updater(settings, FakeClient(source_text))  # type: ignore[arg-type]

    snapshot, plan = await updater.plan()
    assert snapshot.date_value == "2026-11-09 10:00:00"
    assert plan.changed_count == 2


def test_backup_rotation(tmp_path) -> None:
    directory = tmp_path / "backups"
    directory.mkdir()
    now = datetime(2026, 11, 10, 12, 0, 0)
    for index in range(5):
        path = directory / f"hosts_2026110{index}_120000.bak"
        path.write_text("x", encoding="utf-8")
        stamp = (now - timedelta(days=index)).timestamp()
        import os

        os.utime(path, (stamp, stamp))

    removed = backup_service.prune_backups(directory, keep_count=2, keep_days=30, now=now)
    assert len(removed) == 3
    assert len(backup_service.list_backups(directory)) == 2


def test_restore_backup(tmp_path) -> None:
    hosts = tmp_path / "hosts"
    hosts.write_text("original", encoding="utf-8")
    backup = backup_service.create_backup(hosts, tmp_path / "backups")
    hosts.write_text("changed", encoding="utf-8")

    backup_service.restore_backup(backup, hosts)
    assert hosts.read_text(encoding="utf-8") == "original"
