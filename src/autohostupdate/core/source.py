"""Разбор ответа источника GeoHideDNS."""

from __future__ import annotations

from autohostupdate.core import hosts_parser
from autohostupdate.core.models import SourceSnapshot
from autohostupdate.errors import SourceFormatError

MAX_SOURCE_BYTES = 2048 * 1024


def decode_source(data: bytes, encoding: str = "auto") -> str:
    """Декодирование ответа источника с учётом BOM."""
    if encoding != "auto":
        return data.decode(encoding, errors="replace").lstrip("\ufeff")

    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    if data.startswith(b"\xff\xfe"):
        return data.decode("utf-16")
    if data.startswith(b"\xfe\xff"):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1251", errors="replace")


def parse_source(text: str, *, url: str = "", require_date: bool = True) -> SourceSnapshot:
    """Собирает снимок источника: дата из второй строки и именованные группы."""
    lines = hosts_parser.split_lines(text)
    if len(lines) < 2:
        raise SourceFormatError("Файл источника слишком короткий или пуст.")

    date_value = hosts_parser.source_date(lines)
    if require_date and not date_value:
        raise SourceFormatError(
            f"Не найдена строка '{hosts_parser.DEFAULT_MARKER_PREFIX}' во 2-й строке источника."
        )

    groups = tuple(hosts_parser.parse_groups(lines))
    if not groups:
        raise SourceFormatError("В источнике не найдено ни одной именованной группы.")
    return SourceSnapshot(date_value=date_value, groups=groups, url=url)
