"""Grouped property editor: section headers + labeled rows, fully adaptive."""
from __future__ import annotations

from dataclasses import fields, is_dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from svdstudio.ui.i18n import t

# group -> ordered attrs per domain type (group titles are i18n keys)
GROUPS: dict[str, list[tuple[str, list[str]]]] = {
    "SvdDevice": [
        ("g_identity", ["name", "vendor", "vendor_id", "series", "version", "description",
                        "license_text"]),
        ("g_addrwidth", ["address_unit_bits", "width", "size", "access", "protection",
                         "reset_value", "reset_mask"]),
    ],
    "SvdPeripheral": [
        ("g_identity", ["name", "display_name", "description", "group_name", "header_struct_name",
                        "prepend_to_name", "append_to_name"]),
        ("g_address", ["base_address", "derived_from"]),
    ],
    "SvdRegister": [
        ("g_identity", ["name", "display_name", "description", "alternate_register", "derived_from"]),
        ("g_address", ["address_offset", "size"]),
        ("g_access", ["access", "protection", "read_action", "modified_write_values",
                      "write_constraint"]),
        ("g_reset", ["reset_value", "reset_mask"]),
    ],
    "SvdField": [
        ("g_identity", ["name", "description", "derived_from"]),
        ("g_bitfield", ["bit_offset", "bit_width", "lsb", "msb"]),
        ("g_access", ["access", "read_action", "modified_write_values", "write_constraint"]),
        ("g_reset", ["reset_value"]),
    ],
    "default": [("g_default", [])],
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
    "g_address": "#4a7ab0",
    "g_access": "#3f9e6b",
    "g_reset": "#b7791f",
    "g_bitfield": "#8b6fc0",
    "g_addrwidth": "#4a7ab0",
}

# attribute -> i18n key; t() resolves the display text at render time
LABEL_KEYS = {
    "name": "l_name", "display_name": "l_display_name", "description": "l_description",
    "address_offset": "l_address_offset", "base_address": "l_base_address", "size": "l_size",
    "access": "l_access", "protection": "l_protection", "reset_value": "l_reset_value",
    "reset_mask": "l_reset_mask", "read_action": "l_read_action",
    "modified_write_values": "l_modified_write_values", "write_constraint": "l_write_constraint",
    "bit_offset": "l_bit_offset", "bit_width": "l_bit_width", "lsb": "l_lsb", "msb": "l_msb",
    "derived_from": "l_derived_from", "alternate_register": "l_alternate_register",
    "group_name": "l_group_name", "header_struct_name": "l_header_struct_name",
    "prepend_to_name": "l_prepend_to_name", "append_to_name": "l_append_to_name",
    "vendor": "l_vendor", "vendor_id": "l_vendor_id", "series": "l_series",
    "version": "l_version", "license_text": "l_license_text",
    "address_unit_bits": "l_address_unit_bits", "width": "l_width",
}


class PropertyEditor(QTableWidget):
    valueEdited = Signal(object, str, object)

    def __init__(self):
        super().__init__(0, 2)
        self.setHorizontalHeaderLabels([t("property"), t("value")])
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                             | QAbstractItemView.EditTrigger.EditKeyPressed
                             | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(True)
        header.setMinimumSectionSize(130)
        self.setColumnWidth(0, 175)
        self._obj = None
        self._loading = False
        self._row_attr: list[str | None] = []
        # closed-set attributes edit through a dropdown editor created on
        # demand (see ChoiceDelegate); no persistent cell widgets are kept.
        from svdstudio.ui.delegates import ChoiceDelegate
        self.setItemDelegateForColumn(1, ChoiceDelegate(CHOICES, self))
        self.cellChanged.connect(self._on_cell)

    def current_object(self):
        """The domain object currently shown (None when the panel is empty)."""
        return self._obj

    def refresh(self):
        """Re-render with current palette and language."""
        self.setHorizontalHeaderLabels([t("property"), t("value")])
        self.set_object(self._obj)

    def set_object(self, obj):
        self._loading = True
        self._obj = obj
        # No persistent cell widgets are kept (dropdowns are delegate editors
        # created on demand), so clearing rows frees everything. Do NOT go
        # back to per-row QComboBox cell widgets: detached cell widgets are
        # never deleted by Qt and leaked ~1MB per register switch.
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

    def _add_section(self, title_key: str):
        row = self.rowCount()
        self.insertRow(row)
        item = QTableWidgetItem(f"▾  {t(title_key)}")
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
        name_item = QTableWidgetItem(t(LABEL_KEYS.get(attr, attr)))
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
        value_item = QTableWidgetItem(text)
        value_item.setToolTip(f"{attr}: {text}" + (" (SVD 标准取值)" if choices else ""))
        value_item.setData(Qt.ItemDataRole.UserRole, attr)
        self.setItem(row, 1, value_item)
        self._row_attr.append(attr)

    def _on_cell(self, row, column):
        # Single commit path for typed text and delegate dropdowns alike.
        if self._loading or column != 1 or self._obj is None:
            return
        if row >= len(self._row_attr) or self._row_attr[row] is None:
            return
        attr = self._row_attr[row]
        cell = self.item(row, 1)
        text = cell.text().strip() if cell is not None else ""
        old = getattr(self._obj, attr)
        if isinstance(old, bool):
            shown = "true" if old else "false"
        elif isinstance(old, int) and attr in ("reset_value", "reset_mask", "base_address",
                                               "address_offset"):
            shown = f"{old:#x}"
        else:
            shown = str(old)
        if text == shown:
            return  # unchanged: never push a no-op undo step
        try:
            if isinstance(old, bool):
                new = text.lower() in ("1", "true", "yes", "真", "是")
            elif isinstance(old, int):
                new = int(text, 0)
            else:
                new = text
        except (TypeError, ValueError):
            cell.setText(shown)  # invalid input: restore instead of corrupting
            return
        self.valueEdited.emit(self._obj, attr, new)
