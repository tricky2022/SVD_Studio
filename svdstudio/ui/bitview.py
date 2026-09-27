"""Register bit layout: accurate canvas + readable, linkable field legend."""
from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from svdstudio.domain.model import SvdField, SvdRegister

PALETTE = [
    QColor("#3f78a8"), QColor("#c2762b"), QColor("#4f9660"), QColor("#b64d53"),
    QColor("#3e9996"), QColor("#8764a8"), QColor("#b66d7e"), QColor("#8a6d3b"),
]

ROW_BITS_TOP = 34
ROW_BITS_HEIGHT = 44
CANVAS_HEIGHT = 124


def bits_text(field: SvdField) -> str:
    """Single-bit fields show one number; multi-bit fields show msb:lsb."""
    return str(field.lsb) if field.bit_width == 1 else f"{field.msb}:{field.lsb}"


class _BitCanvas(QWidget):
    fieldClicked = Signal(object)
    createRequested = Signal(int)

    def __init__(self):
        super().__init__()
        self.reg: SvdRegister | None = None
        self._rects: list[tuple[QRect, SvdField]] = []
        self._hover: SvdField | None = None
        self.setMinimumWidth(420)
        self.setFixedHeight(CANVAS_HEIGHT)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_register(self, register: SvdRegister | None):
        self.reg = register
        self._hover = None
        self.update()

    def _bit_at(self, x: float) -> int | None:
        if self.reg is None or self.reg.size <= 0:
            return None
        cell = self.width() / self.reg.size
        if cell <= 0:
            return None
        bit = self.reg.size - 1 - int(x // cell)
        return bit if 0 <= bit < self.reg.size else None

    def mouseMoveEvent(self, event: QMouseEvent):
        bit = self._bit_at(event.position().x())
        hover = None
        if bit is not None and self.reg is not None:
            for field in self.reg.fields:
                if field.bit_offset <= bit < field.bit_offset + field.bit_width:
                    hover = field
                    break
        if hover is not self._hover:
            self._hover = hover
            self.update()
        if hover is not None:
            self.setToolTip(f"{hover.name}  •  {bits_text(hover)}  •  {hover.bit_width} bit"
                            + (f"\n{hover.description}" if hover.description else ""))
        else:
            self.setToolTip("")

    def mousePressEvent(self, event: QMouseEvent):
        bit = self._bit_at(event.position().x())
        if bit is None or self.reg is None:
            return
        for field in self.reg.fields:
            if field.bit_offset <= bit < field.bit_offset + field.bit_width:
                self.fieldClicked.emit(field)
                return

    def leaveEvent(self, _event):
        if self._hover is not None:
            self._hover = None
            self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        bit = self._bit_at(event.position().x())
        if bit is None or self.reg is None:
            return
        occupied = any(f.bit_offset <= bit < f.bit_offset + f.bit_width for f in self.reg.fields)
        if not occupied:
            self.createRequested.emit(bit)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), self.palette().base())
        if self.reg is None:
            painter.setPen(self.palette().mid().color())
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Select a register to inspect its bit layout")
            return

        size = self.reg.size
        cell = self.width() / size
        self._rects = []

        header_font = QFont(self.font())
        header_font.setBold(True)
        painter.setFont(header_font)
        painter.setPen(self.palette().text().color())
        painter.drawText(6, 0, self.width() - 12, 18, Qt.AlignmentFlag.AlignLeft,
                         f"{self.reg.name}   ·   {size}-bit   ·   reset {self.reg.reset_value:#0{2 + size // 4}x}")
        painter.setFont(self.font())

        # bit ruler: hide numbers that cannot fit to avoid unreadable clutter
        digit_font = QFont(self.font())
        digit_font.setPointSizeF(max(6.0, self.font().pointSizeF() - 2.5))
        painter.setFont(digit_font)
        for bit in range(size):
            x = int((size - 1 - bit) * cell)
            width = max(1, int(cell))
            label = str(bit)
            if int(cell) < 11 and bit % 8 != 0 and bit != size - 1:
                continue
            painter.setPen(self.palette().mid().color())
            painter.drawText(x, 18, width, 14, Qt.AlignmentFlag.AlignCenter, label)
        painter.setFont(self.font())

        used = [False] * size
        reset = self.reg.reset_value

        for index, field in enumerate(self.reg.fields):
            start = max(0, field.bit_offset)
            end = min(size, field.bit_offset + field.bit_width)
            if start >= end:
                continue
            color = PALETTE[index % len(PALETTE)]
            x0 = int((size - end) * cell)
            width = max(1, int((end - start) * cell))
            rect = QRect(x0, ROW_BITS_TOP, width, ROW_BITS_HEIGHT)
            self._rects.append((rect, field))
            for bit in range(start, end):
                x = int((size - 1 - bit) * cell)
                painter.fillRect(x, ROW_BITS_TOP, max(1, int(cell) + 1), ROW_BITS_HEIGHT, color)
                used[bit] = True

            # reset-value overlay on the lower band of each field
            for bit in range(start, end):
                if reset >> bit & 1:
                    x = int((size - 1 - bit) * cell)
                    painter.fillRect(x, ROW_BITS_TOP + ROW_BITS_HEIGHT - 5,
                                     max(1, int(cell) + 1), 5, QColor("#f2c14e"))

            if field is self._hover:
                painter.setPen(QPen(QColor("#ffffff"), 2))
            else:
                painter.setPen(QPen(QColor(0, 0, 0, 70), 1))
            painter.drawRect(rect)

            small = QFont(self.font())
            small.setPointSizeF(max(7.0, self.font().pointSizeF() - 1.5))
            painter.setFont(small)
            metrics = painter.fontMetrics()
            # always the field name; elide with … when narrow, never bits text
            if width < 22:
                label = ""
            else:
                label = metrics.elidedText(field.name, Qt.TextElideMode.ElideRight, width - 4)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
            painter.setFont(self.font())

        for bit, occupied in enumerate(used):
            if occupied:
                continue
            x = int((size - 1 - bit) * cell)
            painter.setPen(QPen(self.palette().mid().color(), 1, Qt.PenStyle.DotLine))
            painter.drawRect(QRect(x, ROW_BITS_TOP, max(1, int(cell)), ROW_BITS_HEIGHT))

        painter.setPen(self.palette().mid().color())
        hint = "hover for details  •  click a field to select  •  dotted = reserved  •  amber = reset bit set"
        painter.drawText(6, ROW_BITS_TOP + ROW_BITS_HEIGHT + 4, self.width() - 12, 18,
                         Qt.AlignmentFlag.AlignLeft, hint)


class BitView(QWidget):
    fieldClicked = Signal(object)
    createRequested = Signal(int)

    def __init__(self):
        super().__init__()
        self.reg: SvdRegister | None = None
        self.canvas = _BitCanvas()
        self.canvas.createRequested.connect(self.createRequested.emit)
        self.title = QLabel("Bit Layout")
        self.legend = QTableWidget(0, 6)
        self.legend.setHorizontalHeaderLabels(
            ["Field", "Bits", "Width", "Access", "Reset", "Description"]
        )
        self.legend.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.legend.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.legend.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.legend.setAlternatingRowColors(True)
        self.legend.verticalHeader().setVisible(False)
        header = self.legend.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        header.setMinimumSectionSize(56)
        self.legend.setColumnWidth(0, 170)
        self.legend.cellClicked.connect(self._legend_clicked)
        self.canvas.fieldClicked.connect(self._canvas_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(self.title)
        layout.addWidget(self.canvas)
        layout.addWidget(self.legend, 1)

    def set_register(self, register: SvdRegister | None):
        self.reg = register
        self.canvas.set_register(register)
        self.legend.setRowCount(0)
        if register is None:
            self.title.setText("Bit Layout")
            return
        self.title.setText(
            f"Bit Layout  ·  {register.name}  ·  {register.size}-bit  ·  {len(register.fields)} field(s)"
        )
        for field in register.fields:
            row = self.legend.rowCount()
            self.legend.insertRow(row)
            reset = "—" if field.reset_value is None else hex(field.reset_value)
            enum_note = ""
            if field.enumerated_values:
                count = sum(len(item.values) for item in field.enumerated_values)
                enum_note = f"  [{count} enum]"
            values = (
                field.name,
                bits_text(field),
                str(field.bit_width),
                field.access or "—",
                reset,
                (field.description or "") + enum_note,
            )
            for column, value in enumerate(values):
                self.legend.setItem(row, column, QTableWidgetItem(value))

    def _canvas_clicked(self, field: SvdField):
        self._select_field(field)

    def _legend_clicked(self, row, _column):
        if self.reg is not None and 0 <= row < len(self.reg.fields):
            self._select_field(self.reg.fields[row])

    def _select_field(self, field: SvdField):
        if self.reg is not None and field in self.reg.fields:
            self.legend.selectRow(self.reg.fields.index(field))
        self.fieldClicked.emit(field)
