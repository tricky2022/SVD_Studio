"""Tasteful motion helpers: short fades, no bouncing widgets."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

_ANIMATIONS: list[QPropertyAnimation] = []


def fade_in(widget: QWidget, duration_ms: int = 160):
    """Fade a panel from transparent to opaque. Safe to call offscreen."""
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration_ms)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    _ANIMATIONS.append(animation)
    animation.finished.connect(lambda: _ANIMATIONS.remove(animation)
                               if animation in _ANIMATIONS else None)
    animation.start()
