"""Уведомления Windows (AppNotification) с безопасным откатом.

Для unpackaged-приложений регистрация COM-сервера не всегда доступна,
поэтому любая ошибка WinRT не должна ломать обновление: в этом случае
событие просто пишется в журнал.
"""

from __future__ import annotations

from enum import StrEnum
from xml.sax.saxutils import escape

from autohostupdate.config.schema import AppSettings
from autohostupdate.services.logging import get_logger


class NotificationKind(StrEnum):
    SUCCESS = "success"
    NO_UPDATE = "no_update"
    ERROR = "error"


def should_notify(settings: AppSettings, kind: NotificationKind) -> bool:
    """Проверяет пользовательские переключатели уведомлений."""
    notifications = settings.notifications
    if not notifications.enabled:
        return False
    flags = {
        NotificationKind.SUCCESS: notifications.notify_success,
        NotificationKind.NO_UPDATE: notifications.notify_no_update,
        NotificationKind.ERROR: notifications.notify_errors,
    }
    return flags[kind]


def build_payload(title: str, message: str, *, sound: bool = True) -> str:
    """Собирает XML toast-уведомления."""
    silent = "false" if sound else "true"
    return (
        "<toast>"
        '<visual><binding template="ToastGeneric">'
        f"<text>{escape(title)}</text>"
        f"<text>{escape(message)}</text>"
        "</binding></visual>"
        f'<audio silent="{silent}" />'
        "</toast>"
    )


def notify(
    settings: AppSettings,
    title: str,
    message: str,
    kind: NotificationKind = NotificationKind.SUCCESS,
) -> bool:
    """Показывает уведомление. Возвращает True, если оно действительно показано."""
    if not should_notify(settings, kind):
        return False

    payload = build_payload(title, message, sound=settings.notifications.sound)
    try:
        from winrt.microsoft.windows.appnotifications import (
            AppNotification,
            AppNotificationManager,
        )

        manager = AppNotificationManager.default
        manager.register()
        manager.show(AppNotification(payload))
        return True
    except Exception as exc:  # pragma: no cover - зависит от окружения Windows
        get_logger().info("Уведомление (%s): %s — %s [%s]", kind, title, message, exc)
        return False


__all__ = ["NotificationKind", "build_payload", "notify", "should_notify"]
