from __future__ import annotations

from pathlib import Path

import pytest

from autohostupdate.core.source import decode_source, parse_source
from autohostupdate.errors import SourceFormatError

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_parse_fixture() -> None:
    text = (FIXTURES / "source.txt").read_text(encoding="utf-8")
    snapshot = parse_source(text, url="https://example.test/hosts")
    assert snapshot.date_value == "2026-11-09 10:00:00"
    assert len(snapshot.groups) == 4
    assert "Google" in snapshot.group_map()


def test_rejects_short_file() -> None:
    with pytest.raises(SourceFormatError):
        parse_source("# only one line")


def test_rejects_missing_marker() -> None:
    with pytest.raises(SourceFormatError):
        parse_source("# header\n127.0.0.1 localhost\n\n# A\n1.1.1.1 a")


def test_allows_missing_marker_when_not_required() -> None:
    snapshot = parse_source("# header\n# A\n1.1.1.1 a", require_date=False)
    assert snapshot.date_value == ""
    assert len(snapshot.groups) == 1


def test_rejects_no_groups() -> None:
    with pytest.raises(SourceFormatError):
        parse_source("127.0.0.1 localhost\n1.1.1.1 x", require_date=False)


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"\xef\xbb\xbf# x", "# x"),
        ("# x".encode("utf-16"), "# x"),
        ("# Локальная".encode("cp1251"), "# Локальная"),
        (b"# x", "# x"),
    ],
)
def test_decode_source(data: bytes, expected: str) -> None:
    assert decode_source(data) == expected


def test_decode_source_explicit_encoding() -> None:
    assert decode_source("# x".encode("utf-16-le"), "utf-16-le") == "# x"
