"""Состояние приложения и команды для UI (без зависимостей от WinRT).

UI вызывает методы контроллера и подписывается на изменения состояния;
контроллер не знает, как именно рисуется интерфейс.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from autohostupdate import __version__
from autohostupdate.config.schema import AppSettings
from autohostupdate.core import diff, hosts_parser
from autohostupdate.core.models import Group, GroupStatus, SourceSnapshot, UpdatePlan
from autohostupdate.core.source import parse_source
from autohostupdate.core.writer import read_hosts
from autohostupdate.errors import AutoHostUpdateError
from autohostupdate.infrastructure.http import HttpSourceClient, client_from_settings
from autohostupdate.services import logging as log_service
from autohostupdate.services.logging import LogQuery, get_logger
from autohostupdate.services.updater import Updater

Listener = Callable[["AppState"], None]


@dataclass(slots=True)
class GroupRow:
    """Строка страницы Groups."""

    name: str
    status: GroupStatus
    local_lines: int = 0
    source_lines: int = 0
    enabled: bool = True


@dataclass(slots=True)
class SourceProbe:
    """Результат «Проверить соединение» на странице «Источник»."""

    url: str
    date: str
    group_count: int
    total_lines: int
    preview: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TaskSnapshot:
    """Состояние задачи в Планировщике."""

    name: str
    exists: bool
    enabled: bool = False
    state_text: str = ""


@dataclass(slots=True)
class BackupRow:
    """Строка списка резервных копий."""

    path: Path
    created: str
    size_bytes: int = 0


@dataclass(slots=True)
class AppState:
    """Снимок состояния для отрисовки."""

    busy: bool = False
    status_text: str = ""
    source_date: str = ""
    local_date: str = ""
    hosts_path: str = ""
    groups: list[GroupRow] = field(default_factory=list)
    update_available: bool = False
    last_error: str | None = None
    last_backup: str | None = None
    source_groups: int = 0
    source_preview: list[str] = field(default_factory=list)
    task: TaskSnapshot | None = None


def build_client(settings: AppSettings) -> HttpSourceClient:
    """Создаёт HTTP-клиент строго по секции `source` настроек."""
    return client_from_settings(settings)


class AppController:
    """Фасад между UI и сервисами."""

    def __init__(self, settings: AppSettings, *, client: HttpSourceClient | None = None) -> None:
        self.settings = settings
        self.client = client or build_client(settings)
        self._log = get_logger()
        self._listeners: list[Listener] = []
        self._lock = asyncio.Lock()
        self._state = AppState(hosts_path=str(settings.update.hosts_path))
        self._snapshot: SourceSnapshot | None = None
        self._plan: UpdatePlan | None = None

    # --- подписка на состояние -------------------------------------------------
    @property
    def state(self) -> AppState:
        return self._state

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        self._listeners.append(listener)
        listener(self._state)
        return lambda: self._listeners.remove(listener)

    def _set_state(self, **changes: object) -> None:
        self._state = replace(self._state, **changes)  # type: ignore[arg-type]
        for listener in list(self._listeners):
            listener(self._state)

    # --- локальное состояние ---------------------------------------------------
    def load_local(self) -> AppState:
        """Читает локальный hosts и заполняет список групп (без сети)."""
        try:
            document = read_hosts(self.settings.update.hosts_path)
        except AutoHostUpdateError as exc:
            self._set_state(last_error=str(exc))
            return self._state

        groups = hosts_parser.parse_groups(document.lines)
        disabled = self._disabled_keys()
        rows = [
            GroupRow(
                name=group.name,
                status=GroupStatus.LOCAL_ONLY,
                local_lines=len(group.lines),
                enabled=group.name.casefold() not in disabled,
            )
            for group in groups
        ]
        self._set_state(
            hosts_path=document.path,
            local_date=hosts_parser.find_marker(document.lines, self.settings.source.marker_prefix),
            groups=rows,
            source_groups=0,
            last_error=None,
        )
        return self._state

    # --- сетевые команды -------------------------------------------------------
    async def check(self) -> AppState:
        """Проверяет наличие обновлений, ничего не записывая."""
        async with self._lock:
            self._set_state(busy=True, status_text="Проверка источника…", last_error=None)
            try:
                updater = self._updater()
                snapshot, plan = await updater.plan()
                self._snapshot, self._plan = snapshot, plan
                rows = self._rows_from_plan(plan)
                self._set_state(
                    busy=False,
                    status_text=(
                        f"Доступно обновление: {plan.changed_count} групп"
                        if plan.changed_count
                        else "Обновление не требуется"
                    ),
                    source_date=snapshot.date_value,
                    local_date=plan.local_date,
                    groups=rows,
                    source_groups=len(snapshot.groups),
                    update_available=plan.has_changes,
                )
            except AutoHostUpdateError as exc:
                self._fail(exc)
            except Exception as exc:  # pragma: no cover - защитный контур для UI
                self._fail(exc)
            return self._state

    async def update(self, *, dry_run: bool = False) -> AppState:
        """Выполняет обновление (или dry-run) и обновляет состояние."""
        async with self._lock:
            self._set_state(busy=True, status_text="Обновление…", last_error=None)
            try:
                result = await self._updater().run(dry_run=dry_run)
                if result.skipped:
                    text = f"Обновление не требуется: {result.skipped_reason}"
                elif result.dry_run:
                    text = f"Dry-run: изменилось бы групп: {len(result.changed_groups)}"
                else:
                    text = f"Обновлено групп: {len(result.changed_groups)}"
                self._set_state(busy=False, status_text=text, last_backup=result.backup_path)
                self.load_local()
            except AutoHostUpdateError as exc:
                self._fail(exc)
            except Exception as exc:  # pragma: no cover - защитный контур для UI
                self._fail(exc)
            return self._state

    async def probe_source(self) -> SourceProbe:
        """Скачивает источник и возвращает статистику + предпросмотр (без записи)."""
        result = await self.client.fetch()
        snapshot = parse_source(result.text, url=self.settings.source.url)
        preview = result.text.splitlines()[:40]
        probe = SourceProbe(
            url=self.client.url,
            date=snapshot.date_value,
            group_count=len(snapshot.groups),
            total_lines=len(result.text.splitlines()),
            preview=preview,
        )
        self._set_state(
            source_date=snapshot.date_value,
            source_groups=probe.group_count,
            source_preview=preview,
        )
        return probe

    # --- группы ----------------------------------------------------------------
    def set_group_enabled(self, name: str, enabled: bool) -> AppState:
        """Включает/выключает обновление группы и сохраняет настройки."""
        disabled = self.settings.groups.disabled_groups
        if enabled:
            self.settings.groups.disabled_groups = [
                item for item in disabled if item.casefold() != name.casefold()
            ]
        elif all(item.casefold() != name.casefold() for item in disabled):
            self.settings.groups.disabled_groups = [*disabled, name]

        try:
            save_settings_to_disk(self)
        except AutoHostUpdateError as exc:
            self._fail(exc)
            return self._state

        rows = [
            replace(row, enabled=enabled) if row.name == name else row for row in self._state.groups
        ]
        self._set_state(groups=rows)
        return self._state

    def set_group_forced(self, name: str, enabled: bool) -> AppState:
        """Включает/выключает принудительное добавление группы из источника."""
        forced = self.settings.groups.force_add_groups
        if enabled:
            if all(item.casefold() != name.casefold() for item in forced):
                self.settings.groups.force_add_groups = [*forced, name]
        else:
            self.settings.groups.force_add_groups = [
                item for item in forced if item.casefold() != name.casefold()
            ]

        try:
            save_settings_to_disk(self)
        except AutoHostUpdateError as exc:
            self._fail(exc)
            return self._state

        rows = [
            replace(row, enabled=enabled) if row.name == name else row for row in self._state.groups
        ]
        self._set_state(groups=rows)
        return self._state

    # --- резервные копии -------------------------------------------------------
    def list_backups(self) -> list[BackupRow]:
        """Список резервных копий hosts, новые сверху."""
        from autohostupdate.services import backup as backup_service

        rows: list[BackupRow] = []
        for path in backup_service.list_backups(self.settings.update.backup_dir):
            stat = path.stat()
            rows.append(
                BackupRow(
                    path=path,
                    created=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    size_bytes=stat.st_size,
                )
            )
        return rows

    def restore_backup(self, backup_path: str | Path) -> AppState:
        """Восстанавливает hosts из выбранной копии и обновляет состояние."""
        from autohostupdate.services import backup as backup_service
        from autohostupdate.services.dns import flush_dns

        backup_service.restore_backup(backup_path, self.settings.update.hosts_path)
        if self.settings.update.flush_dns:
            flush_dns()
        name = Path(backup_path).name
        self._log.info("hosts восстановлен из %s", name)
        self.load_local()
        self._set_state(status_text=f"hosts восстановлен из {name}", last_error=None)
        return self._state

    # --- планировщик -----------------------------------------------------------
    def task_snapshot(self) -> TaskSnapshot:
        """Читает состояние задачи. Не требует прав администратора."""
        from autohostupdate.services.scheduler import task_info

        name = self.settings.schedule.task_name
        try:
            info = task_info(name)
        except AutoHostUpdateError as exc:
            snapshot = TaskSnapshot(name=name, exists=False, state_text=str(exc))
        else:
            snapshot = TaskSnapshot(
                name=info.name,
                exists=info.exists,
                enabled=info.enabled,
                state_text=_task_state_text(info.state),
            )
        self._set_state(task=snapshot)
        return snapshot

    def install_task(self) -> TaskSnapshot:
        from autohostupdate.services.scheduler import install_task, task_command

        executable, arguments = task_command()
        install_task(executable, self.settings.schedule, arguments=arguments)
        return self.task_snapshot()

    def uninstall_task(self) -> TaskSnapshot:
        from autohostupdate.services.scheduler import uninstall_task

        uninstall_task(self.settings.schedule.task_name)
        return self.task_snapshot()

    def run_task(self) -> None:
        from autohostupdate.services.scheduler import run_task

        run_task(self.settings.schedule.task_name)

    # --- журнал ----------------------------------------------------------------
    @property
    def log_path(self) -> Path:
        return Path(self.settings.logging.directory) / self.settings.logging.file_name

    def read_logs(self, query: LogQuery | None = None) -> list[str]:
        return log_service.read_log_tail(self.log_path, query or LogQuery(limit=500))

    def clear_logs(self) -> None:
        log_service.clear_log(self.log_path)

    def export_diagnostics(self, destination: str | Path) -> Path:
        return log_service.export_diagnostics(
            destination, self.log_path, self.settings, version=__version__
        )

    # --- настройки -------------------------------------------------------------
    def save_settings(self, updated: AppSettings | None = None) -> AppState:
        """Сохраняет настройки на диск и пересоздаёт HTTP-клиент."""
        if updated is not None:
            self.settings = updated
        save_settings_to_disk(self)
        return self._state

    # --- внутреннее ------------------------------------------------------------
    def _disabled_keys(self) -> set[str]:
        groups = self.settings.groups
        if groups.ignore_case:
            return {name.casefold() for name in groups.disabled_groups}
        return set(groups.disabled_groups)

    def _updater(self) -> Updater:
        return Updater(self.settings, self.client)

    def _rows_from_plan(self, plan: UpdatePlan) -> list[GroupRow]:
        disabled = self._disabled_keys()
        ignore_case = self.settings.groups.ignore_case
        force = {
            name.casefold() if ignore_case else name
            for name in self.settings.groups.force_add_groups
        }
        rows: list[GroupRow] = []
        for change in plan.changes:
            key = change.name.casefold() if ignore_case else change.name
            enabled = (
                key in force if change.status is GroupStatus.SOURCE_ONLY else key not in disabled
            )
            rows.append(
                GroupRow(
                    name=change.name,
                    status=change.status,
                    local_lines=len(change.old_lines),
                    source_lines=len(change.new_lines),
                    enabled=enabled,
                )
            )
        return rows

    def _fail(self, exc: Exception) -> None:
        self._log.error("%s", exc)
        self._set_state(busy=False, status_text="Ошибка", last_error=str(exc))


_TASK_STATES = {
    0: "неизвестно",
    1: "отключена",
    2: "в очереди",
    3: "выполняется",
    4: "готова",
}


def _task_state_text(state: int | None) -> str:
    if state is None:
        return ""
    return _TASK_STATES.get(state, f"состояние {state}")


def save_settings_to_disk(controller: AppController, target: Path | None = None) -> None:
    """Единая точка сохранения настроек (UI не пишет JSON напрямую)."""
    from autohostupdate.config.store import save_settings

    save_settings(controller.settings, target)
    controller.client = build_client(controller.settings)


def group_source_map(snapshot: SourceSnapshot) -> dict[str, Group]:
    return {group.name: group for group in snapshot.groups}


def summarize_plan(plan: UpdatePlan) -> str:
    return diff.render_plan(plan)


__all__ = [
    "AppController",
    "AppState",
    "BackupRow",
    "GroupRow",
    "SourceProbe",
    "TaskSnapshot",
    "build_client",
    "group_source_map",
    "save_settings_to_disk",
    "summarize_plan",
]
