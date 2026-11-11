"""Доменные модели: не зависят от UI, сети и Win32."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

Comment = str
Lines = tuple[str, ...]


class GroupStatus(StrEnum):
    """Статус именованной группы при сравнении local <-> source."""

    UP_TO_DATE = "up_to_date"
    OUTDATED = "outdated"
    LOCAL_ONLY = "local_only"
    SOURCE_ONLY = "source_only"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class Group:
    """Именованная группа hosts: заголовок `# Name` + строки записей."""

    name: str
    lines: Lines

    @property
    def entry_count(self) -> int:
        """Количество некомментарных строк в группе."""
        return sum(1 for line in self.lines if line.strip() and not line.lstrip().startswith("#"))

    @property
    def text(self) -> str:
        """Нормализованный текст группы (для сравнения)."""
        return "\n".join(self.lines)


@dataclass(frozen=True, slots=True)
class HostsDocument:
    """Разобранный локальный hosts."""

    path: str
    lines: Lines
    encoding: str = "utf-8-sig"
    newline: str = "\r\n"
    trailing_newline: bool = False
    raw_bytes: bytes = b""

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    """Снимок источника: дата из маркера и именованные группы."""

    date_value: str
    groups: tuple[Group, ...]
    url: str = ""

    def group_map(self) -> dict[str, Group]:
        return {group.name: group for group in self.groups}


@dataclass(frozen=True, slots=True)
class GroupChange:
    """Одно изменение группы между локальным hosts и источником."""

    name: str
    status: GroupStatus
    old_lines: Lines = ()
    new_lines: Lines = ()

    @property
    def changed(self) -> bool:
        """Группа будет заменена в hosts."""
        return self.status is GroupStatus.OUTDATED and self.old_lines != self.new_lines

    @property
    def lines_added(self) -> int:
        return max(0, len(self.new_lines) - len(self.old_lines))

    @property
    def lines_removed(self) -> int:
        return max(0, len(self.old_lines) - len(self.new_lines))


@dataclass(frozen=True, slots=True)
class UpdatePlan:
    """План обновления: что и как изменится."""

    changes: tuple[GroupChange, ...] = ()
    source_date: str = ""
    local_date: str = ""
    new_lines: Lines = ()
    marker_changed: bool = False
    added_groups: tuple[str, ...] = ()

    @property
    def changed_groups(self) -> tuple[GroupChange, ...]:
        return tuple(change for change in self.changes if change.changed)

    @property
    def changed_count(self) -> int:
        return len(self.changed_groups)

    @property
    def has_changes(self) -> bool:
        """Есть ли изменения текста hosts (группы или маркер)."""
        return bool(self.changed_count) or self.marker_changed


@dataclass(frozen=True, slots=True)
class UpdateResult:
    """Результат выполнения обновления."""

    source_date: str = ""
    previous_date: str = ""
    changed_groups: tuple[str, ...] = ()
    backup_path: str | None = None
    written: bool = False
    dry_run: bool = False
    skipped_reason: str | None = None
    log_paths: tuple[str, ...] = field(default_factory=tuple)

    @property
    def skipped(self) -> bool:
        return self.skipped_reason is not None
