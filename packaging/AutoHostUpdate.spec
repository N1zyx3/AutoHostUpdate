# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: --onedir --noconsole.

Сборка: .venv\\Scripts\\pyinstaller.exe packaging\\AutoHostUpdate.spec
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"

datas: list[tuple[str, str]] = []
binaries: list[tuple[str, str]] = []
hiddenimports: list[str] = []

for package in ("winrt",):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

datas.append(
    (str(SRC / "autohostupdate" / "ui" / "xaml"), "autohostupdate/ui/xaml")
)

hiddenimports += [
    "autohostupdate.ui.bootstrap",
    "autohostupdate.ui.application",
    "autohostupdate.ui.main_window",
]

a = Analysis(
    [str(SRC / "autohostupdate" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AutoHostUpdate",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    manifest=str(ROOT / "packaging" / "app.manifest"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="AutoHostUpdate",
)
