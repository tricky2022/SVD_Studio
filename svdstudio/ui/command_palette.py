"""Keyboard-accessible search over the editor's existing commands."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QLineEdit, QListWidget, QVBoxLayout


class CommandPalette(QDialog):
    def __init__(self, commands, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Command Palette")
        self.resize(500, 420)
        self._commands = commands
        self._matches = []
        layout = QVBoxLayout(self)
        search = QLineEdit(self)
        self._list = QListWidget(self)
        layout.addWidget(search)
        layout.addWidget(self._list)
        search.textChanged.connect(self._filter)
        search.returnPressed.connect(self._run_selected)
        self._list.itemActivated.connect(self._run_selected)
        self._filter("")

    def _filter(self, query):
        self._list.clear()
        term = query.casefold().strip()
        self._matches = [command for command in self._commands
                         if term in f"{command[0]} {command[2]}".casefold()]
        for label, _, key in self._matches:
            self._list.addItem(f"{label}  ({key})" if key else label)
        self._list.setCurrentRow(0)

    def _run_selected(self):
        index = self._list.currentRow()
        if index >= 0:
            self.accept()
            self._matches[index][1]()
