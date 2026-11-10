"""Доменный слой AutoHostUpdate (без UI, сети и Win32)."""

from __future__ import annotations

from autohostupdate.core.models import (
    Group,
    GroupChange,
    GroupStatus,
    HostsDocument,
    SourceSnapshot,
    UpdatePlan,
    UpdateResult,
)

__all__ = [
    "Group",
    "GroupChange",
    "GroupStatus",
    "HostsDocument",
    "SourceSnapshot",
    "UpdatePlan",
    "UpdateResult",
]
