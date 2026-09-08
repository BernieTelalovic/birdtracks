# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_submodules,
    copy_metadata,
)


project_root = Path(SPECPATH).parent
datas = [
    (
        str(project_root / "src/birdtracks/projectors/canvas_app.py"),
        "birdtracks/projectors",
    ),
    (str(Path(sys.prefix) / "share" / "jupyter"), "share/jupyter"),
]
hiddenimports = []
binaries = []
for package in ("anywidget", "igraph", "ipykernel", "voila"):
    package_datas, package_binaries, package_imports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_imports
for package in (
    "birdtracks",
    "jupyter_events",
    "jupyter_server",
    "jupyterlab_server",
    "nbconvert",
    "nbformat",
    "rfc3987_syntax",
):
    datas += collect_data_files(package)
datas += copy_metadata("birdtracks")
hiddenimports += collect_submodules("birdtracks")

a = Analysis(
    [str(project_root / "src/birdtracks/projectors/standalone.py")],
    pathex=[str(project_root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Birdtracks",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
