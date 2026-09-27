# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller bundle for SVD Studio. Output goes to Releases/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

block_cipher = None

a = Analysis(
    ["svdstudio/app.py"],
    pathex=[str(Path.cwd())],
    binaries=[],
    datas=[
        ("resources/ui/*.ui", "resources/ui"),
        ("resources/styles/*.qss", "resources/styles"),
        ("resources/icons/*.png", "resources/icons"),
        ("resources/icons/*.ico", "resources/icons"),
    ],
    hiddenimports=["PySide6.QtXml", "lxml", "yaml", "openpyxl"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="SVDStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="resources/icons/svd-studio.ico",
)
