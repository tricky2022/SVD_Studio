"""Apply the bundled light or dark Qt stylesheet."""
from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from svdstudio.resources import resource_path

_current = "light"

UI_FONT = QFont("Microsoft YaHei UI", 9)
UI_FONT.setStyleHint(QFont.StyleHint.SansSerif)


def apply_theme(app: QApplication, mode: str = "light") -> None:
    global _current
    _current = mode
    app.setStyle("Fusion")
    app.setFont(UI_FONT if mode == "light" else QFont("Microsoft YaHei UI", 9))
    stylesheet = resource_path("resources", "styles", f"{mode}.qss")
    app.setStyleSheet(stylesheet.read_text(encoding="utf-8"))


def current_mode() -> str:
    return _current
