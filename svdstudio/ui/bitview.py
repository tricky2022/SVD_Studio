"""Register bit layout: accurate canvas + readable, linkable field legend."""
from __future__ import annotations

import typing

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
from svdstudio.ui.i18n import t

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

    def __init__(self, menu_signal=None):
        super().__init__()
        self.reg: SvdRegister | None = None
        self._menu_signal = menu_signal
        self._rects: list[tuple[QRect, SvdField]] = []
        self._hover: SvdField | None = None
        self._selected: SvdField | None = None
        self.setMinimumWidth(420)
        self.setFixedHeight(CANVAS_HEIGHT)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

    def _on_context_menu(self, pos):
        if self._menu_signal is None:
            return
        bit = self._bit_at(pos.x())
        self._menu_signal.emit(bit if bit is not None else -1, self.mapToGlobal(pos))

    def set_register(self, register: SvdRegister | None):
        self.reg = register
        self._hover = None
        self._selected = None
        self.update()

    def set_selected(self, field: SvdField | None):
        """Highlight a field on the canvas (driven by table selection)."""
        if field is self._selected:
            return
        self._selected = field
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

            if field is self._selected:
                painter.setPen(QPen(QColor(99, 117, 216, 160), 4))
                painter.drawRect(rect.adjusted(-2, -2, 2, 2))
                painter.setPen(QPen(QColor("#ffffff"), 2))
            elif field is self._hover:
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
    fieldEdited = Signal(object, str, object)
    fieldMoved = Signal(object, int, int)  # field, new lsb, new width
    createRequested = Signal(int)
    canvasMenuRequested = Signal(int, object)  # bit (-1 when none), global pos
    legendMenuRequested = Signal(object)  # global pos; rows resolved by the window

    # legend columns the user may edit in place
    EDITABLE_COLUMNS: typing.ClassVar[dict] = {
        0: "name", 1: "bits", 2: "width", 3: "access", 5: "description",
    }

    def __init__(self):
        super().__init__()
        self.reg: SvdRegister | None = None
        self._legend_loading = False
        self.canvas = _BitCanvas(menu_signal=self.canvasMenuRequested)
        self.canvas.createRequested.connect(self.createRequested.emit)
        self.title = QLabel(t("bit_layout_title"))
        self.legend = QTableWidget(0, 6)
        self.legend.setHorizontalHeaderLabels(self._headers())
        self.legend.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.legend.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.legend.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                    | QAbstractItemView.EditTrigger.EditKeyPressed)
        from svdstudio.ui.delegates import AccessDelegate
        self.legend.setItemDelegateForColumn(3, AccessDelegate(self.legend))
        self.legend.itemChanged.connect(self._on_legend_changed)
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
        self.legend.itemSelectionChanged.connect(self._legend_selection_changed)
        self.legend.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.legend.customContextMenuRequested.connect(self._on_legend_menu)
        self.canvas.fieldClicked.connect(self._canvas_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(self.title)
        layout.addWidget(self.canvas)
        layout.addWidget(self.legend, 1)

    @staticmethod
    def _headers() -> list[str]:
        return [t("f_field"), t("f_bits"), t("f_width"), t("f_access"), t("f_reset"),
                t("f_description")]

    def retranslate(self):
        self.legend.setHorizontalHeaderLabels(self._headers())
        self.set_register(self.reg)

    def set_register(self, register: SvdRegister | None):
        changed = register is not self.reg
        self.reg = register
        self.canvas.set_register(register)
        if changed and register is not None:
            self._fade_canvas()
        # the loading guard must cover the whole rebuild: inserting cells emits
        # itemChanged, and an unguarded emit would push undo commands (and a
        # full view rebuild) for every cell just written
        self._legend_loading = True
        self.legend.blockSignals(True)
        try:
            self._fill_legend(register)
        finally:
            self.legend.blockSignals(False)
            self._legend_loading = False

    def _fill_legend(self, register: SvdRegister | None):
        self.legend.setRowCount(0)
        if register is None:
            self.title.setText(t("bit_layout_title"))
            return
        self.title.setText(
            f"{t('bit_layout_title')}  ·  {register.name}  ·  {register.size}-bit  ·  "
            f"{len(register.fields)} {t('f_field')}(s)"
        )
        # LSB-first: bit 0 at the top, matching how engineers read the map
        for field in sorted(register.fields, key=lambda f: (f.bit_offset, f.bit_width)):
            row = self.legend.rowCount()
            self.legend.insertRow(row)
            for column, value in enumerate(self._row_values(field)):
                cell = QTableWidgetItem(value)
                if column in self.EDITABLE_COLUMNS:
                    cell.setToolTip(t("legend_tip_edit"))
                else:
                    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                cell.setData(Qt.ItemDataRole.UserRole, field)
                self.legend.setItem(row, column, cell)

    @staticmethod
    def _row_values(field: SvdField) -> tuple:
        """Canonical display text; also the reference for change detection."""
        enum_note = ""
        if field.enumerated_values:
            count = sum(len(item.values) for item in field.enumerated_values)
            enum_note = f"  [{count} enum]"
        return (
            field.name,
            bits_text(field),
            str(field.bit_width),
            field.access or "—",
            "—" if field.reset_value is None else hex(field.reset_value),
            (field.description or "") + enum_note,
        )

    @staticmethod
    def parse_bits(text: str) -> tuple[int, int] | None:
        """Parse 'msb:lsb' or a single bit into (lsb, width); None when invalid."""
        text = text.strip().replace(" ", "")
        try:
            if ":" in text:
                msb_s, lsb_s = text.split(":", 1)
                msb, lsb = int(msb_s, 0), int(lsb_s, 0)
                if msb < lsb or lsb < 0:
                    return None
                return lsb, msb - lsb + 1
            bit = int(text, 0)
            return (bit, 1) if bit >= 0 else None
        except ValueError:
            return None

    def _on_legend_changed(self, item: QTableWidgetItem):
        if self._legend_loading:
            return
        field = item.data(Qt.ItemDataRole.UserRole)
        attr = self.EDITABLE_COLUMNS.get(item.column())
        if field is None or attr is None or self.reg is None or field not in self.reg.fields:
            return
        text = item.text().strip()
        # canonical display comparison first: rebuilding the table must never
        # look like an edit (that is what wrote "—" into access and triggered
        # an undo push + full refresh per cell)
        shown = self._row_values(field)[item.column()].strip()
        if text == shown:
            return
        if attr == "name":
            if not text or any(f is not field and f.name == text for f in self.reg.fields):
                self.set_register(self.reg)  # revert invalid rename
                return
            self.fieldEdited.emit(field, attr, text)
            return
        if attr in ("bits", "width"):
            parsed = self.parse_bits(text) if attr == "bits" else None
            if attr == "width":
                try:
                    width = int(text, 0)
                    parsed = (field.lsb, width) if width >= 1 else None
                except ValueError:
                    parsed = None
            if parsed is None:
                self.set_register(self.reg)  # revert invalid geometry text
                return
            if parsed == (field.lsb, field.bit_width):
                return
            self.fieldMoved.emit(field, parsed[0], parsed[1])
            return
        if attr == "access":
            value = "" if text in ("—", "-") else text
            if value == (field.access or ""):
                self.set_register(self.reg)  # normalize the "—" display
                return
            self.fieldEdited.emit(field, attr, value)
            return
        self.fieldEdited.emit(field, attr, text)

    def _fade_canvas(self):
        """Subtle 180ms fade so register switches feel alive without distraction."""
        from PySide6.QtCore import QEasingCurve, QPropertyAnimation
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        effect = self.canvas.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(self.canvas)
            self.canvas.setGraphicsEffect(effect)
        self._fade_anim = QPropertyAnimation(effect, b"opacity", self)
        self._fade_anim.setDuration(180)
        self._fade_anim.setStartValue(0.35)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.start()

    def _on_legend_menu(self, pos):
        self.legendMenuRequested.emit(self.legend.mapToGlobal(pos))

    def selected_fields(self) -> list:
        """Field objects behind the selected legend rows (LSB-first display)."""
        fields = self.reg.fields if self.reg is not None else []
        picked, seen = [], set()
        for row in sorted({i.row() for i in self.legend.selectedIndexes()}):
            item = self.legend.item(row, 0)
            field = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            if field is not None and field in fields and id(field) not in seen:
                seen.add(id(field))
                picked.append(field)
        return picked

    def _canvas_clicked(self, field: SvdField):
        self._select_field(field)

    def _legend_selection_changed(self):
        picked = self.selected_fields()
        if not picked:
            return
        self.canvas.set_selected(picked[0])
        self.fieldClicked.emit(picked[0])

    def _select_field(self, field: SvdField):
        if self.reg is not None and field in self.reg.fields:
            self.legend.blockSignals(True)
            try:
                for row in range(self.legend.rowCount()):
                    item = self.legend.item(row, 0)
                    if item is not None and item.data(Qt.ItemDataRole.UserRole) is field:
                        self.legend.selectRow(row)
                        break
            finally:
                self.legend.blockSignals(False)
            self.canvas.set_selected(field)
        self.fieldClicked.emit(field)
