"""Оркестрация полного цикла: fetch -> parse -> compare -> backup -> write -> flush."""

from __future__ import annotations

from pathlib import Path

from autohostupdate.config.schema import AppSettings, UpdateMode
from autohostupdate.core import diff
from autohostupdate.core.models import SourceSnapshot, UpdatePlan, UpdateResult
from autohostupdate.core.source import parse_source
from autohostupdate.core.writer import clear_readonly, read_hosts, write_hosts
from autohostupdate.errors import HostsWriteError, SourceUnavailableError
from autohostupdate.infrastructure.http import FetchResult, HttpSourceClient
from autohostupdate.services import backup as backup_service
from autohostupdate.services.dns import flush_dns
from autohostupdate.services.logging import get_logger


class Updater:
    """Высокоуровневый сценарий обновления hosts."""

    def __init__(
        self,
        settings: AppSettings,
        client: HttpSourceClient,
        *,
        hosts_path: str | Path | None = None,
        fetcher_text: str | None = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.hosts_path = Path(hosts_path) if hosts_path else Path(settings.update.hosts_path)
        self._fetcher_text = fetcher_text
        self._etag: str | None = None
        self._log = get_logger()

    async def fetch_snapshot(self) -> SourceSnapshot:
        if self._fetcher_text is not None:
            text = self._fetcher_text
        else:
            result: FetchResult = await self.client.fetch(etag=self._etag)
            if result.not_modified and self._etag:
                raise SourceUnavailableError("Источник ответил 304 при отсутствии локальной копии.")
            self._etag = result.etag
            text = result.text
        return parse_source(
            text,
            url=self.settings.source.url,
            require_date=self.settings.source.marker_line_index == 2,
        )

    async def plan(self) -> tuple[SourceSnapshot, UpdatePlan]:
        snapshot = await self.fetch_snapshot()
        document = read_hosts(self.hosts_path)
        groups = self.settings.groups
        plan = diff.build_plan(
            document.lines,
            snapshot,
            self.settings.source.marker_prefix,
            skip_names=groups.disabled_groups,
            force_add_names=groups.force_add_groups,
            ignore_case=groups.ignore_case,
        )
        return snapshot, plan

    async def run(self, *, dry_run: bool | None = None) -> UpdateResult:
        settings = self.settings
        is_dry_run = settings.update.dry_run_by_default if dry_run is None else dry_run

        snapshot, plan = await self.plan()
        self._log.info(
            "Источник: дата=%s, групп=%d; локально дата=%s; к обновлению=%d",
            snapshot.date_value or "—",
            len(snapshot.groups),
            plan.local_date or "—",
            plan.changed_count,
        )

        skip_reason = self._skip_reason(plan)
        if skip_reason:
            self._log.info("Обновление не требуется: %s", skip_reason)
            return UpdateResult(
                source_date=snapshot.date_value,
                previous_date=plan.local_date,
                skipped_reason=skip_reason,
                dry_run=is_dry_run,
            )

        changed_names = tuple(change.name for change in plan.changed_groups)
        if is_dry_run:
            self._log.info(
                "Dry-run: запись не выполняется, изменилось групп: %d", len(changed_names)
            )
            return UpdateResult(
                source_date=snapshot.date_value,
                previous_date=plan.local_date,
                changed_groups=changed_names,
                dry_run=True,
            )

        hosts_path = self.hosts_path
        backup_path: Path | None = None
        if settings.update.create_backup:
            backup_path = backup_service.create_backup(hosts_path, settings.update.backup_dir)
            self._log.info("Резервная копия: %s", backup_path)

        try:
            if settings.update.clear_readonly:
                clear_readonly(hosts_path)
            write_hosts(
                hosts_path,
                plan.new_lines,
                encoding=settings.update.encoding,
                newline=settings.update.newline,
                final_newline=settings.update.final_newline,
                validate=settings.update.validate_before_replace,
            )
        except HostsWriteError:
            if backup_path and settings.update.restore_backup_on_error:
                self._log.error("Ошибка записи, восстанавливаю hosts из %s", backup_path)
                backup_service.restore_backup(backup_path, hosts_path)
            raise

        self._log.info("hosts записан: %d строк", len(plan.new_lines))
        if settings.update.flush_dns:
            flush_dns()
        self._prune_backups()

        return UpdateResult(
            source_date=snapshot.date_value,
            previous_date=plan.local_date,
            changed_groups=changed_names,
            backup_path=str(backup_path) if backup_path else None,
            written=True,
            dry_run=False,
        )

    def _skip_reason(self, plan: UpdatePlan) -> str | None:
        update = self.settings.update
        if update.compare_mode is UpdateMode.HASH:
            if not plan.has_changes:
                return "содержимое групп совпадает"
            return None
        if plan.local_date and plan.local_date == plan.source_date:
            return f"дата совпадает ({plan.local_date})"
        if not plan.changed_count and plan.local_date:
            return "группы совпадают"
        return None

    def _prune_backups(self) -> None:
        removed = backup_service.prune_backups(
            self.settings.update.backup_dir,
            keep_count=self.settings.update.backup_keep_count,
            keep_days=self.settings.update.backup_keep_days,
        )
        if removed:
            self._log.info("Удалено старых копий: %d", len(removed))
