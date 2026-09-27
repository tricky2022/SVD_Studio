"""Item delegates for in-place table editing with SVD-standard value sets."""
from __future__ import annotations

import typing

from PySide6.QtWidgets import QComboBox, QStyledItemDelegate


class AccessDelegate(QStyledItemDelegate):
    """Dropdown for the CMSIS-SVD access field; empty renders as an em dash."""

    VALUES: typing.ClassVar[list] = ["", "read-only", "write-only", "read-write",
                                        "writeOnce", "read-clear"]
    EMPTY_LABEL = "—"

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.addItems([self.EMPTY_LABEL if v == "" else v for v in self.VALUES])
        return combo

    def setEditorData(self, editor, index):
        current = index.data() or ""
        label = self.EMPTY_LABEL if current == "" else current
        pos = editor.findText(label)
        editor.setCurrentIndex(max(pos, 0))

    def setModelData(self, editor, model, index):
        text = editor.currentText()
        model.setData(index, "" if text == self.EMPTY_LABEL else text)
