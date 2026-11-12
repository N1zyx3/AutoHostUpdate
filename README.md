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
# UI (WinUI 3): 7 страниц — Обзор, Группы, Источник, Расписание, Журнал,
# Настройки, О программе
.venv\Scripts\python.exe -m autohostupdate

# CLI
.venv\Scripts\python.exe -m autohostupdate --check
.venv\Scripts\python.exe -m autohostupdate --update
.venv\Scripts\python.exe -m autohostupdate --update --dry-run --quiet
.venv\Scripts\python.exe -m autohostupdate --install-task
.venv\Scripts\python.exe -m autohostupdate --uninstall-task
.venv\Scripts\python.exe -m autohostupdate --task-status
.venv\Scripts\python.exe -m autohostupdate --restore <путь к .bak>

# offline-проверка на файле вместо сети (тесты, отладка)
.venv\Scripts\python.exe -m autohostupdate --check --source-file tests\fixtures\source.txt --json
```

Изменение `hosts`, регистрация задачи и `ipconfig /flushdns` требуют прав
администратора. CLI выполняйте в elevated-консоли; UI сам запросит UAC и
выполнит операцию через свой CLI-helper, а при отказе покажет ошибку.

## Возможности UI

- **Обзор** — дата источника и локального маркера, кнопки «Проверить»,
  «Обновить», «Dry-run», индикатор занятости и строка состояния.
- **Группы** — список локальных групп со статусом, поиск, включение/выключение
  обновления отдельной группы (сохраняется в `disabled_groups`).
- **Источник** — URL, таймаут, повторы, максимальный размер, префикс маркера,
  TLS, прокси, «Проверить соединение» и предпросмотр ответа.
- **Расписание** — триггер (вход/ежедневно/интервал/вручную), время, задержка,
  условия питания, установка/удаление/запуск задачи, статус из Планировщика.
- **Журнал** — фильтр по уровню и поиск, открыть файл, очистить, экспорт
  диагностики в zip (журналы + сводка окружения, без содержимого `hosts`).
- **Настройки** — общие, источник, обновление и backup, уведомления, журнал;
  сохранение с валидацией и сброс к значениям по умолчанию.
- **Резервные копии** (в «Настройках») — список копий с датой и размером,
  восстановление hosts из выбранной копии (двойное подтверждение, нужны права
  администратора) и открытие каталога копий.

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
