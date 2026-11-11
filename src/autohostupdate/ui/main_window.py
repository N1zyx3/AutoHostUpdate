"""Главное окно WinUI 3 (строится программно: XamlReader не видит winui3-контролы)."""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from autohostupdate import __version__
from autohostupdate.config.schema import AppSettings
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

PAGE_TITLES = {
    "dashboard": "Обзор",
    "groups": "Группы",
    "source": "Источник",
    "schedule": "Расписание",
    "logs": "Журнал",
    "settings": "Настройки",
    "about": "О программе",
}


class MainWindow:
    """Окно и навигация. Все сетевые операции — в фоновом потоке."""

    def __init__(self, settings: AppSettings) -> None:
        from winrt import system
        from winui3.microsoft.ui.xaml import Application, Thickness, Visibility, Window
        from winui3.microsoft.ui.xaml.controls import Grid, NavigationView, NavigationViewItem

        self._sys = system
        self._thickness = Thickness
        self._visibility = Visibility
        self._application = Application
        self._grid_cls = Grid
        self._nav_item_cls = NavigationViewItem

        self.settings = settings
        self.controller = AppController(settings)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.log = get_logger()

        self.window = Window()
        self.window.title = f"AutoHostUpdate {__version__}"

        self.nav = NavigationView()
        self.nav.pane_display_mode = 0
        self.nav.is_settings_visible = False
        self.nav.open_pane_length = 220.0

        self.pages: dict[str, Any] = {}
        self.root = self._grid_cls()
        self.nav.content = self.root
        self.window.content = self.nav

        self._build_pages()
        self._build_menu()

        self.window.add_closed(self._on_closed)
        self.controller.subscribe(lambda state: self._ui(lambda: self._render(state)))
        self._render(self.controller.load_local())

    # --- инфраструктура UI -----------------------------------------------------
    def _ui(self, fn: Callable[[], None]) -> None:
        queue = self.window.dispatcher_queue
        queue.try_enqueue(lambda: fn())

    def _box(self, value: str) -> Any:
        return self._sys.box_string(value)

    def _open_logs(self) -> None:
        log_path = Path(self.settings.logging.directory) / self.settings.logging.file_name
        if log_path.exists():
            os.startfile(log_path)

    def _submit(self, factory: Callable[[], Coroutine[Any, Any, AppState]], busy: str) -> None:
        self._set_busy(True, busy)

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
        self.ring.is_active = busy
        if text:
            self.status_text.text = text

    def _show_error(self, message: str) -> None:
        self.info_bar.title = "Ошибка"
        self.info_bar.message = message
        self.info_bar.severity = 3  # Error
        self.info_bar.is_open = True

    # --- построение UI ---------------------------------------------------------
    def _new_page(self) -> Any:
        from winui3.microsoft.ui.xaml.controls import StackPanel

        panel = StackPanel()
        panel.spacing = 8.0
        panel.padding = self._thickness(24, 24, 24, 24)
        return panel

    def _add_text(self, page: Any, text: str, *, size: float = 14.0, header: bool = False) -> Any:
        from winui3.microsoft.ui.xaml.controls import TextBlock

        block = TextBlock()
        block.text = text
        block.font_size = 28.0 if header else size
        block.text_wrapping = 2  # Wrap
        page.children.append(block)
        return block

    def _add_button(self, page: Any, text: str, handler: Callable[[Any, Any], None]) -> Any:
        from winui3.microsoft.ui.xaml.controls import Button

        button = Button()
        button.content = self._box(text)
        button.add_click(handler)
        page.children.append(button)
        return button

    def _build_pages(self) -> None:
        from winui3.microsoft.ui.xaml.controls import (
            CheckBox,
            ComboBox,
            ComboBoxItem,
            InfoBar,
            ListView,
            ProgressRing,
            TextBox,
        )

        # Dashboard
        page = self._new_page()
        self.info_bar = InfoBar()
        self.info_bar.is_open = True
        self.info_bar.severity = 0
        self.info_bar.title = "Готово"
        page.children.append(self.info_bar)

        self.status_text = self._add_text(page, "Проверка не выполнялась")
        self.source_date_text = self._add_text(page, "Источник: —")
        self.local_date_text = self._add_text(page, "Локально: —")
        self.backup_text = self._add_text(page, "Резервная копия: —")

        from winui3.microsoft.ui.xaml.controls import StackPanel

        buttons = StackPanel()
        buttons.orientation = 0  # Horizontal
        buttons.spacing = 8.0
        page.children.append(buttons)

        def add_to_buttons(text: str, handler: Callable[[Any, Any], None]) -> Any:
            from winui3.microsoft.ui.xaml.controls import Button

            button = Button()
            button.content = self._box(text)
            button.add_click(handler)
            buttons.children.append(button)
            return button

        add_to_buttons("Проверить", lambda s, a: self._submit(self.controller.check, "Проверка…"))
        add_to_buttons("Обновить", lambda s, a: self._submit(self.controller.update, "Обновление…"))
        add_to_buttons(
            "Dry-run",
            lambda s, a: self._submit(lambda: self.controller.update(dry_run=True), "Dry-run…"),
        )
        self.ring = ProgressRing()
        self.ring.is_active = False
        self.ring.width = 24.0
        self.ring.height = 24.0
        buttons.children.append(self.ring)
        self.pages["dashboard"] = page

        # Groups
        page = self._new_page()
        self._add_text(page, "Группы", header=True)
        self.groups_summary = self._add_text(page, "Нет данных")
        self.groups_list = ListView()
        self.groups_list.height = 420.0
        page.children.append(self.groups_list)
        self.pages["groups"] = page

        # Source
        page = self._new_page()
        self._add_text(page, "Источник", header=True)
        self.source_url_box = TextBox()
        self.source_url_box.header = self._box("URL источника")
        self.source_url_box.text = self.settings.source.url
        page.children.append(self.source_url_box)
        self.source_info_text = self._add_text(page, "Данные ещё не получены")
        self.pages["source"] = page

        # Schedule
        page = self._new_page()
        self._add_text(page, "Расписание", header=True)
        self.task_name_box = TextBox()
        self.task_name_box.header = self._box("Имя задачи")
        self.task_name_box.text = self.settings.schedule.task_name
        page.children.append(self.task_name_box)

        self.trigger_combo = ComboBox()
        self.trigger_combo.header = self._box("Триггер")
        for label, tag in (
            ("При входе в систему", "at_logon"),
            ("Ежедневно", "daily"),
            ("По интервалу", "interval"),
        ):
            item = ComboBoxItem()
            item.content = self._box(label)
            item.tag = self._box(tag)
            self.trigger_combo.items.append(item)
        self.trigger_combo.selected_index = 0
        page.children.append(self.trigger_combo)

        self._add_button(page, "Установить задачу", lambda s, a: self._install_task(True))
        self._add_button(page, "Удалить задачу", lambda s, a: self._install_task(False))
        self.task_status_text = self._add_text(
            page, "Для установки задачи нужны права администратора"
        )
        self.pages["schedule"] = page

        # Logs
        page = self._new_page()
        self._add_text(page, "Журнал", header=True)
        self._add_button(page, "Обновить", lambda s, a: self._refresh_logs())
        self._add_button(page, "Открыть файл", lambda s, a: self._open_logs())
        self.log_box = TextBox()
        self.log_box.is_read_only = True
        self.log_box.accepts_return = True
        self.log_box.height = 420.0
        page.children.append(self.log_box)
        self.pages["logs"] = page

        # Settings
        page = self._new_page()
        self._add_text(page, "Настройки", header=True)
        self.run_at_logon_check = CheckBox()
        self.run_at_logon_check.content = self._box("Запускать при входе в систему")
        self.run_at_logon_check.is_checked = self.settings.general.run_at_logon
        page.children.append(self.run_at_logon_check)

        self.flush_dns_check = CheckBox()
        self.flush_dns_check.content = self._box("Сбрасывать DNS-кеш после записи")
        self.flush_dns_check.is_checked = self.settings.update.flush_dns
        page.children.append(self.flush_dns_check)

        self.dry_run_check = CheckBox()
        self.dry_run_check.content = self._box("Dry-run по умолчанию")
        self.dry_run_check.is_checked = self.settings.update.dry_run_by_default
        page.children.append(self.dry_run_check)

        self._add_button(page, "Сохранить", lambda s, a: self._save_settings())
        self.settings_status_text = self._add_text(page, "")
        self.pages["settings"] = page

        # About
        page = self._new_page()
        self._add_text(page, "О программе", header=True)
        self._add_text(page, f"AutoHostUpdate {__version__}")
        self._add_text(page, "Источник: https://geohide.ru/eu/hosts")
        self._add_text(page, "Python + WinUI 3 (PyWinRT). Лицензия MIT.")
        self.pages["about"] = page

        for name, panel in self.pages.items():
            panel.visibility = (
                self._visibility.VISIBLE if name == "dashboard" else self._visibility.COLLAPSED
            )
            self.root.children.append(panel)

        self._refresh_logs()

    def _build_menu(self) -> None:
        self._menu_items: dict[str, Any] = {}
        for tag, title in PAGE_TITLES.items():
            item = self._nav_item_cls()
            from winui3.microsoft.ui.xaml.controls import TextBlock

            label = TextBlock()
            label.text = title
            item.content = label
            item.tag = self._box(tag)
            self.nav.menu_items.append(item)
            self._menu_items[tag] = item
        self.nav.add_item_invoked(self._on_nav_invoked)
        self.nav.selected_item = self._menu_items["dashboard"]

    # --- обработчики -----------------------------------------------------------
    def _on_nav_invoked(self, sender: Any, args: Any) -> None:
        item = args.invoked_item
        if item is None or item.tag is None:
            return
        tag = self._sys.unbox_string(item.tag)
        self._show_page(tag)

    def _show_page(self, tag: str) -> None:
        for name, panel in self.pages.items():
            panel.visibility = (
                self._visibility.VISIBLE if name == tag else self._visibility.COLLAPSED
            )
        if tag == "logs":
            self._refresh_logs()

    def _on_closed(self, sender: Any, args: Any) -> None:
        self.executor.shutdown(wait=False)
        self._application.exit()

    def _install_task(self, install: bool) -> None:
        if not is_admin():
            self.task_status_text.text = (
                "Нужны права администратора. Запустите приложение от имени администратора "
                "или используйте CLI: autohostupdate --install-task"
            )
            return
        from autohostupdate.services.scheduler import install_task, task_info, uninstall_task

        task_name = self.task_name_box.text.strip() or "AutoHostUpdate"
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

    def _save_settings(self) -> None:
        self.settings.general.run_at_logon = bool(self.run_at_logon_check.is_checked)
        self.settings.update.flush_dns = bool(self.flush_dns_check.is_checked)
        self.settings.update.dry_run_by_default = bool(self.dry_run_check.is_checked)
        url = (self.source_url_box.text or "").strip()
        if url:
            self.settings.source.url = url
        try:
            save_settings(self.settings)
        except AutoHostUpdateError as exc:
            self.settings_status_text.text = f"Ошибка сохранения: {exc}"
            return
        self.controller.settings = self.settings
        self.settings_status_text.text = "Настройки сохранены."
        self.info_bar.title = "Готово"
        self.info_bar.message = "Настройки сохранены"
        self.info_bar.severity = 1

    def _refresh_logs(self) -> None:
        log_path = Path(self.settings.logging.directory) / self.settings.logging.file_name
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            self.log_box.text = f"Журнал не найден: {log_path}"
            return
        self.log_box.text = "\n".join(lines[-500:])

    def _render(self, state: AppState) -> None:
        self.status_text.text = state.status_text or "Готово"
        self.source_date_text.text = f"Источник: {state.source_date or '—'}"
        self.local_date_text.text = f"Локально: {state.local_date or '—'}"
        self.backup_text.text = f"Резервная копия: {state.last_backup or '—'}"
        self.groups_summary.text = (
            f"Всего групп: {len(state.groups)}, к обновлению: "
            f"{sum(1 for row in state.groups if row.status is GroupStatus.OUTDATED)}"
        )
        self._render_groups(state.groups)

        if state.last_error:
            self.info_bar.title = "Ошибка"
            self.info_bar.message = state.last_error
            self.info_bar.severity = 3
        else:
            self.info_bar.title = "Готово" if not state.busy else "Выполняется"
            self.info_bar.message = state.status_text
            self.info_bar.severity = 0 if not state.update_available else 2
        self.info_bar.is_open = True

    def _render_groups(self, groups: list[GroupRow]) -> None:
        from winui3.microsoft.ui.xaml.controls import TextBlock

        self.groups_list.items.clear()
        for row in groups:
            block = TextBlock()
            block.text = (
                f"{row.name} — {STATUS_RU[row.status]} "
                f"({row.local_lines} → {row.source_lines} строк)"
            )
            block.font_size = 14.0
            self.groups_list.items.append(block)

    def show(self) -> None:
        self.window.activate()
        self.log.info("UI запущен")


__all__ = ["MainWindow"]
