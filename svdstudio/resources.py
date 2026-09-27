"""Runtime paths that work from source and from a PyInstaller bundle."""
from __future__ import annotations

import sys
from pathlib import Path


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def resource_path(*parts: str) -> Path:
    return project_root().joinpath(*parts)
