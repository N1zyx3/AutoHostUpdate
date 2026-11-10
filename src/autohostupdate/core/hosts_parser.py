"""Парсер hosts: разбиение на блоки, именованные группы, маркер даты.

Повторяет поведение `Split-Blocks`, `Get-NamedGroups`, `Get-MarkerDate`
и `Set-MarkerDate` из PowerShell-версии (см. legacy/AutoHostUpdate.ps1).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from autohostupdate.core.models import Group

DEFAULT_MARKER_PREFIX = "Последнее обновление:"
MARKER_LINE_INDEX = 1  # 1-based: вторая строка источника

_HEADER_RE = re.compile(r"^#")
_COMMENT_RE = re.compile(r"^\s*#")


def marker_regex(prefix: str = DEFAULT_MARKER_PREFIX) -> re.Pattern[str]:
    """Регулярка строки маркера: `# <prefix> <value>`."""
    return re.compile(r"^#\s*" + re.escape(prefix) + r"\s*(.*)$", re.IGNORECASE)


def normalize_text(text: str) -> str:
    """Приводит переводы строк к LF и убирает BOM, если он остался в строке."""
    if text.startswith("\ufeff"):
        text = text[1:]
    return text.replace("\r\n", "\n").replace("\r", "\n")


def split_lines(text: str) -> list[str]:
    """Текст -> строки без завершающего перевода строки.

    Соответствует `Read-HostsLines`: один хвостовой пустой элемент отбрасывается.
    """
    lines = normalize_text(text).split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def split_blocks(lines: Iterable[str]) -> list[tuple[str, ...]]:
    """Разбиение на блоки по строкам из одних пробелов.

    Каждая непустая строка обрезается справа (`TrimEnd`), как в PowerShell.
    Пустые строки внутрь блока не попадают.
    """
    blocks: list[tuple[str, ...]] = []
    current: list[str] = []
    for line in lines:
        if line is None:  # защита от None в исходных данных
            line = ""
        if not line.strip():
            if current:
                blocks.append(tuple(current))
                current = []
        else:
            current.append(line.rstrip())
    if current:
        blocks.append(tuple(current))
    return blocks


def has_entries(block: Sequence[str]) -> bool:
    """Есть ли в блоке хотя бы одна некомментарная строка."""
    return any(not _COMMENT_RE.match(line) for line in block)


def block_name(block: Sequence[str]) -> str | None:
    """Имя именованной группы или None, если блок не является группой."""
    if not block or not _HEADER_RE.match(block[0]):
        return None
    if not has_entries(block):
        return None
    name = block[0].lstrip("# ").strip()
    return name or None


def named_groups(blocks: Iterable[Sequence[str]]) -> list[Group]:
    """Именованные группы из блоков (порядок сохраняется)."""
    groups: list[Group] = []
    for block in blocks:
        name = block_name(block)
        if name is not None:
            groups.append(Group(name=name, lines=tuple(block)))
    return groups


def parse_groups(lines: Iterable[str]) -> list[Group]:
    return named_groups(split_blocks(lines))


def find_marker(lines: Iterable[str], prefix: str = DEFAULT_MARKER_PREFIX) -> str:
    """Значение маркера в первой подходящей строке или пустая строка."""
    pattern = marker_regex(prefix)
    for line in lines:
        match = pattern.match(line)
        if match:
            return match.group(1).strip()
    return ""


def marker_line(value: str, prefix: str = DEFAULT_MARKER_PREFIX) -> str:
    return f"# {prefix} {value}"


def replace_marker(
    lines: Sequence[str], value: str, prefix: str = DEFAULT_MARKER_PREFIX
) -> list[str]:
    """Заменяет все строки маркера; если их нет — добавляет в начало."""
    pattern = marker_regex(prefix)
    new_line = marker_line(value, prefix)
    out: list[str] = []
    replaced = False
    for line in lines:
        if pattern.match(line):
            out.append(new_line)
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.insert(0, new_line)
    return out


def source_date(lines: Sequence[str], prefix: str = DEFAULT_MARKER_PREFIX) -> str:
    """Дата источника: маркер строго во второй строке (1-based index 2)."""
    if len(lines) <= MARKER_LINE_INDEX:
        return ""
    match = marker_regex(prefix).match(lines[MARKER_LINE_INDEX])
    return match.group(1).strip() if match else ""
