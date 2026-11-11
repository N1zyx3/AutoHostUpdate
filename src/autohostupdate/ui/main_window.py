"""Главное окно WinUI 3: XAML + code-behind на PyWinRT."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from autohostupdate import __version__
from autohostupdate.config.schema import AppSettings, LogLevel, ScheduleTrigger
from autohostupdate.config.store import save_settings
from autohostupdate.core.models import GroupStatus
from autohostupdate.errors import AutoHostUpdateError
from autohostupdate.services.logging import get_logger
from autohostupdate.services.privileges import is_admin
from autohostupdate.ui.viewmodels.app_controller import AppController, AppState, GroupRow

STATUS_RU = {
    GroupStatus.UP_TO_DATE: "актуальна",
    GroupStatus.OUTDATED: "устарела",
    GroupStatus.LOCAL_ONLY: "только локально",
    GroupStatus.SOURCE_ONLY: "только в источнике",
}

PAGE_NAMES = {
    "dashboard": "DashboardPage",
    "groups": "GroupsPage",
    "source": "SourcePage",
    "schedule": "SchedulePage",
    "logs": "LogsPage",
    "settings": "SettingsPage",
    "about": "AboutPage",
}

XAML_PATH = Path(__file__).with_name("xaml") / "main_window.xaml"


class MainWindow:
    """Окно и навигация. Сетевые операции выполняются в фоновом потоке."""

    def __init__(self, settings: AppSettings) -> None:
        from winrt.microsoft.ui.xaml import FrameworkElement, Visibility, Window
        from winrt.microsoft.ui.xaml.controls import (
            Button,
            CheckBox,
            ComboBox,
            InfoBar,
            ListView,
            NavigationView,
            ProgressRing,
            StackPanel,
            TextBlock,
            TextBox,
        )
        from winrt.microsoft.ui.xaml.markup import XamlReader
        from winrt.system import unbox_string

        self.settings = settings
        self.controller = AppController(settings)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.log = get_logger()
        self._unbox = unbox_string
        self._visibility = Visibility

        window = XamlReader.load(XAML_PATH.read_text(encoding="utf-8")).as_(Window)
        self.window = window
        self.window.title = f"AutoHostUpdate {__version__}"
        self.root = window.content.as_(FrameworkElement)

        def find(name: str) -> Any:
            return self.root.find_name(name)

        self.nav = find("NavView").as_(NavigationView)
        self.status_bar = find("StatusBar").as_(InfoBar)
        self.status_text = find("StatusText").as_(TextBlock)
        self.source_date_text = find("SourceDateText").as_(TextBlock)
        self.local_date_text = find("LocalDateText").as_(TextBlock)
        self.backup_text = find("BackupText").as_(TextBlock)
        self.busy_ring = find("BusyRing").as_(ProgressRing)
        self.groups_summary = find("GroupsSummary").as_(TextBlock)
        self.groups_list = find("GroupsList").as_(ListView)
        self.source_url_box = find("SourceUrlBox").as_(TextBox)
        self.source_info_text = find("SourceInfoText").as_(TextBlock)
        self.task_name_box = find("TaskNameBox").as_(TextBox)
        self.trigger_combo = find("TriggerCombo").as_(ComboBox)
        self.task_status_text = find("TaskStatusText").as_(TextBlock)
        self.log_box = find("LogBox").as_(TextBox)
        self.run_at_logon_check = find("RunAtLogonCheck").as_(CheckBox)
        self.flush_dns_check = find("FlushDnsCheck").as_(CheckBox)
        self.dry_run_check = find("DryRunCheck").as_(CheckBox)
        self.log_level_combo = find("LogLevelCombo").as_(ComboBox)
        self.settings_status_text = find("SettingsStatusText").as_(TextBlock)

        self._pages = {tag: find(name).as_(StackPanel) for tag, name in PAGE_NAMES.items()}
        self._nav_items: dict[str, Any] = {}

        self._wire(find("CheckButton").as_(Button), lambda: self._submit(self.controller.check))
        self._wire(find("UpdateButton").as_(Button), lambda: self._submit(self.controller.update))
        self._wire(
            find("DryRunButton").as_(Button),
            lambda: self._submit(lambda: self.controller.update(dry_run=True)),
        )
        self._wire(find("RefreshLogsButton").as_(Button), self._refresh_logs)
        self._wire(find("OpenLogsButton").as_(Button), self._open_logs)
        self._wire(find("InstallTaskButton").as_(Button), lambda: self._install_task(True))
        self._wire(find("RemoveTaskButton").as_(Button), lambda: self._install_task(False))
        self._wire(find("SaveSettingsButton").as_(Button), self._save_settings)

        for index, tag in enumerate(PAGE_NAMES):
            self._nav_items[tag] = self.nav.menu_items.get_at(index)
        self.nav.add_item_invoked(self._on_nav_invoked)
        self.nav.selected_item = self._nav_items["dashboard"]

        self._load_settings_into_ui()
        self.window.add_closed(self._on_closed)
        self.controller.subscribe(lambda state: self._ui(lambda: self._render(state)))
        self._render(self.controller.load_local())

    # --- инфраструктура --------------------------------------------------------
    @staticmethod
    def _wire(button: Any, action: Callable[[], None]) -> None:
        button.add_click(lambda sender, args: action())

    def _ui(self, fn: Callable[[], None]) -> None:
        self.window.dispatcher_queue.try_enqueue(lambda: fn())

    def _submit(self, factory: Callable[[], Coroutine[Any, Any, AppState]]) -> None:
        self._set_busy(True, "Выполняется…")

        def job() -> None:
            try:
                asyncio.run(factory())
            except Exception as exc:  # pragma: no cover - защитный контур UI
                self.log.exception("Ошибка операции")
                message = str(exc)
                self._ui(lambda: self._show_error(message))
            finally:
                self._ui(lambda: self._set_busy(False))

        self.executor.submit(job)

    def _set_busy(self, busy: bool, text: str = "") -> None:
        self.busy_ring.is_active = busy
        if text:
            self.status_text.text = text

    def _show_error(self, message: str) -> None:
        self.status_bar.title = "Ошибка"
        self.status_bar.message = message
        self.status_bar.severity = 3
        self.status_bar.is_open = True

    # --- навигация -------------------------------------------------------------
    def _on_nav_invoked(self, sender: Any, args: Any) -> None:
        item = args.invoked_item
        if item is None or item.tag is None:
            return
        self._show_page(self._unbox(item.tag))

    def _show_page(self, tag: str) -> None:
        for name, page in self._pages.items():
            page.visibility = (
                self._visibility.VISIBLE if name == tag else self._visibility.COLLAPSED
            )
        if tag == "logs":
            self._refresh_logs()

    # --- обработчики -----------------------------------------------------------
    def _on_closed(self, sender: Any, args: Any) -> None:
        # Финализация WinRT-объектов после Application.Start падает в PyWinRT,
        # поэтому завершаем процесс сразу после закрытия окна.
        self.executor.shutdown(wait=False)
        logging.shutdown()
        os._exit(0)

    def _install_task(self, install: bool) -> None:
        if not is_admin():
            self.task_status_text.text = (
                "Нужны права администратора. Запустите приложение от имени администратора "
                "или используйте CLI: autohostupdate --install-task"
            )
            return
        from autohostupdate.services.scheduler import install_task, task_info, uninstall_task

        task_name = (self.task_name_box.text or "").strip() or "AutoHostUpdate"
        try:
            if install:
                install_task(sys.executable, self.settings.schedule)
                info = task_info(task_name)
                self.task_status_text.text = (
                    f"Задача '{task_name}' зарегистрирована."
                    if info.exists
                    else "Не удалось найти задачу после регистрации."
                )
            else:
                uninstall_task(task_name)
                self.task_status_text.text = f"Задача '{task_name}' удалена."
        except AutoHostUpdateError as exc:
            self.task_status_text.text = f"Ошибка: {exc}"

    def _load_settings_into_ui(self) -> None:
        self.source_url_box.text = self.settings.source.url
        self.task_name_box.text = self.settings.schedule.task_name
        self.run_at_logon_check.is_checked = self.settings.general.run_at_logon
        self.flush_dns_check.is_checked = self.settings.update.flush_dns
        self.dry_run_check.is_checked = self.settings.update.dry_run_by_default

        triggers = ["at_logon", "daily", "interval", "manual"]
        self.trigger_combo.selected_index = (
            triggers.index(self.settings.schedule.trigger.value)
            if self.settings.schedule.trigger.value in triggers
            else 0
        )
        levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        self.log_level_combo.selected_index = levels.index(self.settings.logging.level.value)

    def _save_settings(self) -> None:
        self.settings.general.run_at_logon = bool(self.run_at_logon_check.is_checked)
        self.settings.update.flush_dns = bool(self.flush_dns_check.is_checked)
        self.settings.update.dry_run_by_default = bool(self.dry_run_check.is_checked)
        url = (self.source_url_box.text or "").strip()
        if url:
            self.settings.source.url = url

        trigger_item = self.trigger_combo.selected_item
        if trigger_item is not None and trigger_item.tag is not None:
            self.settings.schedule.trigger = ScheduleTrigger(self._unbox(trigger_item.tag))

        level_item = self.log_level_combo.selected_item
        if level_item is not None and level_item.tag is not None:
            self.settings.logging.level = LogLevel(self._unbox(level_item.tag))

        try:
            save_settings(self.settings)
        except AutoHostUpdateError as exc:
            self.settings_status_text.text = f"Ошибка сохранения: {exc}"
            return
        self.settings_status_text.text = "Настройки сохранены."
        self.status_bar.title = "Готово"
        self.status_bar.message = "Настройки сохранены"
        self.status_bar.severity = 1
        self.status_bar.is_open = True

    def _open_logs(self) -> None:
        log_path = Path(self.settings.logging.directory) / self.settings.logging.file_name
        if log_path.exists():
            os.startfile(log_path)

    def _refresh_logs(self) -> None:
        log_path = Path(self.settings.logging.directory) / self.settings.logging.file_name
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            self.log_box.text = f"Журнал не найден: {log_path}"
            return
        self.log_box.text = "\n".join(lines[-500:])

    # --- отрисовка -------------------------------------------------------------
    def _render(self, state: AppState) -> None:
        self.status_text.text = state.status_text or "Готово"
        self.source_date_text.text = state.source_date or "—"
        self.local_date_text.text = state.local_date or "—"
        self.backup_text.text = state.last_backup or "—"
        outdated = sum(1 for row in state.groups if row.status is GroupStatus.OUTDATED)
        self.groups_summary.text = f"Всего групп: {len(state.groups)}, к обновлению: {outdated}"
        self.source_info_text.text = (
            f"Дата источника: {state.source_date or '—'}; в hosts: {state.local_date or '—'}"
        )
        self._render_groups(state.groups)

        if state.last_error:
            self.status_bar.title = "Ошибка"
            self.status_bar.message = state.last_error
            self.status_bar.severity = 3
        else:
            self.status_bar.title = "Выполняется" if state.busy else "Готово"
            self.status_bar.message = state.status_text
            self.status_bar.severity = 0 if not state.update_available else 2
        self.status_bar.is_open = True

    def _render_groups(self, groups: list[GroupRow]) -> None:
        from winrt.microsoft.ui.xaml.controls import TextBlock

        self.groups_list.items.clear()
        for row in groups:
            block = TextBlock()
            block.text = (
                f"{row.name} — {STATUS_RU[row.status]} "
                f"({row.local_lines} → {row.source_lines} строк)"
            )
            self.groups_list.items.append(block)

    def show(self) -> None:
        self.window.activate()
        self.log.info("UI запущен")


__all__ = ["MainWindow"]
