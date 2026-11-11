from __future__ import annotations

import zipfile

from autohostupdate.config.schema import AppSettings
from autohostupdate.services.logging import (
    LogQuery,
    clear_log,
    export_diagnostics,
    read_log_tail,
    redact,
)

TEXT_LOG = "\n".join(
    [
        "2026-11-11 10:00:00,000  DEBUG  first debug",
        "2026-11-11 10:00:01,000  INFO  Источник: дата=2026-11-09",
        "2026-11-11 10:00:02,000  WARNING  Что-то не так",
        "2026-11-11 10:00:03,000  ERROR  Падение записи",
        "2026-11-11 10:00:04,000  INFO  Готово",
    ]
)


def test_read_tail_default_returns_last_lines(tmp_path) -> None:
    log = tmp_path / "app.log"
    log.write_text(TEXT_LOG, encoding="utf-8")

    lines = read_log_tail(log, LogQuery(limit=2))

    assert lines == [
        "2026-11-11 10:00:03,000  ERROR  Падение записи",
        "2026-11-11 10:00:04,000  INFO  Готово",
    ]


def test_read_tail_filters_by_level_and_search(tmp_path) -> None:
    log = tmp_path / "app.log"
    log.write_text(TEXT_LOG, encoding="utf-8")

    assert read_log_tail(log, LogQuery(level="ERROR")) == [
        "2026-11-11 10:00:03,000  ERROR  Падение записи"
    ]
    assert read_log_tail(log, LogQuery(search="источник")) == [
        "2026-11-11 10:00:01,000  INFO  Источник: дата=2026-11-09"
    ]


def test_read_tail_missing_file_is_empty(tmp_path) -> None:
    assert read_log_tail(tmp_path / "nope.log") == []


def test_clear_log_truncates(tmp_path) -> None:
    log = tmp_path / "app.log"
    log.write_text(TEXT_LOG, encoding="utf-8")

    clear_log(log)

    assert log.read_text(encoding="utf-8") == ""
    clear_log(tmp_path / "absent.log")


def test_export_diagnostics_collects_logs_and_environment(tmp_path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "app.log").write_text(TEXT_LOG, encoding="utf-8")
    (log_dir / "app.log.1").write_text("old line\n", encoding="utf-8")
    settings = AppSettings()
    target = tmp_path / "diag.zip"

    result = export_diagnostics(target, log_dir / "app.log", settings, version="9.9.9")

    assert result == target
    with zipfile.ZipFile(target) as archive:
        names = set(archive.namelist())
        environment = archive.read("environment.txt").decode("utf-8")
    assert names == {"app.log", "app.log.1", "environment.txt"}
    assert "version: 9.9.9" in environment
    assert "source_url:" in environment
    # Содержимое hosts в диагностику не попадает.
    assert "0.0.0.0" not in environment


def test_redact_hides_query_string() -> None:
    assert redact("GET https://example.com/hosts?token=abc HTTP/1.1") == (
        "GET https://example.com/hosts?<redacted> HTTP/1.1"
    )
