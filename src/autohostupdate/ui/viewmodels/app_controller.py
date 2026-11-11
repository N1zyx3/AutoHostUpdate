"""Состояние приложения и команды для UI (без зависимостей от WinRT).

UI вызывает методы контроллера и подписывается на изменения состояния;
контроллер не знает, как именно рисуется интерфейс.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from autohostupdate.config.schema import AppSettings
from autohostupdate.core import diff, hosts_parser
from autohostupdate.core.models import Group, GroupStatus, SourceSnapshot, UpdatePlan
from autohostupdate.core.writer import read_hosts
from autohostupdate.errors import AutoHostUpdateError
from autohostupdate.infrastructure.http import HttpSourceClient
from autohostupdate.services.logging import get_logger
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


class AppController:
    """Фасад между UI и сервисами."""

    def __init__(self, settings: AppSettings, *, client: HttpSourceClient | None = None) -> None:
        self.settings = settings
        self.client = client or HttpSourceClient(
            url=settings.source.url,
            timeout=settings.source.timeout_seconds,
            retries=settings.source.retries,
        )
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

    # --- команды ---------------------------------------------------------------
    def load_local(self) -> AppState:
        """Читает локальный hosts и заполняет список групп (без сети)."""
        try:
            document = read_hosts(self.settings.update.hosts_path)
        except AutoHostUpdateError as exc:
            self._set_state(last_error=str(exc))
            return self._state

        groups = hosts_parser.parse_groups(document.lines)
        rows = [
            GroupRow(name=group.name, status=GroupStatus.LOCAL_ONLY, local_lines=len(group.lines))
            for group in groups
        ]
        self._set_state(
            hosts_path=document.path,
            local_date=hosts_parser.find_marker(document.lines, self.settings.source.marker_prefix),
            groups=rows,
            last_error=None,
        )
        return self._state

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
            return self._state

    def _updater(self) -> Updater:
        return Updater(self.settings, self.client)

    def _rows_from_plan(self, plan: UpdatePlan) -> list[GroupRow]:
        rows: list[GroupRow] = []
        disabled = set(self.settings.groups.disabled_groups)
        for change in plan.changes:
            rows.append(
                GroupRow(
                    name=change.name,
                    status=change.status,
                    local_lines=len(change.old_lines),
                    source_lines=len(change.new_lines),
                    enabled=change.name not in disabled,
                )
            )
        return rows

    def _fail(self, exc: Exception) -> None:
        self._log.error("%s", exc)
        self._set_state(busy=False, status_text="Ошибка", last_error=str(exc))


def save_settings_to_disk(controller: AppController, target: Path | None = None) -> None:
    """Единая точка сохранения настроек (UI не пишет JSON напрямую)."""
    from autohostupdate.config.store import save_settings

    save_settings(controller.settings, target)
    controller.client = HttpSourceClient(
        url=controller.settings.source.url,
        timeout=controller.settings.source.timeout_seconds,
        retries=controller.settings.source.retries,
    )


def group_source_map(snapshot: SourceSnapshot) -> dict[str, Group]:
    return {group.name: group for group in snapshot.groups}


__all__ = ["AppController", "AppState", "GroupRow", "group_source_map", "save_settings_to_disk"]


def summarize_plan(plan: UpdatePlan) -> str:
    return diff.render_plan(plan)
