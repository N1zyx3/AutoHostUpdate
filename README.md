# AutoHostUpdate

Автоматическая синхронизация именованных групп записей в системном файле
`hosts` с источником **GeoHideDNS** (`https://geohide.ru/eu/hosts`).

Обновляются только те именованные группы, которые уже есть в вашем `hosts`;
остальное содержимое файла не трогается. Группа — блок строк, начинающийся с
`# ИмяГруппы` и отделённый от других пустыми строками.

Проект переписан на **Python 3.11 + WinUI 3 (PyWinRT)**. Старая
PowerShell-версия сохранена в `legacy/` до завершения приёмки.

## Как это работает

1. Скачивает файл `hosts` из источника.
2. Берёт дату из второй строки источника: `# Последнее обновление: ...`.
3. Если дата в локальном `hosts` совпадает — ничего не пишет.
4. Иначе создаёт резервную копию, заменяет **целиком** каждую именованную
   группу, которая есть и локально, и в источнике, обновляет маркер даты,
   атомарно записывает файл и сбрасывает DNS-кеш.

Группы, которые есть только в источнике, и блоки без имени (стандартный
заголовок Windows и т.п.) остаются без изменений.

## Установка (для разработки)

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev,ui]"
```

## Запуск

```powershell
# UI (WinUI 3)
.venv\Scripts\python.exe -m autohostupdate

# CLI
.venv\Scripts\python.exe -m autohostupdate --check
.venv\Scripts\python.exe -m autohostupdate --update
.venv\Scripts\python.exe -m autohostupdate --update --dry-run --quiet
.venv\Scripts\python.exe -m autohostupdate --install-task
.venv\Scripts\python.exe -m autohostupdate --uninstall-task
.venv\Scripts\python.exe -m autohostupdate --task-status
.venv\Scripts\python.exe -m autohostupdate --restore <путь к .bak>
```

Изменение `hosts`, регистрация задачи и `ipconfig /flushdns` требуют прав
администратора: CLI выполняйте в elevated-консоли, UI покажет ошибку.

## Проверки

```powershell
.venv\Scripts\ruff.exe check .
.venv\Scripts\mypy.exe src
.venv\Scripts\python.exe -m pytest
```

## Сборка

```powershell
.venv\Scripts\pyinstaller.exe packaging\AutoHostUpdate.spec --noconfirm
iscc packaging\installer.iss
```

## Требования

- Windows 10 1809+ / Windows 11, x64.
- Python 3.11 (для сборки).
- Windows App Runtime 1.6+ (проверено на 1.8; bootstrap подбирает версию сам).
- Доступ в интернет к источнику.

## Состав проекта

| Путь | Назначение |
|---|---|
| `src/autohostupdate/` | Python-приложение: core, services, config, UI. |
| `tests/` | Unit/integration/UI-тесты и фикстуры. |
| `packaging/` | PyInstaller spec, манифест, Inno Setup. |
| `legacy/` | PowerShell-версия (эталон поведения, до приёмки). |
| `tools/` | Вспомогательные скрипты (spike UI). |
| `AGENTS.md` | Техническая документация для разработки. |

## Журнал и резервные копии

- Логи: `%LOCALAPPDATA%\AutoHostUpdate\logs\AutoHostUpdate.log` (ротация).
- Копии `hosts`: `%LOCALAPPDATA%\AutoHostUpdate\backups`.
- Настройки: `%LOCALAPPDATA%\AutoHostUpdate\settings.json`.
