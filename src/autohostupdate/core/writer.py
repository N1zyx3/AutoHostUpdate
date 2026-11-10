"""Чтение и атомарная запись hosts."""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

from autohostupdate.core import hosts_parser
from autohostupdate.core.models import HostsDocument
from autohostupdate.errors import HostsReadError, HostsWriteError

DEFAULT_ENCODING = "utf-8-sig"
DEFAULT_NEWLINE = "\r\n"


def decode_bytes(data: bytes) -> tuple[str, str]:
    """Декодирует байты hosts и возвращает (текст, имя кодировки)."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig"
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16"), "utf-16"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("cp1251", errors="replace"), "cp1251"


def read_hosts(path: str | os.PathLike[str]) -> HostsDocument:
    """Читает hosts, определяя кодировку и перевод строки."""
    host_path = Path(path)
    try:
        raw = host_path.read_bytes()
    except OSError as exc:
        raise HostsReadError(f"Не удалось прочитать hosts: {host_path}: {exc}") from exc

    text, encoding = decode_bytes(raw)
    newline = "\r\n" if b"\r\n" in raw else "\n"
    trailing_newline = text.endswith(("\n", "\r"))
    lines = hosts_parser.split_lines(text)
    return HostsDocument(
        path=str(host_path),
        lines=tuple(lines),
        encoding=encoding,
        newline=newline,
        trailing_newline=trailing_newline,
        raw_bytes=raw,
    )


def encode_lines(
    lines: Sequence[str],
    encoding: str = DEFAULT_ENCODING,
    newline: str = DEFAULT_NEWLINE,
    final_newline: bool = False,
) -> bytes:
    text = newline.join(lines)
    if final_newline and lines:
        text += newline
    return text.encode(encoding if encoding != "utf-8-sig" else "utf-8-sig")


def clear_readonly(path: Path) -> bool:
    """Снимает атрибут ReadOnly. Возвращает True, если атрибут был снят."""
    if not path.exists():
        return False
    mode = path.stat().st_mode
    if mode & 0o200:
        return False
    try:
        os.chmod(path, mode | 0o200)
    except OSError as exc:  # pragma: no cover - зависит от ОС
        raise HostsWriteError(f"Не удалось снять атрибут ReadOnly: {path}: {exc}") from exc
    return True


def write_atomic(
    path: str | os.PathLike[str],
    data: bytes,
    *,
    preserve_attributes: bool = True,
    retries: int = 3,
) -> None:
    """Атомарная замена файла: temp в том же каталоге + `os.replace`.

    Временный файл копируется с оригинала (`copy2` сохраняет ACL и атрибуты),
    затем перезаписывается содержимым. ReadOnly на самом hosts не трогается.
    """
    host_path = Path(path)
    parent = host_path.parent
    if not parent.exists():
        raise HostsWriteError(f"Каталог не существует: {parent}")

    fd, tmp_name = tempfile.mkstemp(prefix=".autohostupdate-", suffix=".tmp", dir=parent)
    os.close(fd)
    tmp_path = Path(tmp_name)

    try:
        if host_path.exists() and preserve_attributes:
            shutil.copyfile(host_path, tmp_path)  # на Windows копирует и security descriptor
            shutil.copystat(host_path, tmp_path)
        clear_readonly(tmp_path)
        tmp_path.write_bytes(data)

        last_error: OSError | None = None
        for attempt in range(retries):
            try:
                os.replace(tmp_path, host_path)
                return
            except PermissionError as exc:  # антивирус/индексатор могут держать файл
                last_error = exc
                time.sleep(0.15 * (attempt + 1))
        raise HostsWriteError(f"Не удалось заменить hosts: {host_path}: {last_error}")
    except HostsWriteError:
        raise
    except OSError as exc:
        raise HostsWriteError(f"Не удалось записать hosts: {host_path}: {exc}") from exc
    finally:
        if tmp_path.exists():
            try:
                clear_readonly(tmp_path)
                tmp_path.unlink()
            except OSError:
                pass


def write_hosts(
    path: str | os.PathLike[str],
    lines: Sequence[str],
    *,
    encoding: str = DEFAULT_ENCODING,
    newline: str = DEFAULT_NEWLINE,
    final_newline: bool = False,
    validate: bool = True,
) -> None:
    """Записывает строки hosts атомарно с проверкой результата."""
    data = encode_lines(lines, encoding, newline, final_newline)
    if validate:
        decoded, _ = decode_bytes(data)
        if hosts_parser.split_lines(decoded) != list(lines):
            raise HostsWriteError("Проверка результата записи не пройдена: текст не совпадает.")
    write_atomic(path, data)
