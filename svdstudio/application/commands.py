"""Undoable application commands for domain edits."""
from __future__ import annotations

from copy import deepcopy

from PySide6.QtGui import QUndoCommand


class SetAttrCommand(QUndoCommand):
    def __init__(self, obj, attr, new, refresh):
        super().__init__(f"Edit {attr}")
        self._object = obj
        self._attribute = attr
        self._new_value = new
        self._refresh = refresh
        self._old_value = getattr(obj, attr)

    def redo(self):
        setattr(self._object, self._attribute, self._new_value)
        self._refresh()

    def undo(self):
        setattr(self._object, self._attribute, self._old_value)
        self._refresh()


class InsertCommand(QUndoCommand):
    def __init__(self, items, item, index, label, refresh):
        super().__init__(label)
        self._items = items
        self._item = item
        self._index = index
        self._refresh = refresh

    def redo(self):
        self._items.insert(self._index, self._item)
        self._refresh()

    def undo(self):
        self._items.pop(self._index)
        self._refresh()


class DeleteCommand(QUndoCommand):
    def __init__(self, items, item, label, refresh):
        super().__init__(label)
        self._items = items
        self._item = item
        self._index = -1
        self._refresh = refresh

    def redo(self):
        self._index = self._items.index(self._item)
        self._items.pop(self._index)
        self._refresh()

    def undo(self):
        self._items.insert(self._index, self._item)
        self._refresh()


def clone_item(item):
    """Create a detached clone for duplicate operations."""
    clone = deepcopy(item)
    if hasattr(clone, "name"):
        clone.name = f"{clone.name}_COPY"
    return clone


def append_command(items, item, label, refresh):
    return InsertCommand(items, item, len(items), label, refresh)


class BatchAttrCommand(QUndoCommand):
    """Apply one attribute change to many objects as a single undo step."""

    def __init__(self, objects, attr, new, refresh, label=""):
        super().__init__(label or f"Batch edit {attr} x{len(objects)}")
        self._objects = list(objects)
        self._attr = attr
        self._new = new
        self._refresh = refresh
        self._olds = [getattr(o, attr) for o in self._objects]

    def redo(self):
        for o in self._objects:
            setattr(o, self._attr, self._new)
        self._refresh()

    def undo(self):
        for o, old in zip(self._objects, self._olds):
            setattr(o, self._attr, old)
        self._refresh()


class MoveCommand(QUndoCommand):
    """Move an item within its list (up/down) as one undo step."""

    def __init__(self, items, item, direction: int, refresh):
        super().__init__(f"Move {getattr(item, 'name', '')}")
        self._items = items
        self._item = item
        self._dir = -1 if direction < 0 else 1
        self._refresh = refresh
        self._from = -1
        self._to = -1

    def redo(self):
        idx = self._items.index(self._item)
        other = idx + self._dir
        if 0 <= other < len(self._items):
            self._from, self._to = idx, other
            self._items[idx], self._items[other] = self._items[other], self._items[idx]
        self._refresh()

    def undo(self):
        if self._from >= 0:
            self._items[self._to], self._items[self._from] = \
                self._items[self._from], self._items[self._to]
        self._refresh()
