from __future__ import annotations

import sys

from autohostupdate.services import privileges


def test_is_admin_returns_bool() -> None:
    assert isinstance(privileges.is_admin(), bool)


def test_command_uses_module_invocation_for_source(monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)

    executable, params = privileges._command(["--install-task", "--quiet"])

    assert executable
    assert "-m autohostupdate" in params
    assert "--install-task" in params


def test_command_uses_executable_when_frozen(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Apps\AutoHostUpdate.exe")

    executable, params = privileges._command(["--update"])

    assert executable == r"C:\Apps\AutoHostUpdate.exe"
    assert params == "--update"
