"""Резервные копии hosts: создание, ротация, восстановление."""

from __future__ import annotations

import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

from autohostupdate.errors import HostsWriteError

BACKUP_PREFIX = "hosts_"
BACKUP_SUFFIX = ".bak"


def create_backup(
    hosts_path: str | Path,
    backup_dir: str | Path,
    *,
    now: datetime | None = None,
) -> Path:
    """Копирует hosts в `backup_dir/hosts_YYYYmmdd_HHMMSS.bak`."""
    source = Path(hosts_path)
    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    target = target_dir / f"{BACKUP_PREFIX}{stamp}{BACKUP_SUFFIX}"
    if target.exists():
        target = (
            target_dir / f"{BACKUP_PREFIX}{stamp}_{int(time.time() * 1000) % 1000}{BACKUP_SUFFIX}"
        )
    try:
        shutil.copy2(source, target)
    except OSError as exc:
        raise HostsWriteError(f"Не удалось создать резервную копию: {exc}") from exc
    return target


def list_backups(backup_dir: str | Path) -> list[Path]:
    directory = Path(backup_dir)
    if not directory.exists():
        return []
    backups = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.name.startswith(BACKUP_PREFIX) and path.suffix == BACKUP_SUFFIX
    ]
    return sorted(backups, key=lambda path: path.stat().st_mtime, reverse=True)


def prune_backups(
    backup_dir: str | Path,
    *,
    keep_count: int = 10,
    keep_days: int = 30,
    now: datetime | None = None,
) -> list[Path]:
    """Удаляет старые копии по количеству и возрасту. Возвращает удалённые."""
    backups = list_backups(backup_dir)
    deadline = (now or datetime.now()) - timedelta(days=keep_days)
    removed: list[Path] = []
    for index, path in enumerate(backups):
        is_old = datetime.fromtimestamp(path.stat().st_mtime) < deadline
        if index >= keep_count or is_old:
            try:
                path.unlink()
                removed.append(path)
            except OSError:
                continue
    return removed


def restore_backup(backup_path: str | Path, hosts_path: str | Path) -> None:
    """Восстанавливает hosts из копии."""
    source = Path(backup_path)
    target = Path(hosts_path)
    try:
        from autohostupdate.core.writer import write_atomic

        write_atomic(target, source.read_bytes())
    except OSError as exc:
        raise HostsWriteError(f"Не удалось восстановить hosts из {source}: {exc}") from exc
