"""Grouped property editor: section headers + labeled rows, fully adaptive."""
from __future__ import annotations

from dataclasses import fields, is_dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

# group -> ordered attrs per domain type
GROUPS: dict[str, list[tuple[str, list[str]]]] = {
    "SvdDevice": [
        ("标识", ["name", "vendor", "vendor_id", "series", "version", "description", "license_text"]),
        ("地址与宽度", ["address_unit_bits", "width", "size", "access", "protection",
                        "reset_value", "reset_mask"]),
    ],
    "SvdPeripheral": [
        ("标识", ["name", "display_name", "description", "group_name", "header_struct_name",
                  "prepend_to_name", "append_to_name"]),
        ("地址", ["base_address", "derived_from"]),
    ],
    "SvdRegister": [
        ("标识", ["name", "display_name", "description", "alternate_register", "derived_from"]),
        ("地址", ["address_offset", "size"]),
        ("访问", ["access", "protection", "read_action", "modified_write_values", "write_constraint"]),
        ("复位", ["reset_value", "reset_mask"]),
    ],
    "SvdField": [
        ("标识", ["name", "description", "derived_from"]),
        ("位域", ["bit_offset", "bit_width", "lsb", "msb"]),
        ("访问", ["access", "read_action", "modified_write_values", "write_constraint"]),
        ("复位", ["reset_value"]),
    ],
    "default": [("属性", [])],
}

# SVD-standard closed value sets -> combo boxes instead of free text
CHOICES: dict[str, list[str]] = {
    "access": ["", "read-only", "write-only", "read-write", "writeOnce", "read-clear"],
    "protection": ["", "secure", "non-secure", "privileged"],
    "read_action": ["", "clear", "set", "modify", "modifyExternal"],
    "modified_write_values": ["", "oneToClear", "oneToSet", "oneToToggle", "zeroToClear",
                              "zeroToSet", "zeroToToggle", "clear", "set", "modify"],
    "write_constraint": ["", "writeAsRead", "useEnumeratedValues", "range"],
    "endian": ["", "little", "big", "selectable", "other"],
}

# category accent color per property group (module-level: immutable usage)
CATEGORY_COLORS = {
    "地址": "#4a7ab0",
    "访问": "#3f9e6b",
    "复位": "#b7791f",
    "位域": "#8b6fc0",
    "地址与宽度": "#4a7ab0",
}

LABELS = {
    "name": "名称", "display_name": "显示名", "description": "描述",
    "address_offset": "偏移", "base_address": "基地址", "size": "位宽",
    "access": "访问", "protection": "保护", "reset_value": "复位值", "reset_mask": "复位掩码",
    "read_action": "读动作", "modified_write_values": "写语义", "write_constraint": "写约束",
    "bit_offset": "起始位", "bit_width": "位宽", "lsb": "LSB", "msb": "MSB",
    "derived_from": "继承自", "alternate_register": "别名寄存器",
    "group_name": "分组", "header_struct_name": "结构体名",
    "prepend_to_name": "名称前缀", "append_to_name": "名称后缀",
    "vendor": "厂商", "vendor_id": "厂商ID", "series": "系列", "version": "版本",
    "license_text": "许可", "address_unit_bits": "地址单元", "width": "宽度",
}


class PropertyEditor(QTableWidget):
    valueEdited = Signal(object, str, object)

    def __init__(self):
        super().__init__(0, 2)
        self.setHorizontalHeaderLabels(["属性", "值"])
        self.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(True)
        header.setMinimumSectionSize(110)
        self.setColumnWidth(0, 150)
        self._obj = None
        self._loading = False
        self._row_attr: list[str | None] = []
        self.cellChanged.connect(self._on_cell)

    def refresh(self):
        """Re-render with current palette (call after theme switch)."""
        self.set_object(self._obj)

    def set_object(self, obj):
        self._loading = True
        self._obj = obj
        for row in range(self.rowCount()):
            self.removeCellWidget(row, 1)
        self.setRowCount(0)
        self._row_attr = []
        if obj is not None and is_dataclass(obj):
            type_name = type(obj).__name__
            declared = {f.name for f in fields(obj)}
            for group_name, attrs in GROUPS.get(type_name, GROUPS["default"]):
                shown = [a for a in attrs if a in declared]
                if type_name in GROUPS and not shown:
                    continue
                if type_name not in GROUPS:
                    shown = [f.name for f in fields(obj) if f.name not in
                             ("meta", "fields", "registers", "clusters", "peripherals",
                              "enumerated_values", "values", "dim", "address_blocks", "cpu")]
                if not shown:
                    continue
                self._add_section(group_name)
                for attr in shown:
                    self._add_row(attr, getattr(obj, attr), group_name)
        self.resizeRowsToContents()
        self._loading = False

    def _add_section(self, title: str):
        row = self.rowCount()
        self.insertRow(row)
        item = QTableWidgetItem(f"▾  {title}")
        font = QFont(self.font())
        font.setBold(True)
        item.setFont(font)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        # explicit per-theme section colors (palette Button role is unreliable
        # across Fusion/QSS, which caused black headers in light mode)
        from svdstudio.ui.theme import current_mode
        dark = current_mode() == "dark"
        bg = QColor("#33405a") if dark else QColor("#dfe8f2")
        fg = QColor("#d7e5f5") if dark else QColor("#29435c")
        item.setBackground(bg)
        item.setForeground(fg)
        self.setItem(row, 0, item)
        span = QTableWidgetItem("")
        span.setFlags(span.flags() & ~Qt.ItemFlag.ItemIsEditable)
        span.setBackground(bg)
        span.setForeground(fg)
        self.setItem(row, 1, span)
        self._row_attr.append(None)

    def _add_row(self, attr: str, value, group: str = ""):
        from svdstudio.domain.model import NodeMeta
        if isinstance(value, NodeMeta):
            return
        row = self.rowCount()
        self.insertRow(row)
        name_item = QTableWidgetItem(LABELS.get(attr, attr))
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        name_item.setToolTip(attr)
        accent = CATEGORY_COLORS.get(group)
        if accent is not None:
            name_item.setForeground(QColor(accent))
        if isinstance(value, bool):
            text = "true" if value else "false"
        elif isinstance(value, int):
            text = f"{value:#x}" if attr in ("reset_value", "reset_mask", "base_address",
                                             "address_offset") else str(value)
        else:
            text = str(value)
        self.setItem(row, 0, name_item)
        choices = CHOICES.get(attr)
        if choices is not None and not isinstance(value, bool):
            from PySide6.QtWidgets import QComboBox
            combo = QComboBox()
            combo.addItems(choices)
            combo.setCurrentText(text if text in choices else "")
            combo.setToolTip(f"{attr}: SVD 标准取值")
            combo.currentTextChanged.connect(
                lambda new_text, a=attr: self._on_choice(a, new_text))
            self.setCellWidget(row, 1, combo)
            shadow = QTableWidgetItem(text)
            shadow.setFlags(shadow.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.setItem(row, 1, shadow)
        else:
            value_item = QTableWidgetItem(text)
            value_item.setToolTip(f"{attr}: {text}")
            self.setItem(row, 1, value_item)
        self._row_attr.append(attr)

    def _on_choice(self, attr: str, text: str):
        if self._loading or self._obj is None:
            return
        if getattr(self._obj, attr, "") == text:
            return
        self.valueEdited.emit(self._obj, attr, text)

    def _on_cell(self, row, column):
        if self._loading or column != 1 or self._obj is None:
            return
        if self.cellWidget(row, 1) is not None:
            return  # combo-driven rows commit via _on_choice
        if row >= len(self._row_attr) or self._row_attr[row] is None:
            return
        attr = self._row_attr[row]
        text = self.item(row, 1).text().strip()
        old = getattr(self._obj, attr)
        try:
            if isinstance(old, bool):
                new = text.lower() in ("1", "true", "yes", "真", "是")
            elif isinstance(old, int):
                new = int(text, 0)
            elif isinstance(old, str):
                new = text
            else:
                new = text
        except (TypeError, ValueError):
            new = text
        self.valueEdited.emit(self._obj, attr, new)
