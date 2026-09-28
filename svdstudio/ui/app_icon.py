"""Application icon: generated chip glyph, no external assets needed.

``render_icon_image`` is the single painter; ``make_app_icon`` wraps it in a
multi-resolution ``QIcon`` for the window/taskbar, and
``tools/make_icon.py`` uses the same painter to produce the build-time
``.ico`` so the packaged exe and the running app never drift apart.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPixmap

SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def render_icon_image(size: int) -> QImage:
    """Draw the brand glyph at ``size`` px as a transparent RGBA image."""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    radius = max(2.0, size * 0.18)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#1769a6"))
    painter.drawRoundedRect(0, 0, size, size, radius, radius)

    # pins: skipped below 20px where they turn into mush
    if size >= 20:
        painter.setBrush(QColor("#0e4a77"))
        pin_w = size * 0.10
        pin_h = max(1.0, size * 0.045)
        for i in range(4):
            y = size * (0.22 + i * 0.16)
            painter.drawRoundedRect(0, int(y), int(pin_w), int(pin_h), 2, 2)
            painter.drawRoundedRect(int(size - pin_w), int(y), int(pin_w), int(pin_h), 2, 2)

    margin = size * 0.24
    painter.setBrush(QColor("#f2f7fc"))
    painter.drawRoundedRect(int(margin), int(margin), int(size - 2 * margin),
                            int(size - 2 * margin), max(1.5, size * 0.06), max(1.5, size * 0.06))

    # the "S" only reads at 32px and up; smaller sizes stay a clean chip
    if size >= 32:
        painter.setPen(QColor("#1769a6"))
        font = QFont("Arial")
        font.setPixelSize(int(size * 0.34))
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        text_rect = image.rect().adjusted(0, int(-size * 0.02), 0, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "S")
    painter.end()
    return image


def make_app_icon(size: int = 128) -> QIcon:
    icon = QIcon()
    for candidate in SIZES + ((size,) if size not in SIZES else ()):
        # PySide6 rejects the QImage overload of addPixmap, so convert first
        icon.addPixmap(QPixmap.fromImage(render_icon_image(candidate)))
    return icon
