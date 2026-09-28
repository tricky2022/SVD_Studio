# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller bundle for SVD Studio. Output goes to Releases/.

Two executables from one source tree:

    Releases/SVDStudio.exe         windowed GUI; also answers --cli / --mcp
    Releases/svdstudio-cli.exe     console binary for CLI and MCP clients

The .ico is a build input and MUST exist: when the path is missing
PyInstaller only warns and ships the generic icon, which is exactly how the
packaged app previously lost its icon. Regenerate it with:

    python tools/make_icon.py

The Windows version resource is generated from svdstudio.__version__ so the
file properties (Details tab) never drift from the About dialog.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(SPECPATH)))

from svdstudio import __author__, __license__, __version__  # noqa: E402

ICON = str(Path(SPECPATH) / "resources" / "icons" / "svd-studio.ico")
if not Path(ICON).exists():
    raise SystemExit(
        f"Missing build icon: {ICON}\nRun 'python tools/make_icon.py' first.")

block_cipher = None

DATAS = [
    ("resources/ui/*.ui", "resources/ui"),
    ("resources/styles/*.qss", "resources/styles"),
    ("resources/icons/*.png", "resources/icons"),
    ("resources/icons/*.ico", "resources/icons"),
]
HIDDEN = ["PySide6.QtXml", "PySide6.QtSvg", "PySide6.QtUiTools",
          "lxml", "lxml.etree", "lxml._elementpath", "yaml", "openpyxl"]

VERSION_FILE = Path(SPECPATH) / "resources" / "version_info.txt"
try:
    from PyInstaller.utils.win32.versioninfo import (  # noqa: F401
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    parts = [int(p) for p in __version__.split(".")[:4]]
    parts += [0] * (4 - len(parts))
    # the text form PyInstaller parses is the *unprefixed* constructor form;
    # repr() emits "versioninfo." prefixes and fails to deserialize
    VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    strings = [
        ("CompanyName", __author__),
        ("FileDescription", "SVD Studio — CMSIS-SVD workbench"),
        ("FileVersion", __version__),
        ("InternalName", "SVDStudio"),
        ("OriginalFilename", "SVDStudio.exe"),
        ("ProductName", "SVD Studio"),
        ("ProductVersion", __version__),
        ("LegalCopyright", __license__),
    ]
    table = ",\n".join(f"            StringStruct({k!r}, {v!r})"
                       for k, v in strings)
    VERSION_FILE.write_text(
        "VSVersionInfo(\n"
        f"  ffi=FixedFileInfo(filevers={tuple(parts)}, prodvers={tuple(parts)},\n"
        "    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),\n"
        "  kids=[\n"
        "    StringFileInfo([\n"
        "        StringTable('040904B0', [\n"
        f"{table}\n"
        "        ])\n"
        "    ]),\n"
        "    VarFileInfo([VarStruct('Translation', [1033, 1200])])\n"
        "  ]\n"
        ")\n", encoding="utf-8")
    VERSION_ARGS = {"version": str(VERSION_FILE)}
except Exception as _exc:  # pragma: no cover - non-Windows build hosts
    print(f"version resource skipped: {_exc}")
    VERSION_ARGS = {}


def _analysis(script, excludes):
    return Analysis(
        [script],
        pathex=[str(Path(SPECPATH))],
        binaries=[],
        datas=DATAS,
        hiddenimports=HIDDEN,
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=excludes,
        win_no_prefer_redirects=False,
        win_private_assemblies=False,
        cipher=block_cipher,
        noarchive=False,
    )


# ---------------------------------------------------------------- GUI (windowed)
a = _analysis("svdstudio/app.py", excludes=[])

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
    icon=ICON,
    **VERSION_ARGS,
)

# ------------------------------------------------- CLI + MCP (console subsystem)
a_cli = _analysis("run_cli.py", excludes=["PySide6", "tkinter", "unittest", "pydoc_data"])

pyz_cli = PYZ(a_cli.pure, a_cli.zipped_data, cipher=block_cipher)

exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    a_cli.binaries,
    a_cli.zipfiles,
    a_cli.datas,
    [],
    name="svdstudio-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
    **VERSION_ARGS,
)
