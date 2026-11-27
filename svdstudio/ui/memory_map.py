"""Compact address overview for the selected memory-mapped peripheral."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget


class MemoryMapView(QWidget):
    registerClicked = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._peripheral = None
        self._bounds = (0, 1)
        self._ranges = []

    def set_device(self, device, peripheral):
        self._peripheral = peripheral
        unit_bits = max(1, device.address_unit_bits)
        self._ranges = []
        for register in peripheral.registers:
            width_bits = max(1, register.size or device.size)
            start = register.address_offset
            end = start + (width_bits + unit_bits - 1) // unit_bits
            self._ranges.append((start, end, register))
        starts = [start for start, _, _ in self._ranges]
        ends = [end for _, end, _ in self._ranges]
        for block in peripheral.address_blocks:
            starts.append(block.offset)
            ends.append(block.offset + block.size)
        low = min([0, *starts])
        self._bounds = (low, max([low + 1, *ends]))
        self.update()

    def clear(self):
        self._peripheral = None
        self._ranges = []
        self.update()

    def _bar(self):
        return QRectF(10, 6, max(1, self.width() - 20), max(10, self.height() - 29))

    def _register_rect(self, start, end, bar):
        low, high = self._bounds
        scale = bar.width() / (high - low)
        return QRectF(bar.left() + (start - low) * scale, bar.top(),
                      max(2, (end - start) * scale), bar.height())

    def paintEvent(self, event):
        if self._peripheral is None:
            return
        painter = QPainter(self)
        bar = self._bar()
        painter.fillRect(bar, self.palette().mid())
        for start, end, _ in self._ranges:
            painter.fillRect(self._register_rect(start, end, bar), QColor("#4a7ab0"))
        low, high = self._bounds
        base = self._peripheral.base_address
        painter.setPen(self.palette().windowText().color())
        painter.drawText(QRectF(bar.left(), bar.bottom(), bar.width(), 20),
                         Qt.AlignmentFlag.AlignLeft, f"{base + low:#010x}")
        painter.drawText(QRectF(bar.left(), bar.bottom(), bar.width(), 20),
                         Qt.AlignmentFlag.AlignRight, f"{base + high - 1:#010x}")

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        bar = self._bar()
        for start, end, register in self._ranges:
            if self._register_rect(start, end, bar).contains(event.position()):
                self.registerClicked.emit(register)
                return
