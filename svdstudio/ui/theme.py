"""Theme manager: design-token light/dark, runtime switchable.

All colors/spacings live in ``ui/palette.py`` as design tokens; the QSS is
generated from them. The ``resources/styles/*.qss`` files are derived outputs
kept for reference and tooling, not the source of truth.
"""
from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from svdstudio.resources import resource_path
from svdstudio.ui.palette import resolve as resolve_qss

_current = "light"

UI_FONT = QFont("Microsoft YaHei UI", 9)
UI_FONT.setStyleHint(QFont.StyleHint.SansSerif)


def apply_theme(app: QApplication, mode: str = "light") -> None:
    global _current
    _current = mode
    app.setStyle("Fusion")
    app.setFont(UI_FONT if mode == "light" else QFont("Microsoft YaHei UI", 9))
    app.setStyleSheet(resolve_qss(mode))


def current_mode() -> str:
    return _current


def _regenerate_qss_files() -> None:
    """Write the derived .qss outputs for anyone who opens them directly."""
    from svdstudio.ui.palette import build_qss
    for mode, name in (("light", "base.qss"), ("dark", "dark.qss")):
        path = resource_path("resources", "styles", name)
        path.write_text(build_qss(mode), encoding="utf-8")