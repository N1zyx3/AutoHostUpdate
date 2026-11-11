"""Acceptance-сценарий R8 без прав администратора и без сети.

Проверяет полный цикл CLI на временной копии hosts:
check -> dry-run -> update -> backup -> restore + статус задачи.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from autohostupdate import cli

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    hosts = tmp_path / "hosts"
    shutil.copy(FIXTURES / "hosts_local.txt", hosts)
    source_file = tmp_path / "source.txt"
    shutil.copy(FIXTURES / "source.txt", source_file)
    settings_path = tmp_path / "settings.json"
    backups = tmp_path / "backups"
    logs = tmp_path / "logs"

    from autohostupdate.config.schema import AppSettings

    settings = AppSettings()
    settings.update.hosts_path = hosts
    settings.update.backup_dir = backups
    settings.logging.directory = logs
    settings.advanced.settings_path = settings_path
    settings_path.write_text(settings.model_dump_json(), encoding="utf-8")

    monkeypatch.setattr(cli, "is_admin", lambda: True)
    return {
        "hosts": hosts,
        "source": source_file,
        "settings": settings_path,
        "backups": backups,
        "root": tmp_path,
    }


def run(env: dict[str, Path], *args: str) -> int:
    return cli.main(
        [
            "--config",
            str(env["settings"]),
            "--hosts",
            str(env["hosts"]),
            "--source-file",
            str(env["source"]),
            "--quiet",
            *args,
        ]
    )


def test_full_acceptance_cycle(env: dict[str, Path]) -> None:
    hosts = env["hosts"]
    original = hosts.read_text(encoding="utf-8")

    # 1. check: обновление доступно -> код 2
    assert run(env, "--check") == cli.EXIT_SKIPPED

    # 2. dry-run: файл не меняется -> код 2
    assert run(env, "--update", "--dry-run") == cli.EXIT_SKIPPED
    assert hosts.read_text(encoding="utf-8") == original

    # 3. update: файл обновлён, дата источника записана
    assert run(env, "--update") == cli.EXIT_OK
    updated = hosts.read_text(encoding="utf-8-sig")
    assert "2026-11-09 10:00:00" in updated
    assert "www.google.com" in updated

    # 4. повторный update: обновление не требуется
    assert run(env, "--update") == cli.EXIT_OK

    # 5. backup создан, restore возвращает исходное содержимое
    backups = sorted(env["backups"].glob("*.bak"))
    assert backups, "резервная копия не создана"
    assert run(env, "--restore", str(backups[-1])) == cli.EXIT_OK
    assert hosts.read_text(encoding="utf-8") == original


def test_check_reports_json_payload(
    env: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(
        [
            "--config",
            str(env["settings"]),
            "--hosts",
            str(env["hosts"]),
            "--source-file",
            str(env["source"]),
            "--check",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out.strip())

    assert code == cli.EXIT_SKIPPED
    assert payload["source_date"] == "2026-11-09 10:00:00"
    assert payload["update_available"] is True
    assert set(payload["changed_groups"]) == {"Google", "YouTube"}


def test_task_status_works_without_admin(env: dict[str, Path], capsys, monkeypatch) -> None:
    from autohostupdate.services.scheduler import TaskInfo

    monkeypatch.setattr(
        cli, "task_info", lambda name: TaskInfo(name=name, path="", state=None, enabled=False)
    )

    code = cli.main(
        [
            "--config",
            str(env["settings"]),
            "--hosts",
            str(env["hosts"]),
            "--task-status",
            "--json",
        ]
    )
    assert code == cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["exists"] is False


def test_install_task_uses_module_invocation(env: dict[str, Path], monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_install(executable: str, settings, *, arguments: str = "") -> None:
        captured["executable"] = executable
        captured["arguments"] = arguments

    monkeypatch.setattr(cli, "install_task", fake_install)

    assert run(env, "--install-task") == cli.EXIT_OK
    assert captured["arguments"] == "-m autohostupdate --update --quiet"
