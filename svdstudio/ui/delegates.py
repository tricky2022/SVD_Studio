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


class ChoiceDelegate(QStyledItemDelegate):
    """Dropdown editor for property rows whose attribute has a closed set.

    Replaces per-rebuild QComboBox cell widgets (which leaked: Qt never
    deletes detached cell widgets, ~85 per register switch). Editors now
    exist only while a cell is being edited and are destroyed by the view.
    The attribute name travels in the item's UserRole data.
    """

    def __init__(self, choices: dict, parent=None):
        super().__init__(parent)
        self._choices = choices

    def createEditor(self, parent, option, index):
        from PySide6.QtCore import Qt
        attr = index.data(Qt.ItemDataRole.UserRole)
        values = self._choices.get(attr) if isinstance(attr, str) else None
        if not values:
            return super().createEditor(parent, option, index)
        combo = QComboBox(parent)
        combo.addItems(list(values))
        return combo

    def setEditorData(self, editor, index):
        from PySide6.QtWidgets import QComboBox
        if not isinstance(editor, QComboBox):
            super().setEditorData(editor, index)
            return
        current = index.data() or ""
        pos = editor.findText(current)
        editor.setCurrentIndex(max(pos, 0))

    def setModelData(self, editor, model, index):
        from PySide6.QtWidgets import QComboBox
        if not isinstance(editor, QComboBox):
            super().setModelData(editor, model, index)
            return
        model.setData(index, editor.currentText())
