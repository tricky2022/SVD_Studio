"""Grouped property editor: section headers + labeled rows, fully adaptive."""
from __future__ import annotations

from dataclasses import fields, is_dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from svdstudio.domain.model import CPU_PROPERTIES, CpuInfo
from svdstudio.ui.i18n import t

# group -> ordered attrs per domain type (group titles are i18n keys)
GROUPS: dict[str, list[tuple[str, list[str]]]] = {
    "SvdDevice": [
        ("g_identity", ["name", "vendor", "vendor_id", "series", "version", "description",
                        "license_text"]),
        ("g_addrwidth", ["address_unit_bits", "width", "size", "access", "protection",
                         "reset_value", "reset_mask"]),
    ],
    "CpuInfo": [
        ("g_identity", ["name", "revision", "endian"]),
        ("g_cpu_features", ["mpu_present", "fpu_present", "fpu_dp", "dsp_present",
                            "icache_present", "dcache_present", "itcm_present", "dtcm_present",
                            "vtor_present"]),
        ("g_cpu_interrupts", ["nvic_prio_bits", "vendor_systick_config", "device_num_interrupts",
                              "sau_num_regions"]),
    ],
    "CoreRegisterGroup": [("g_identity", ["name", "description"])],
    "CoreRegister": [
        ("g_identity", ["name", "description"]),
        ("g_address", ["size"]),
        ("g_access", ["access"]),
        ("g_reset", ["reset_value", "reset_mask"]),
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
    "core_field_access": ["", "RW", "R", "W", "N"],
}

CPU_FLAGS = {"mpu_present", "fpu_present", "vendor_systick_config"}
OPTIONAL_CPU_FLAGS = {"fpu_dp", "dsp_present", "icache_present", "dcache_present",
                      "itcm_present", "dtcm_present", "vtor_present"}
CPU_TAGS = {attr: tag for tag, attr, _ in CPU_PROPERTIES}
CPU_INTS = {"nvic_prio_bits", "device_num_interrupts", "sau_num_regions"}
OPTIONAL_INTS = {"size", "reset_value", "reset_mask"}
HEX_INTS = {"reset_value", "reset_mask", "base_address", "address_offset"}
CHOICES.update({name: ["", "true", "false"] for name in CPU_FLAGS | OPTIONAL_CPU_FLAGS})


def _display(attr, value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and attr in HEX_INTS:
        return f"{value:#x}"
    return str(value)


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
    "revision": "l_cpu_revision", "endian": "l_cpu_endian",
    "mpu_present": "l_cpu_mpu", "fpu_present": "l_cpu_fpu", "fpu_dp": "l_cpu_fpu_dp",
    "dsp_present": "l_cpu_dsp", "icache_present": "l_cpu_icache",
    "dcache_present": "l_cpu_dcache", "itcm_present": "l_cpu_itcm", "dtcm_present": "l_cpu_dtcm",
    "vtor_present": "l_cpu_vtor", "nvic_prio_bits": "l_cpu_nvic_prio_bits",
    "vendor_systick_config": "l_cpu_systick", "device_num_interrupts": "l_cpu_interrupts",
    "sau_num_regions": "l_cpu_sau_regions",
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
        self._core_field = False
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

    def _value(self, attr):
        value = getattr(self._obj, attr)
        if (isinstance(self._obj, CpuInfo) and attr in CPU_FLAGS | {"nvic_prio_bits"}
                and CPU_TAGS[attr] not in self._obj.meta.present
                and value == getattr(CpuInfo(), attr)):
            return None
        return value

    def refresh(self):
        """Re-render with current palette and language."""
        self.setHorizontalHeaderLabels([t("property"), t("value")])
        self.set_object(self._obj, core_field=self._core_field)

    def set_object(self, obj, *, core_field=False):
        self._loading = True
        self._obj = obj
        self._core_field = core_field
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
                    self._add_row(attr, self._value(attr), group_name)
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
        text = _display(attr, value)
        self.setItem(row, 0, name_item)
        choice_key = "core_field_access" if self._core_field and attr == "access" else attr
        value_item = QTableWidgetItem(text)
        value_item.setToolTip(f"{attr}: {text}")
        value_item.setData(Qt.ItemDataRole.UserRole, choice_key)
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
        old = self._value(attr)
        shown = _display(attr, old)
        if text == shown:
            return  # unchanged: never push a no-op undo step
        try:
            if isinstance(old, bool) or attr in CPU_FLAGS | OPTIONAL_CPU_FLAGS:
                new = {"true": True, "false": False}[text] if text else None
            elif isinstance(old, int) or attr in OPTIONAL_INTS | CPU_INTS:
                new = int(text, 0) if text else None
            else:
                new = text
            if (new is None and attr not in CPU_FLAGS | OPTIONAL_CPU_FLAGS | CPU_INTS
                    and not self._is_optional_int(attr)):
                raise ValueError
            if type(new) is int and (new < 0 or (attr == "size" and new < 1)):
                raise ValueError
        except (KeyError, ValueError):
            self._loading = True
            cell.setText(shown)
            self._loading = False
            return
        self.valueEdited.emit(self._obj, attr, new)

    def _is_optional_int(self, attr):
        if attr not in OPTIONAL_INTS:
            return False
        return type(self._obj).__name__ not in {"SvdDevice"} and (
            attr != "size" or type(self._obj).__name__ != "CoreRegister"
        )
