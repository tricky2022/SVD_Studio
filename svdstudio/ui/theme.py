"""Theme manager: qdarkstyle dark + refined light, runtime switchable."""
from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from svdstudio.resources import resource_path

BASE_QSS = resource_path("resources", "styles", "base.qss")
DARK_QSS = resource_path("resources", "styles", "dark.qss")

_current = "light"

LIGHT_FONT = QFont("Microsoft YaHei UI", 9)
LIGHT_FONT.setStyleHint(QFont.StyleHint.SansSerif)


def apply_theme(app: QApplication, mode: str = "light") -> None:
    global _current
    _current = mode
    app.setStyle("Fusion")
    app.setFont(LIGHT_FONT if mode == "light" else QFont("Microsoft YaHei UI", 9))
    if mode == "dark":
        dark_extra = DARK_QSS.read_text(encoding="utf-8") if DARK_QSS.exists() else ""
        app.setStyleSheet(dark_extra)
    else:
        base = BASE_QSS.read_text(encoding="utf-8") if BASE_QSS.exists() else ""
        app.setStyleSheet(base)


def current_mode() -> str:
    return _current
