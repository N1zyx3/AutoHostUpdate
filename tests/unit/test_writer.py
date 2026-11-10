from __future__ import annotations

import os
from pathlib import Path

import pytest

from autohostupdate.core import hosts_parser, writer
from autohostupdate.errors import HostsReadError, HostsWriteError


def test_roundtrip_utf8_bom_crlf(tmp_path: Path) -> None:
    target = tmp_path / "hosts"
    lines = ["# Header", "127.0.0.1 localhost"]
    writer.write_hosts(target, lines)

    raw = target.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in raw
    assert not raw.endswith(b"\n")

    document = writer.read_hosts(target)
    assert document.lines == tuple(lines)
    assert document.encoding == "utf-8-sig"


def test_read_detects_utf16_and_lf(tmp_path: Path) -> None:
    target = tmp_path / "hosts"
    target.write_bytes("a\nb\n".encode("utf-16"))
    document = writer.read_hosts(target)
    assert document.encoding == "utf-16"
    assert document.lines == ("a", "b")
    assert document.newline == "\n"


def test_read_cp1251_fallback(tmp_path: Path) -> None:
    target = tmp_path / "hosts"
    target.write_bytes("# Локальная\n1.1.1.1 x".encode("cp1251"))
    document = writer.read_hosts(target)
    assert document.encoding == "cp1251"
    assert document.lines[0] == "# Локальная"


def test_read_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(HostsReadError):
        writer.read_hosts(tmp_path / "nope")


def test_write_atomic_replaces_without_leftovers(tmp_path: Path) -> None:
    target = tmp_path / "hosts"
    target.write_text("old", encoding="utf-8")
    writer.write_atomic(target, b"new")
    assert target.read_bytes() == b"new"
    assert [path.name for path in tmp_path.iterdir()] == ["hosts"]


def test_write_atomic_clears_readonly_target(tmp_path: Path) -> None:
    target = tmp_path / "hosts"
    target.write_text("old", encoding="utf-8")
    os.chmod(target, 0o444)
    assert writer.clear_readonly(target) is True
    writer.write_atomic(target, b"new")
    assert target.read_bytes() == b"new"


def test_write_hosts_validation_catches_corruption(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "hosts"
    monkeypatch.setattr(writer, "encode_lines", lambda *a, **k: b"\x00\x01")
    with pytest.raises(HostsWriteError):
        writer.write_hosts(target, ["a"])


def test_write_hosts_preserves_custom_lines(tmp_path: Path) -> None:
    target = tmp_path / "hosts"
    lines = ["# A", "1.1.1.1 a", "", "# B", "2.2.2.2 b"]
    writer.write_hosts(target, lines, final_newline=True)
    raw = target.read_bytes()
    assert raw.endswith(b"\r\n")
    assert hosts_parser.split_lines(raw.decode("utf-8-sig")) == lines


def test_encode_lines_newline_modes() -> None:
    assert writer.encode_lines(["a", "b"], "utf-8", "\n") == b"a\nb"
    assert writer.encode_lines(["a"], "utf-8", "\n", final_newline=True) == b"a\n"
