from __future__ import annotations

from pathlib import Path

import pytest

from autohostupdate.core import hosts_parser

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_split_blocks_trims_and_skips_blank_runs() -> None:
    blocks = hosts_parser.split_blocks(["a  ", "", "  ", "b\t", "", "# c"])
    assert blocks == [("a",), ("b",), ("# c",)]


def test_split_blocks_ignores_none() -> None:
    assert hosts_parser.split_blocks([None, "x"]) == [("x",)]


def test_split_lines_drops_single_trailing_newline() -> None:
    assert hosts_parser.split_lines("a\r\nb\r\n") == ["a", "b"]
    assert hosts_parser.split_lines("a\nb") == ["a", "b"]
    assert hosts_parser.split_lines("a\n\n") == ["a", ""]


def test_split_lines_strips_bom() -> None:
    assert hosts_parser.split_lines("\ufeffa\n") == ["a"]


def test_block_name_requires_comment_header_and_entry() -> None:
    assert hosts_parser.block_name(("# Google", "1.1.1.1 x")) == "Google"
    assert hosts_parser.block_name(("## Google", "1.1.1.1 x")) == "Google"
    assert hosts_parser.block_name(("# Only comment", "# second")) is None
    assert hosts_parser.block_name(("1.1.1.1 x",)) is None
    assert hosts_parser.block_name(("# ", "1.1.1.1 x")) is None


def test_named_groups_from_fixture() -> None:
    lines = hosts_parser.split_lines((FIXTURES / "source.txt").read_text(encoding="utf-8"))
    groups = hosts_parser.parse_groups(lines)
    assert [group.name for group in groups] == [
        "Google",
        "YouTube",
        "Discord",
        "Только в источнике",
    ]
    assert groups[0].entry_count == 2
    assert groups[1].lines[0] == "# YouTube"


def test_find_and_replace_marker() -> None:
    lines = ["# Последнее обновление: old", "127.0.0.1 localhost"]
    assert hosts_parser.find_marker(lines) == "old"
    replaced = hosts_parser.replace_marker(lines, "new")
    assert replaced[0] == "# Последнее обновление: new"
    assert len(replaced) == 2


def test_replace_marker_inserts_when_missing() -> None:
    replaced = hosts_parser.replace_marker(["127.0.0.1 localhost"], "2026-01-01")
    assert replaced == ["# Последнее обновление: 2026-01-01", "127.0.0.1 localhost"]


def test_source_date_requires_second_line() -> None:
    assert hosts_parser.source_date(["# header", "# Последнее обновление: d1"]) == "d1"
    assert hosts_parser.source_date(["# Последнее обновление: d1"]) == ""
    assert hosts_parser.source_date(["# header", "no marker"]) == ""


@pytest.mark.parametrize("line", ["#Последнее обновление: x", "#  Последнее обновление:   x  "])
def test_marker_regex_is_lenient(line: str) -> None:
    assert hosts_parser.find_marker([line]) == "x"
