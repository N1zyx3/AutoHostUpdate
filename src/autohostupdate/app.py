"""Точка входа: выбор UI или CLI."""

from __future__ import annotations

import sys


def choose_mode(argv: list[str]) -> str:
    """`ui`, если аргументов нет; иначе `cli` (headless/helper)."""
    return "cli" if argv else "ui"


def run_ui() -> int:
    from autohostupdate.ui.bootstrap import run_application

    return run_application()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if choose_mode(args) == "cli":
        from autohostupdate.cli import main as cli_main

        return cli_main(args)

    try:
        return run_ui()
    except ModuleNotFoundError as exc:  # UI-пакеты ещё не установлены
        print(
            "AutoHostUpdate: UI-компоненты не установлены "
            f"({exc.name}). Используйте CLI (--update / --check).",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
