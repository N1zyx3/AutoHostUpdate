from __future__ import annotations

from pathlib import Path

from autohostupdate.core import diff, hosts_parser
from autohostupdate.core.models import Group, GroupStatus, SourceSnapshot
from autohostupdate.core.source import parse_source

FIXTURES = Path(__file__).parent.parent / "fixtures"


def load_source() -> SourceSnapshot:
    return parse_source((FIXTURES / "source.txt").read_text(encoding="utf-8"))


def local_lines() -> list[str]:
    return hosts_parser.split_lines((FIXTURES / "hosts_local.txt").read_text(encoding="utf-8"))


def test_plan_updates_only_existing_groups() -> None:
    plan = diff.build_plan(local_lines(), load_source())
    statuses = {change.name: change.status for change in plan.changes}

    assert statuses["Google"] is GroupStatus.OUTDATED
    assert statuses["YouTube"] is GroupStatus.OUTDATED
    assert statuses["Моя локальная группа"] is GroupStatus.LOCAL_ONLY
    assert statuses["Discord"] is GroupStatus.SOURCE_ONLY
    assert statuses["Только в источнике"] is GroupStatus.SOURCE_ONLY
    assert plan.changed_count == 2


def test_plan_keeps_local_groups_and_unrelated_lines() -> None:
    plan = diff.build_plan(local_lines(), load_source())
    text = "\n".join(plan.new_lines)
    assert "nas.local" in text
    assert "127.0.0.1       localhost" in text
    assert "gateway.discord.gg" not in text
    assert "source-only.example" not in text


def test_plan_updates_marker() -> None:
    plan = diff.build_plan(local_lines(), load_source())
    assert plan.local_date == "2026-10-01 08:00:00"
    assert plan.source_date == "2026-11-09 10:00:00"
    assert plan.new_lines[6] == "# Последнее обновление: 2026-11-09 10:00:00"
    assert plan.marker_changed


def test_plan_inserts_marker_when_missing() -> None:
    lines = hosts_parser.split_lines((FIXTURES / "hosts_no_marker.txt").read_text(encoding="utf-8"))
    plan = diff.build_plan(lines, load_source())
    assert plan.local_date == ""
    assert plan.new_lines[0] == "# Последнее обновление: 2026-11-09 10:00:00"


def test_plan_stable_when_everything_matches() -> None:
    snapshot = SourceSnapshot(
        date_value="2026-01-01",
        groups=(Group(name="A", lines=("# A", "1.1.1.1 a.example")),),
    )
    lines = ["# Последнее обновление: 2026-01-01", "", "# A", "1.1.1.1 a.example"]
    plan = diff.build_plan(lines, snapshot)
    assert plan.changed_count == 0
    assert plan.new_lines == tuple(lines)
    assert not plan.has_changes


def test_render_plan_contains_summary() -> None:
    report = diff.render_plan(diff.build_plan(local_lines(), load_source()))
    assert "2026-11-09 10:00:00" in report
    assert "Групп к обновлению: 2" in report
