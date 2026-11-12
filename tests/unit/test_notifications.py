from __future__ import annotations

from autohostupdate.config.schema import AppSettings
from autohostupdate.services.notifications import (
    NotificationKind,
    build_payload,
    notify,
    should_notify,
)


def test_should_notify_respects_global_switch() -> None:
    settings = AppSettings()
    settings.notifications.enabled = False

    assert should_notify(settings, NotificationKind.SUCCESS) is False
    assert should_notify(settings, NotificationKind.ERROR) is False


def test_should_notify_respects_per_kind_switches() -> None:
    settings = AppSettings()
    settings.notifications.notify_success = False
    settings.notifications.notify_errors = True

    assert should_notify(settings, NotificationKind.SUCCESS) is False
    assert should_notify(settings, NotificationKind.ERROR) is True


def test_build_payload_escapes_text_and_sound() -> None:
    payload = build_payload("A & B", "<script>", sound=False)

    assert "A &amp; B" in payload
    assert "&lt;script&gt;" in payload
    assert 'silent="true"' in payload
    assert "ToastGeneric" in payload


def test_notify_returns_false_when_disabled() -> None:
    settings = AppSettings()
    settings.notifications.enabled = False

    assert notify(settings, "t", "m") is False


def test_notify_falls_back_without_winrt(monkeypatch) -> None:
    settings = AppSettings()
    messages: list[str] = []

    class FakeLogger:
        def info(self, *args) -> None:
            messages.append(args[0])

    monkeypatch.setattr("autohostupdate.services.notifications.get_logger", lambda: FakeLogger())

    from winrt.microsoft.windows import appnotifications

    class Broken:
        @property
        def default(self):
            raise OSError("нет регистрации")

    monkeypatch.setattr(appnotifications, "AppNotificationManager", Broken)

    assert notify(settings, "Заголовок", "Текст") is False
    assert messages
