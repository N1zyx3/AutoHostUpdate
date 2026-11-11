"""Сравнение локального hosts с источником и построение плана обновления.

Повторяет `Update-GroupsLines` + `Set-MarkerDate` из PowerShell-версии:
обновляются только группы, присутствующие и локально, и в источнике.
"""

from __future__ import annotations

from collections.abc import Sequence

from autohostupdate.core import hosts_parser
from autohostupdate.core.models import (
    GroupChange,
    GroupStatus,
    SourceSnapshot,
    UpdatePlan,
)


def _normalize(name: str, ignore_case: bool) -> str:
    return name.casefold() if ignore_case else name


def build_plan(
    local_lines: Sequence[str],
    snapshot: SourceSnapshot,
    prefix: str = hosts_parser.DEFAULT_MARKER_PREFIX,
    *,
    skip_names: Sequence[str] = (),
    force_add_names: Sequence[str] = (),
    ignore_case: bool = False,
) -> UpdatePlan:
    """Строит план обновления.

    ``skip_names`` — группы, которые нельзя менять (пользователь отключил);
    ``force_add_names`` — группы, которых локально нет, но их нужно добавить.
    ``ignore_case`` — сопоставлять имена без учёта регистра.
    """
    blocks = hosts_parser.split_blocks(local_lines)
    source_groups = {_normalize(group.name, ignore_case): group for group in snapshot.groups}
    skip = {_normalize(name, ignore_case) for name in skip_names}
    force_add = {_normalize(name, ignore_case) for name in force_add_names}
    local_names: set[str] = set()

    out: list[str] = []
    changes: list[GroupChange] = []

    for block in blocks:
        name = hosts_parser.block_name(block)
        if name is None:
            out.extend(block)
            out.append("")
            continue

        key = _normalize(name, ignore_case)
        local_names.add(key)
        source_group = source_groups.get(key)

        if key in skip:
            changes.append(
                GroupChange(
                    name=name,
                    status=GroupStatus.DISABLED,
                    old_lines=tuple(block),
                    new_lines=source_group.lines if source_group else (),
                )
            )
            out.extend(block)
            out.append("")
            continue

        if source_group is None:
            changes.append(
                GroupChange(name=name, status=GroupStatus.LOCAL_ONLY, old_lines=tuple(block))
            )
            out.extend(block)
            out.append("")
            continue

        status = (
            GroupStatus.UP_TO_DATE if tuple(block) == source_group.lines else GroupStatus.OUTDATED
        )
        changes.append(
            GroupChange(
                name=name,
                status=status,
                old_lines=tuple(block),
                new_lines=source_group.lines,
            )
        )
        out.extend(source_group.lines)
        out.append("")

    if out and out[-1] == "":
        out.pop()

    added: list[str] = []
    for group in snapshot.groups:
        key = _normalize(group.name, ignore_case)
        if key in local_names:
            continue
        if key in force_add:
            if out:
                out.append("")
            out.extend(group.lines)
            added.append(group.name)
        changes.append(
            GroupChange(name=group.name, status=GroupStatus.SOURCE_ONLY, new_lines=group.lines)
        )

    local_date = hosts_parser.find_marker(local_lines, prefix)
    new_lines = hosts_parser.replace_marker(out, snapshot.date_value, prefix)
    marker_changed = tuple(new_lines) != tuple(out) or not hosts_parser.find_marker(out, prefix)

    return UpdatePlan(
        changes=tuple(changes),
        source_date=snapshot.date_value,
        local_date=local_date,
        new_lines=tuple(new_lines),
        marker_changed=marker_changed,
        added_groups=tuple(added),
    )


def render_plan(plan: UpdatePlan, *, limit: int = 20) -> str:
    """Короткий текстовый отчёт по плану (для CLI и логов)."""
    lines = [
        f"Источник: {plan.source_date or '—'}",
        f"Локально: {plan.local_date or '—'}",
        f"Групп к обновлению: {plan.changed_count}",
    ]
    for index, change in enumerate(plan.changed_groups):
        if index >= limit:
            lines.append(f"... и ещё {plan.changed_count - index}")
            break
        lines.append(f"  - {change.name}: {len(change.old_lines)} -> {len(change.new_lines)} строк")
    return "\n".join(lines)
