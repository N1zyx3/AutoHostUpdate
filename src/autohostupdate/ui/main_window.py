"""Главное окно WinUI 3: XAML + code-behind на PyWinRT."""

from __future__ import annotations

import asyncio
import logging
import os
import platform
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from autohostupdate import __version__
from autohostupdate.config.schema import (
    AppSettings,
    Language,
    LogFormat,
    LogLevel,
    ProxyMode,
    ScheduleTrigger,
    Theme,
    UpdateMode,
)
from autohostupdate.core.models import GroupStatus
from autohostupdate.errors import AutoHostUpdateError
from autohostupdate.services.logging import LogQuery, get_logger
from autohostupdate.services.privileges import is_admin
from autohostupdate.ui.viewmodels.app_controller import (
    AppController,
    AppState,
    GroupRow,
    TaskSnapshot,
)

STATUS_RU = {
    GroupStatus.UP_TO_DATE: "актуальна",
    GroupStatus.OUTDATED: "устарела",
    GroupStatus.LOCAL_ONLY: "только локально",
    GroupStatus.SOURCE_ONLY: "только в источнике",
    GroupStatus.DISABLED: "отключена",
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
            ComboBoxItem,
            InfoBar,
            ListView,
            NavigationView,
            ProgressRing,
            StackPanel,
            TextBlock,
            TextBox,
        )
        from winrt.microsoft.ui.xaml.markup import XamlReader
        from winrt.system import box_string, unbox_string

        self._types = {
            "button": Button,
            "checkbox": CheckBox,
            "combo": ComboBox,
            "comboitem": ComboBoxItem,
            "infobar": InfoBar,
            "listview": ListView,
            "navigationview": NavigationView,
            "progressring": ProgressRing,
            "stackpanel": StackPanel,
            "textblock": TextBlock,
            "textbox": TextBox,
        }

        self.settings = settings
        self.controller = AppController(settings)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.log = get_logger()
        self._box = box_string
        self._unbox = unbox_string
        self._visibility = Visibility

        window = XamlReader.load(XAML_PATH.read_text(encoding="utf-8")).as_(Window)
        self.window = window
        self.window.title = f"AutoHostUpdate {__version__}"
        self.root = window.content.as_(FrameworkElement)

        self.nav = self._ctl("NavView", "navigationview")
        self.status_bar = self._ctl("StatusBar", "infobar")
        self.status_text = self._ctl("StatusText", "textblock")
        self.source_date_text = self._ctl("SourceDateText", "textblock")
        self.local_date_text = self._ctl("LocalDateText", "textblock")
        self.backup_text = self._ctl("BackupText", "textblock")
        self.busy_ring = self._ctl("BusyRing", "progressring")
        self.groups_summary = self._ctl("GroupsSummary", "textblock")
        self.groups_list = self._ctl("GroupsList", "listview")
        self.group_search_box = self._ctl("GroupSearchBox", "textbox")

        self.source_url_box = self._ctl("SourceUrlBox", "textbox")
        self.source_timeout_box = self._ctl("SourceTimeoutBox", "textbox")
        self.source_retries_box = self._ctl("SourceRetriesBox", "textbox")
        self.source_max_kb_box = self._ctl("SourceMaxKbBox", "textbox")
        self.marker_prefix_box = self._ctl("MarkerPrefixBox", "textbox")
        self.verify_tls_check = self._ctl("VerifyTlsCheck", "checkbox")
        self.proxy_combo = self._ctl("ProxyCombo", "combo")
        self.proxy_url_box = self._ctl("ProxyUrlBox", "textbox")
        self.source_info_text = self._ctl("SourceInfoText", "textblock")
        self.source_preview_box = self._ctl("SourcePreviewBox", "textbox")

        self.task_name_box = self._ctl("TaskNameBox", "textbox")
        self.trigger_combo = self._ctl("TriggerCombo", "combo")
        self.daily_time_box = self._ctl("DailyTimeBox", "textbox")
        self.interval_box = self._ctl("IntervalBox", "textbox")
        self.delay_box = self._ctl("DelayBox", "textbox")
        self.allow_battery_check = self._ctl("AllowBatteryCheck", "checkbox")
        self.run_missed_check = self._ctl("RunMissedCheck", "checkbox")
        self.task_status_text = self._ctl("TaskStatusText", "textblock")
        self.schedule_admin_hint = self._ctl("ScheduleAdminHint", "textblock")

        self.log_level_filter = self._ctl("LogLevelFilter", "combo")
        self.log_search_box = self._ctl("LogSearchBox", "textbox")
        self.log_box = self._ctl("LogBox", "textbox")

        self.language_combo = self._ctl("LanguageCombo", "combo")
        self.theme_combo = self._ctl("ThemeCombo", "combo")
        self.run_at_logon_check = self._ctl("RunAtLogonCheck", "checkbox")
        self.start_minimized_check = self._ctl("StartMinimizedCheck", "checkbox")
        self.single_instance_check = self._ctl("SingleInstanceCheck", "checkbox")
        self.compare_mode_combo = self._ctl("CompareModeCombo", "combo")
        self.dry_run_check = self._ctl("DryRunCheck", "checkbox")
        self.create_backup_check = self._ctl("CreateBackupCheck", "checkbox")
        self.flush_dns_check = self._ctl("FlushDnsCheck", "checkbox")
        self.clear_readonly_check = self._ctl("ClearReadonlyCheck", "checkbox")
        self.backup_keep_count_box = self._ctl("BackupKeepCountBox", "textbox")
        self.backup_keep_days_box = self._ctl("BackupKeepDaysBox", "textbox")
        self.hosts_path_box = self._ctl("HostsPathBox", "textbox")
        self.notify_enabled_check = self._ctl("NotifyEnabledCheck", "checkbox")
        self.notify_success_check = self._ctl("NotifySuccessCheck", "checkbox")
        self.notify_no_update_check = self._ctl("NotifyNoUpdateCheck", "checkbox")
        self.notify_errors_check = self._ctl("NotifyErrorsCheck", "checkbox")
        self.notify_sound_check = self._ctl("NotifySoundCheck", "checkbox")
        self.log_level_combo = self._ctl("LogLevelCombo", "combo")
        self.log_format_combo = self._ctl("LogFormatCombo", "combo")
        self.log_max_size_box = self._ctl("LogMaxSizeBox", "textbox")
        self.log_backup_count_box = self._ctl("LogBackupCountBox", "textbox")
        self.log_directory_box = self._ctl("LogDirectoryBox", "textbox")
        self.settings_status_text = self._ctl("SettingsStatusText", "textblock")
        self.about_version_text = self._ctl("AboutVersionText", "textblock")
        self.about_environment_text = self._ctl("AboutEnvironmentText", "textblock")

        self._pages = {tag: self._ctl(name, "stackpanel") for tag, name in PAGE_NAMES.items()}
        self._nav_items: dict[str, Any] = {}

        self._wire_buttons()
        self._wire_checkboxes()

        for index, tag in enumerate(PAGE_NAMES):
            self._nav_items[tag] = self.nav.menu_items.get_at(index)
        self.nav.add_item_invoked(self._on_nav_invoked)
        self.nav.selected_item = self._nav_items["dashboard"]

        self.group_search_box.add_text_changed(
            lambda s, a: self._render_groups(self.controller.state)
        )
        self.log_level_filter.add_selection_changed(lambda s, a: self._refresh_logs())
        self.log_search_box.add_text_changed(lambda s, a: self._refresh_logs())

        self._load_settings_into_ui()
        self.about_version_text.text = f"AutoHostUpdate {__version__}"
        self.about_environment_text.text = (
            f"Python {platform.python_version()}, {platform.system()} "
            f"{platform.release()}\nhosts: {self.settings.update.hosts_path}"
        )
        self.window.add_closed(self._on_closed)
        self.controller.subscribe(lambda state: self._ui(lambda: self._render(state)))
        self._render(self.controller.load_local())
        self._refresh_task_status()
        self._refresh_logs()

    # --- инфраструктура --------------------------------------------------------
    def _ctl(self, name: str, kind: str) -> Any:
        return self.root.find_name(name).as_(self._types[kind])

    def _wire(self, name: str, action: Callable[[], object]) -> None:
        button = self._ctl(name, "button")
        button.add_click(lambda sender, args: action())

    def _wire_buttons(self) -> None:
        self._wire("CheckButton", lambda: self._submit(self.controller.check))
        self._wire("UpdateButton", lambda: self._submit(self.controller.update))
        self._wire(
            "DryRunButton",
            lambda: self._submit(lambda: self.controller.update(dry_run=True)),
        )
        self._wire("OpenSettingsButton", lambda: self._show_page("settings"))
        self._wire("OpenLogsButton2", lambda: self._show_page("logs"))
        self._wire("OpenSourceButton", lambda: self._show_page("source"))
        self._wire("RefreshGroupsButton", self._refresh_groups)
        self._wire("EnableAllGroupsButton", lambda: self._set_all_groups(True))
        self._wire("DisableAllGroupsButton", lambda: self._set_all_groups(False))
        self._wire("ProbeSourceButton", self._probe_source)
        self._wire("SaveSourceButton", lambda: self._save_source_settings())
        self._wire("InstallTaskButton", lambda: self._task_action("install"))
        self._wire("RemoveTaskButton", lambda: self._task_action("remove"))
        self._wire("RunTaskButton", lambda: self._task_action("run"))
        self._wire("RefreshTaskButton", self._refresh_task_status)
        self._wire("RefreshLogsButton", self._refresh_logs)
        self._wire("OpenLogsButton", self._open_logs)
        self._wire("ClearLogsButton", self._clear_logs)
        self._wire("ExportDiagnosticsButton", self._export_diagnostics)
        self._wire("SaveSettingsButton", self._save_settings)
        self._wire("ResetSettingsButton", self._reset_settings)

    def _wire_checkboxes(self) -> None:
        for box in (
            self.run_at_logon_check,
            self.start_minimized_check,
            self.single_instance_check,
            self.dry_run_check,
            self.create_backup_check,
            self.flush_dns_check,
            self.clear_readonly_check,
            self.notify_enabled_check,
            self.notify_success_check,
            self.notify_no_update_check,
            self.notify_errors_check,
            self.notify_sound_check,
        ):
            box.add_click(lambda s, a: self._clear_settings_status())

    def _clear_settings_status(self) -> None:
        self.settings_status_text.text = ""

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

    def _notice(self, message: str) -> None:
        self.status_bar.title = "Готово"
        self.status_bar.message = message
        self.status_bar.severity = 1
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
        elif tag == "schedule":
            self._refresh_task_status()

    # --- обработчики -----------------------------------------------------------
    def _on_closed(self, sender: Any, args: Any) -> None:
        # Финализация WinRT-объектов после Application.Start падает в PyWinRT,
        # поэтому завершаем процесс сразу после закрытия окна.
        self.executor.shutdown(wait=False)
        logging.shutdown()
        os._exit(0)

    # --- группы ----------------------------------------------------------------
    def _refresh_groups(self) -> None:
        self.controller.load_local()
        self._notice("Список групп обновлён")

    def _set_all_groups(self, enabled: bool) -> None:
        for row in list(self.controller.state.groups):
            if row.enabled != enabled:
                self.controller.set_group_enabled(row.name, enabled)
        self._notice("Все группы включены" if enabled else "Все группы отключены")

    def _on_group_toggled(self, name: str, enabled: bool) -> None:
        self.controller.set_group_enabled(name, enabled)

    # --- источник --------------------------------------------------------------
    def _probe_source(self) -> None:
        if not self._save_source_settings(silent=True):
            return
        self.source_info_text.text = "Проверка соединения…"
        self._submit(self._probe_job)

    async def _probe_job(self) -> AppState:
        try:
            probe = await self.controller.probe_source()
        except AutoHostUpdateError as exc:
            message = str(exc)
            self._ui(lambda: self._source_probe_failed(message))
            return self.controller.state

        def show() -> None:
            self.source_info_text.text = (
                f"Соединение установлено: {probe.url}\n"
                f"Дата источника: {probe.date}; групп: {probe.group_count}; "
                f"строк: {probe.total_lines}"
            )
            self.source_preview_box.text = "\n".join(probe.preview)
            self._notice("Источник доступен")

        self._ui(show)
        return self.controller.state

    def _source_probe_failed(self, message: str) -> None:
        self.source_info_text.text = f"Ошибка: {message}"
        self._show_error(message)

    def _save_source_settings(self, *, silent: bool = False) -> bool:
        source = self.settings.source
        source.url = (self.source_url_box.text or "").strip() or source.url
        marker = (self.marker_prefix_box.text or "").strip()
        if marker:
            source.marker_prefix = marker

        errors: list[str] = []
        source.timeout_seconds = self._number(
            self.source_timeout_box, "Таймаут", errors, default=source.timeout_seconds, minimum=1
        )
        source.retries = self._int_number(
            self.source_retries_box,
            "Повторы",
            errors,
            default=source.retries,
            minimum=0,
            maximum=10,
        )
        source.max_response_kb = self._int_number(
            self.source_max_kb_box,
            "Макс. размер",
            errors,
            default=source.max_response_kb,
            minimum=16,
            maximum=65536,
        )
        source.verify_tls = bool(self.verify_tls_check.is_checked)

        proxy_tag = self._selected_tag(self.proxy_combo) or "system"
        source.proxy_mode = ProxyMode(proxy_tag)
        proxy_url = (self.proxy_url_box.text or "").strip()
        source.proxy_url = proxy_url or None
        if source.proxy_mode is ProxyMode.MANUAL and not source.proxy_url:
            errors.append("Укажите URL прокси")

        if errors:
            self.source_info_text.text = "; ".join(errors)
            self.settings_status_text.text = "; ".join(errors)
            return False

        try:
            self.controller.save_settings(self.settings)
        except AutoHostUpdateError as exc:
            self.source_info_text.text = f"Ошибка сохранения: {exc}"
            return False
        if not silent:
            self.source_info_text.text = "Настройки источника сохранены."
            self._notice("Настройки источника сохранены")
        return True

    # --- расписание ------------------------------------------------------------
    def _task_action(self, action: str) -> None:
        if action in {"install", "remove"} and not is_admin():
            self.task_status_text.text = (
                "Нужны права администратора. Запустите приложение от имени администратора "
                "или используйте CLI: autohostupdate --install-task"
            )
            return
        self._save_schedule_settings()
        try:
            if action == "install":
                snapshot = self.controller.install_task()
                self.task_status_text.text = (
                    f"Задача «{snapshot.name}» зарегистрирована."
                    if snapshot.exists
                    else "Не удалось найти задачу после регистрации."
                )
            elif action == "remove":
                snapshot = self.controller.uninstall_task()
                self.task_status_text.text = (
                    f"Задача «{snapshot.name}» удалена."
                    if not snapshot.exists
                    else "Не удалось удалить задачу."
                )
            else:
                self.controller.run_task()
                self.task_status_text.text = "Задача запущена."
        except AutoHostUpdateError as exc:
            self.task_status_text.text = f"Ошибка: {exc}"

    def _refresh_task_status(self) -> None:
        snapshot = self.controller.task_snapshot()
        self.task_status_text.text = self._task_text(snapshot)
        self.schedule_admin_hint.text = (
            "Права администратора есть: задачу можно установить."
            if is_admin()
            else "Для установки/удаления задачи нужны права администратора."
        )

    @staticmethod
    def _task_text(snapshot: TaskSnapshot) -> str:
        if not snapshot.exists:
            state = f" ({snapshot.state_text})" if snapshot.state_text else ""
            return f"Задача «{snapshot.name}» не найдена{state}"
        enabled = "включена" if snapshot.enabled else "отключена"
        state = f", {snapshot.state_text}" if snapshot.state_text else ""
        return f"Задача «{snapshot.name}»: {enabled}{state}"

    def _save_schedule_settings(self) -> None:
        schedule = self.settings.schedule
        schedule.task_name = (self.task_name_box.text or "").strip() or schedule.task_name
        trigger = self._selected_tag(self.trigger_combo) or schedule.trigger.value
        schedule.trigger = ScheduleTrigger(trigger)

        errors: list[str] = []
        daily = (self.daily_time_box.text or "").strip()
        if daily:
            try:
                schedule.daily_time = daily
            except ValueError as exc:
                errors.append(str(exc))
        schedule.interval_minutes = self._int_number(
            self.interval_box,
            "Интервал",
            errors,
            default=schedule.interval_minutes,
            minimum=5,
            maximum=10080,
        )
        schedule.start_delay_seconds = self._int_number(
            self.delay_box,
            "Задержка",
            errors,
            default=schedule.start_delay_seconds,
            minimum=0,
            maximum=3600,
        )
        schedule.allow_on_battery = bool(self.allow_battery_check.is_checked)
        schedule.run_missed_start = bool(self.run_missed_check.is_checked)

        if errors:
            self.task_status_text.text = "; ".join(errors)
            return
        try:
            self.controller.save_settings(self.settings)
        except (AutoHostUpdateError, ValueError) as exc:
            self.task_status_text.text = f"Ошибка сохранения: {exc}"

    # --- журнал ----------------------------------------------------------------
    def _log_query(self) -> LogQuery:
        level = self._selected_tag(self.log_level_filter) or None
        return LogQuery(
            limit=500, level=level or None, search=(self.log_search_box.text or "").strip()
        )

    def _refresh_logs(self) -> None:
        lines = self.controller.read_logs(self._log_query())
        if not lines:
            self.log_box.text = f"Записей нет. Файл журнала: {self.controller.log_path}"
            return
        self.log_box.text = "\n".join(lines)

    def _open_logs(self) -> None:
        if self.controller.log_path.exists():
            os.startfile(self.controller.log_path)

    def _clear_logs(self) -> None:
        self.controller.clear_logs()
        self._refresh_logs()
        self._notice("Журнал очищен")

    def _export_diagnostics(self) -> None:
        from datetime import datetime

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.controller.log_path.parent / f"diagnostics-{stamp}.zip"
        try:
            path = self.controller.export_diagnostics(target)
        except OSError as exc:
            self._show_error(f"Не удалось создать архив: {exc}")
            return
        self._notice(f"Диагностика сохранена: {path}")

    # --- настройки -------------------------------------------------------------
    def _number(
        self,
        box: Any,
        label: str,
        errors: list[str],
        *,
        default: float,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float:
        raw = (box.text or "").strip()
        if not raw:
            return default
        try:
            value = float(raw.replace(",", "."))
        except ValueError:
            errors.append(f"{label}: ожидается число")
            return default
        if minimum is not None and value < minimum:
            errors.append(f"{label}: минимум {minimum:g}")
        if maximum is not None and value > maximum:
            errors.append(f"{label}: максимум {maximum:g}")
        return value

    def _int_number(
        self,
        box: Any,
        label: str,
        errors: list[str],
        *,
        default: int,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> int:
        return int(
            self._number(
                box, label, errors, default=float(default), minimum=minimum, maximum=maximum
            )
        )

    def _selected_tag(self, combo: Any) -> str | None:
        item = combo.selected_item
        if item is None:
            return None
        item = item.as_(self._types["comboitem"])
        if item.tag is None:
            return None
        return self._unbox(item.tag)

    def _select_by_tag(self, combo: Any, tag: str) -> None:
        items = combo.items
        for index in range(items.size):
            item = items.get_at(index).as_(self._types["comboitem"])
            if item.tag is not None and self._unbox(item.tag) == tag:
                combo.selected_index = index
                return

    def _load_settings_into_ui(self) -> None:
        settings = self.settings

        self.source_url_box.text = settings.source.url
        self.source_timeout_box.text = f"{settings.source.timeout_seconds:g}"
        self.source_retries_box.text = str(settings.source.retries)
        self.source_max_kb_box.text = str(settings.source.max_response_kb)
        self.marker_prefix_box.text = settings.source.marker_prefix
        self.verify_tls_check.is_checked = settings.source.verify_tls
        self._select_by_tag(self.proxy_combo, settings.source.proxy_mode.value)
        self.proxy_url_box.text = settings.source.proxy_url or ""

        self.task_name_box.text = settings.schedule.task_name
        self._select_by_tag(self.trigger_combo, settings.schedule.trigger.value)
        self.daily_time_box.text = settings.schedule.daily_time
        self.interval_box.text = str(settings.schedule.interval_minutes)
        self.delay_box.text = str(settings.schedule.start_delay_seconds)
        self.allow_battery_check.is_checked = settings.schedule.allow_on_battery
        self.run_missed_check.is_checked = settings.schedule.run_missed_start

        self._select_by_tag(self.language_combo, settings.general.language.value)
        self._select_by_tag(self.theme_combo, settings.general.theme.value)
        self.run_at_logon_check.is_checked = settings.general.run_at_logon
        self.start_minimized_check.is_checked = settings.general.start_minimized
        self.single_instance_check.is_checked = settings.general.single_instance

        self._select_by_tag(self.compare_mode_combo, settings.update.compare_mode.value)
        self.dry_run_check.is_checked = settings.update.dry_run_by_default
        self.create_backup_check.is_checked = settings.update.create_backup
        self.flush_dns_check.is_checked = settings.update.flush_dns
        self.clear_readonly_check.is_checked = settings.update.clear_readonly
        self.backup_keep_count_box.text = str(settings.update.backup_keep_count)
        self.backup_keep_days_box.text = str(settings.update.backup_keep_days)
        self.hosts_path_box.text = str(settings.update.hosts_path)

        self.notify_enabled_check.is_checked = settings.notifications.enabled
        self.notify_success_check.is_checked = settings.notifications.notify_success
        self.notify_no_update_check.is_checked = settings.notifications.notify_no_update
        self.notify_errors_check.is_checked = settings.notifications.notify_errors
        self.notify_sound_check.is_checked = settings.notifications.sound

        self._select_by_tag(self.log_level_combo, settings.logging.level.value)
        self._select_by_tag(self.log_format_combo, settings.logging.format.value)
        self.log_max_size_box.text = str(settings.logging.max_size_mb)
        self.log_backup_count_box.text = str(settings.logging.backup_count)
        self.log_directory_box.text = str(settings.logging.directory)

    def _save_settings(self) -> None:
        settings = self.settings
        errors: list[str] = []

        settings.general.language = Language(self._selected_tag(self.language_combo) or "ru")
        settings.general.theme = Theme(self._selected_tag(self.theme_combo) or "system")
        settings.general.run_at_logon = bool(self.run_at_logon_check.is_checked)
        settings.general.start_minimized = bool(self.start_minimized_check.is_checked)
        settings.general.single_instance = bool(self.single_instance_check.is_checked)

        settings.update.compare_mode = UpdateMode(
            self._selected_tag(self.compare_mode_combo) or "date"
        )
        settings.update.dry_run_by_default = bool(self.dry_run_check.is_checked)
        settings.update.create_backup = bool(self.create_backup_check.is_checked)
        settings.update.flush_dns = bool(self.flush_dns_check.is_checked)
        settings.update.clear_readonly = bool(self.clear_readonly_check.is_checked)
        settings.update.backup_keep_count = self._int_number(
            self.backup_keep_count_box,
            "Хранить копий",
            errors,
            default=settings.update.backup_keep_count,
            minimum=1,
            maximum=500,
        )
        settings.update.backup_keep_days = self._int_number(
            self.backup_keep_days_box,
            "Хранить дней",
            errors,
            default=settings.update.backup_keep_days,
            minimum=1,
            maximum=3650,
        )
        hosts_path = (self.hosts_path_box.text or "").strip()
        if hosts_path:
            settings.update.hosts_path = Path(hosts_path)

        settings.notifications.enabled = bool(self.notify_enabled_check.is_checked)
        settings.notifications.notify_success = bool(self.notify_success_check.is_checked)
        settings.notifications.notify_no_update = bool(self.notify_no_update_check.is_checked)
        settings.notifications.notify_errors = bool(self.notify_errors_check.is_checked)
        settings.notifications.sound = bool(self.notify_sound_check.is_checked)

        settings.logging.level = LogLevel(self._selected_tag(self.log_level_combo) or "INFO")
        settings.logging.format = LogFormat(self._selected_tag(self.log_format_combo) or "text")
        settings.logging.max_size_mb = self._int_number(
            self.log_max_size_box,
            "Макс. размер журнала",
            errors,
            default=settings.logging.max_size_mb,
            minimum=1,
            maximum=100,
        )
        settings.logging.backup_count = self._int_number(
            self.log_backup_count_box,
            "Ротаций",
            errors,
            default=settings.logging.backup_count,
            minimum=1,
            maximum=50,
        )
        log_dir = (self.log_directory_box.text or "").strip()
        if log_dir:
            settings.logging.directory = Path(log_dir)

        if errors:
            self.settings_status_text.text = "; ".join(errors)
            return
        try:
            self.controller.save_settings(settings)
        except (AutoHostUpdateError, ValueError) as exc:
            self.settings_status_text.text = f"Ошибка сохранения: {exc}"
            return

        self.settings_status_text.text = "Настройки сохранены."
        self._notice("Настройки сохранены")

    def _reset_settings(self) -> None:
        self.settings = AppSettings()
        self.controller.settings = self.settings
        self._load_settings_into_ui()
        try:
            self.controller.save_settings(self.settings)
        except AutoHostUpdateError as exc:
            self.settings_status_text.text = f"Ошибка сохранения: {exc}"
            return
        self.settings_status_text.text = "Настройки сброшены к значениям по умолчанию."
        self._refresh_task_status()
        self.controller.load_local()

    # --- отрисовка -------------------------------------------------------------
    def _render(self, state: AppState) -> None:
        self.status_text.text = state.status_text or "Готово"
        self.source_date_text.text = state.source_date or "—"
        self.local_date_text.text = state.local_date or "—"
        self.backup_text.text = state.last_backup or "—"
        outdated = sum(1 for row in state.groups if row.status is GroupStatus.OUTDATED)
        self.groups_summary.text = (
            f"Всего групп: {len(state.groups)}, к обновлению: {outdated}; "
            f"групп в источнике: {state.source_groups}"
        )
        self._render_groups(state)

        if state.last_error:
            self.status_bar.title = "Ошибка"
            self.status_bar.message = state.last_error
            self.status_bar.severity = 3
        else:
            self.status_bar.title = "Выполняется" if state.busy else "Готово"
            self.status_bar.message = state.status_text
            self.status_bar.severity = 0 if not state.update_available else 2
        self.status_bar.is_open = True

    def _render_groups(self, state: AppState) -> None:
        from winrt.microsoft.ui.xaml.controls import CheckBox, StackPanel, TextBlock

        needle = (self.group_search_box.text or "").strip().casefold()
        self.groups_list.items.clear()
        for row in state.groups:
            if needle and needle not in row.name.casefold():
                continue
            self.groups_list.items.append(self._group_item(row, CheckBox, StackPanel, TextBlock))

    def _group_item(self, row: GroupRow, check_cls: Any, panel_cls: Any, text_cls: Any) -> Any:
        panel = panel_cls()
        panel.orientation = 0  # Horizontal
        panel.spacing = 12.0

        check = check_cls()
        check.is_checked = row.enabled
        check.content = self._box(row.name)
        check.add_click(lambda sender, args: self._on_group_toggled(row.name, sender.is_checked))
        panel.children.append(check)

        label = text_cls()
        detail = f"{STATUS_RU[row.status]} ({row.local_lines} → {row.source_lines} строк)"
        label.text = detail
        label.opacity = 0.8 if row.enabled else 0.45
        panel.children.append(label)
        return panel

    def show(self) -> None:
        self.window.activate()
        self.log.info("UI запущен")

    def smoke_exercise(self) -> None:
        """Прокликивает страницы и обработчики чтения (используется в smoke-тесте)."""
        for tag in PAGE_NAMES:
            self._show_page(tag)
        self.group_search_box.text = "you"
        self._render_groups(self.controller.state)
        self.group_search_box.text = ""
        self._render_groups(self.controller.state)
        self._refresh_groups()
        self._refresh_logs()
        self._refresh_task_status()
        self._load_settings_into_ui()
        if os.environ.get("AUTOHOSTUPDATE_UI_SMOKE_WRITE"):
            self._save_source_settings(silent=True)
            self._save_settings()
            self._refresh_logs()
        self._show_page("dashboard")


__all__ = ["MainWindow"]
