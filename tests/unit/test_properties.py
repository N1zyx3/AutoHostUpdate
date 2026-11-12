"""Property-based проверки инвариантов записи/чтения hosts."""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from autohostupdate.core import hosts_parser, writer

# Символы, которые безопасно переживают все поддерживаемые кодировки и не
# содержат переводов строк (строки задаются списком).
_LINE = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\r\n"),
    max_size=40,
)
_DOCUMENT = st.lists(_LINE, max_size=20)
_FORMAT = st.sampled_from([("utf-8-sig", "\r\n"), ("utf-16", "\r\n"), ("utf-8-sig", "\n")])


@given(_DOCUMENT, _FORMAT, st.booleans())
@settings(max_examples=60, deadline=None)
def test_write_read_roundtrip(lines: list[str], fmt: tuple[str, str], final_newline: bool) -> None:
    encoding, newline = fmt
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "hosts"
        writer.write_hosts(
            path,
            lines,
            encoding=encoding,
            newline=newline,
            final_newline=final_newline,
        )
        document = writer.read_hosts(path)

    expected_text = newline.join(lines)
    if final_newline and lines:
        expected_text += newline
    expected = expected_text.replace("\r\n", "\n").split("\n")
    # read_hosts отбрасывает один хвостовой пустой элемент (как Read-HostsLines).
    if expected and expected[-1] == "":
        expected.pop()
    assert list(document.lines) == expected
    assert document.encoding == encoding
    # Перевод строки определяется по содержимому: у пустого файла его нет.
    if newline in expected_text:
        assert document.newline == newline


@given(_DOCUMENT)
@settings(max_examples=40, deadline=None)
def test_split_blocks_preserves_all_non_blank_lines(lines: list[str]) -> None:
    blocks = hosts_parser.split_blocks(lines)
    rebuilt = [line.rstrip() for block in blocks for line in block]
    expected = [line.rstrip() for line in lines if line.strip()]
    assert rebuilt == expected
