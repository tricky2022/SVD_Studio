"""Application icon: generated chip glyph, no external assets needed."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap


def make_app_icon(size: int = 128) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    radius = size * 0.18
    painter.setBrush(QColor("#1769a6"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, size, size, radius, radius)
    # pins
    painter.setBrush(QColor("#0e4a77"))
    pin_w = size * 0.10
    pin_h = size * 0.045
    for i in range(4):
        y = size * (0.22 + i * 0.16)
        painter.drawRoundedRect(0, int(y), int(pin_w), int(pin_h), 2, 2)
        painter.drawRoundedRect(int(size - pin_w), int(y), int(pin_w), int(pin_h), 2, 2)
    # die
    painter.setBrush(QColor("#f2f7fc"))
    margin = size * 0.24
    painter.drawRoundedRect(int(margin), int(margin), int(size - 2 * margin),
                            int(size - 2 * margin), 8, 8)
    painter.setPen(QColor("#1769a6"))
    font = QFont("Arial", int(size * 0.22), QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "S")
    painter.end()
    return QIcon(pix)
