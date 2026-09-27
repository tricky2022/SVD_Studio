"""Enumerated-value editor dialog for a field."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class EnumEditorDialog(QDialog):
    def __init__(self, field, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Enumerated Values — {field.name}")
        self.resize(560, 380)
        self.field = field
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Name", "Value", "Description"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        for group in field.enumerated_values:
            for v in group.values:
                r = self.table.rowCount()
                self.table.insertRow(r)
                self.table.setItem(r, 0, QTableWidgetItem(v.name))
                self.table.setItem(r, 1, QTableWidgetItem(str(v.value)))
                self.table.setItem(r, 2, QTableWidgetItem(v.description))
        bar = QHBoxLayout()
        add_btn = QPushButton("Add")
        del_btn = QPushButton("Delete")
        add_btn.clicked.connect(lambda: self.table.insertRow(self.table.rowCount()))
        del_btn.clicked.connect(lambda: self.table.removeRow(self.table.currentRow()))
        bar.addWidget(add_btn)
        bar.addWidget(del_btn)
        bar.addStretch(1)
        layout.addLayout(bar)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result_values(self) -> list[tuple[str, int, str]]:
        out = []
        for r in range(self.table.rowCount()):
            name_item = self.table.item(r, 0)
            val_item = self.table.item(r, 1)
            desc_item = self.table.item(r, 2)
            name = name_item.text().strip() if name_item else ""
            if not name:
                continue
            try:
                val = int((val_item.text().strip() if val_item else "0"), 0)
            except ValueError:
                QMessageBox.warning(self, "Invalid value", f"Row {r + 1}: value must be numeric.")
                raise ValueError("invalid enum value")
            desc = desc_item.text() if desc_item else ""
            width = self.field.bit_width
            if val >= (1 << width):
                QMessageBox.warning(self, "Out of range",
                                    f"{name}={val:#x} exceeds {width}-bit field.")
                raise ValueError("enum out of range")
            out.append((name, val, desc))
        return out
