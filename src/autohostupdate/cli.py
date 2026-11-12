"""Headless-интерфейс и elevated-helper."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

from autohostupdate import __version__
from autohostupdate.config.schema import AppSettings
from autohostupdate.config.store import SettingsError, load_settings
from autohostupdate.core.writer import read_hosts
from autohostupdate.errors import AutoHostUpdateError, ElevationRequiredError
from autohostupdate.infrastructure.http import client_from_settings
from autohostupdate.services import backup as backup_service
from autohostupdate.services.logging import get_logger, setup_logging
from autohostupdate.services.privileges import is_admin
from autohostupdate.services.scheduler import (
    install_task,
    task_command,
    task_info,
    uninstall_task,
)
from autohostupdate.services.single_instance import SingleInstance
from autohostupdate.services.updater import Updater

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_SKIPPED = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autohostupdate",
        description="Синхронизация именованных групп hosts с источником GeoHideDNS.",
    )
    parser.add_argument("--version", action="version", version=f"AutoHostUpdate {__version__}")
    parser.add_argument("--config", type=Path, help="Путь к settings.json")
    parser.add_argument("--hosts", type=Path, help="Путь к файлу hosts (для тестов)")
    parser.add_argument("--source", help="URL источника (переопределяет настройки)")
    parser.add_argument(
        "--source-file", type=Path, help="Читать ответ источника из файла (offline/тесты)"
    )
    parser.add_argument("--quiet", action="store_true", help="Без вывода в консоль")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--update", action="store_true", help="Проверить и обновить hosts")
    group.add_argument("--check", action="store_true", help="Только проверить наличие обновления")
    group.add_argument("--install-task", action="store_true", help="Зарегистрировать задачу")
    group.add_argument("--uninstall-task", action="store_true", help="Удалить задачу")
    group.add_argument("--restore", type=Path, metavar="BACKUP", help="Восстановить hosts из копии")
    group.add_argument("--task-status", action="store_true", help="Показать статус задачи")
    parser.add_argument("--dry-run", action="store_true", help="Не записывать изменения")
    parser.add_argument("--json", action="store_true", help="Вывод результата в JSON")
    return parser


def _emit(quiet: bool, payload: dict | str, as_json: bool) -> None:
    if quiet:
        return
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, default=str))
    else:
        print(payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False))


async def _run_update(settings: AppSettings, args: argparse.Namespace, logger) -> int:
    client = client_from_settings(settings)
    source_text: str | None = None
    if getattr(args, "source_file", None):
        source_text = Path(args.source_file).read_text(encoding="utf-8")
    updater = Updater(settings, client, fetcher_text=source_text)

    if args.check:
        snapshot, plan = await updater.plan()
        _emit(
            args.quiet,
            {
                "source_date": snapshot.date_value,
                "local_date": plan.local_date,
                "source_groups": len(snapshot.groups),
                "changed_groups": [change.name for change in plan.changed_groups],
                "update_available": plan.has_changes,
            },
            args.json,
        )
        return EXIT_OK if not plan.has_changes else EXIT_SKIPPED

    dry_run = args.dry_run or settings.update.dry_run_by_default
    if not dry_run and not is_admin():
        raise ElevationRequiredError("Нужны права администратора для изменения hosts.")

    result = await updater.run(dry_run=dry_run)
    _emit(args.quiet, {k: v for k, v in asdict(result).items()}, args.json)
    if result.skipped:
        return EXIT_OK
    if result.dry_run:
        return EXIT_SKIPPED
    logger.info("Обновление завершено: групп=%d", len(result.changed_groups))
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        settings = load_settings(args.config)
    except SettingsError as exc:
        print(f"AutoHostUpdate: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.hosts:
        settings.update.hosts_path = args.hosts
    if args.source:
        settings.source.url = args.source

    setup_logging(settings, console=not args.quiet)
    logger = get_logger()

    try:
        if args.restore:
            backup_service.restore_backup(args.restore, settings.update.hosts_path)
            if settings.update.flush_dns:
                from autohostupdate.services.dns import flush_dns

                flush_dns()
            _emit(args.quiet, f"hosts восстановлен из {args.restore}", args.json)
            return EXIT_OK

        if args.install_task:
            executable, arguments = task_command()
            install_task(executable, settings.schedule, arguments=arguments)
            _emit(
                args.quiet, f"Задача '{settings.schedule.task_name}' зарегистрирована.", args.json
            )
            return EXIT_OK

        if args.uninstall_task:
            removed = uninstall_task(settings.schedule.task_name)
            message = "удалена" if removed else "не найдена"
            _emit(args.quiet, f"Задача '{settings.schedule.task_name}' {message}.", args.json)
            return EXIT_OK

        if args.task_status:
            info = task_info(settings.schedule.task_name)
            _emit(args.quiet, asdict(info) | {"exists": info.exists}, args.json)
            return EXIT_OK

        if args.check or args.update:
            if args.update and not args.dry_run:
                with SingleInstance() as instance:
                    if not instance.acquired:
                        _emit(args.quiet, "Другой экземпляр уже выполняется — пропуск.", args.json)
                        return EXIT_OK
                    return asyncio.run(_run_update(settings, args, logger))
            return asyncio.run(_run_update(settings, args, logger))

        document = read_hosts(settings.update.hosts_path)
        from autohostupdate.core import hosts_parser

        _emit(
            args.quiet,
            {
                "hosts": document.path,
                "lines": len(document.lines),
                "encoding": document.encoding,
                "groups": len(hosts_parser.parse_groups(document.lines)),
            },
            args.json,
        )
        return EXIT_OK
    except AutoHostUpdateError as exc:
        logger.error("%s", exc)
        print(f"AutoHostUpdate: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
