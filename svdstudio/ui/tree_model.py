"""Domain-backed tree model for the device explorer."""
from __future__ import annotations

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt, Signal

from svdstudio.domain.model import (
    EnumeratedValues,
    SvdCluster,
    SvdDevice,
    SvdPeripheral,
    SvdRegister,
)

# muted flat icon tones: dusty pastels, no neon, consistent across themes
FLAT_TONES = {
    "device": "#8ea3c2",
    "cpu": "#c29585",
    "peripherals": "#8ea3c2",
    "peripheral": "#7ba7d4",
    "cluster": "#c3ac7c",
    "register": "#82b894",
    "field": "#a895c7",
    "enum": "#c7a06a",
    "enum_value": "#9fb3c8",
}


class _Node:
    __slots__ = ("children", "label", "obj", "parent")

    def __init__(self, label, obj=None, parent=None):
        self.label = label
        self.obj = obj
        self.parent = parent
        self.children: list[_Node] = []

    def row(self):
        # computed, not cached: CRUD mutates sibling lists behind the model's
        # back and a cached row would go stale until the next full rebuild
        return self.parent.children.index(self) if self.parent else 0

    def add(self, child):
        self.children.append(child)
        return child


class DeviceTreeModel(QAbstractItemModel):
    # emitted when an in-place tree rename is committed; the window validates
    # (non-empty, sibling-unique) and routes it through the undo stack
    renameCommitted = Signal(object, str)

    def __init__(self, dev: SvdDevice | None = None):
        super().__init__()
        self.root = _Node("root")
        self._dev = None
        if dev:
            self.set_device(dev)

    def set_device(self, dev: SvdDevice):
        self.beginResetModel()
        self.root = _Node("root")
        self._dev = dev
        self._by_object: dict[int, _Node] = {}
        device_node = _Node(dev.name or "Device", dev, self.root)
        self.root.children.append(device_node)
        device_node.children.append(_Node("CPU", dev.cpu, device_node))
        peripherals_node = _Node("Peripherals", None, device_node)
        device_node.children.append(peripherals_node)
        self._register(device_node)
        for peripheral in dev.peripherals:
            self._add_peripheral(peripheral, peripherals_node)
        self.endResetModel()

    def _register(self, node: _Node) -> _Node:
        if node.obj is not None:
            self._by_object[id(node.obj)] = node
        return node

    def node_for(self, obj) -> _Node | None:
        """O(1) node lookup by domain object (id-keyed, rebuilt per device)."""
        if obj is None:
            return None
        return self._by_object.get(id(obj))

    def source_index_for(self, obj) -> QModelIndex:
        """QModelIndex of a domain object without walking the whole tree."""
        node = self.node_for(obj)
        if node is None or node.parent is None:
            return QModelIndex()
        chain, cursor = [], node
        while cursor.parent is not None and cursor.parent is not self.root:
            chain.append(cursor)
            cursor = cursor.parent
        chain.append(cursor)
        index = QModelIndex()
        for step in reversed(chain):
            index = self.index(step.row(), 0, index)
        return index

    def _add_peripheral(self, peripheral: SvdPeripheral, parent: _Node):
        peripheral_node = self._register(_Node(peripheral.name, peripheral, parent))
        parent.children.append(peripheral_node)
        for register in peripheral.registers:
            self._add_register(register, peripheral_node)
        for cluster in peripheral.clusters:
            self._add_cluster(cluster, peripheral_node)

    def _add_cluster(self, cluster: SvdCluster, parent: _Node):
        cluster_node = self._register(_Node(cluster.name, cluster, parent))
        parent.children.append(cluster_node)
        for register in cluster.registers:
            self._add_register(register, cluster_node)
        for nested in cluster.clusters:
            self._add_cluster(nested, cluster_node)

    def _add_register(self, register: SvdRegister, parent: _Node):
        register_node = self._register(_Node(register.name, register, parent))
        parent.children.append(register_node)
        for field in register.fields:
            field_node = self._register(_Node(field.name, field, register_node))
            register_node.children.append(field_node)
            for enum_values in field.enumerated_values:
                self._add_enumerations(enum_values, field_node)
        for enum_values in register.enumerated_values:
            self._add_enumerations(enum_values, register_node)

    def _add_enumerations(self, enum_values: EnumeratedValues, parent: _Node):
        enum_node = self._register(
            _Node(enum_values.name or "Enumerated Values", enum_values, parent))
        parent.children.append(enum_node)
        for value in enum_values.values:
            value_node = self._register(
                _Node(f"{value.name} = {value.value}", value, enum_node))
            enum_node.children.append(value_node)

    def index(self, row, column, parent=None):
        parent = parent if parent is not None else QModelIndex()
        node = self.root if not parent.isValid() else parent.internalPointer()
        if 0 <= row < len(node.children):
            return self.createIndex(row, column, node.children[row])
        return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        node: _Node = index.internalPointer()
        if node.parent is None or node.parent is self.root:
            return QModelIndex()
        return self.createIndex(node.parent.row(), 0, node.parent)

    def rowCount(self, parent=None):
        parent = parent if parent is not None else QModelIndex()
        node = self.root if not parent.isValid() else parent.internalPointer()
        return len(node.children)

    def columnCount(self, parent=None):
        return 1

    def flags(self, index):
        base = super().flags(index)
        if not index.isValid():
            return base
        node: _Node = index.internalPointer()
        if node.obj is not None and hasattr(node.obj, "name"):
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        node: _Node = index.internalPointer()
        if node.obj is None or not hasattr(node.obj, "name"):
            return False
        text = str(value).strip()
        if not text or text == getattr(node.obj, "name", ""):
            return False
        self.renameCommitted.emit(node.obj, text)
        return True

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        node: _Node = index.internalPointer()
        if role == Qt.ItemDataRole.DisplayRole:
            # live name: property renames reflect instantly without a model reset
            return getattr(node.obj, "name", None) or node.label
        if role == Qt.ItemDataRole.DecorationRole:
            from svdstudio.domain.model import SvdField
            from svdstudio.ui.icons import icon
            o = node.obj
            if isinstance(o, SvdDevice):
                return icon("device", FLAT_TONES["device"])
            if isinstance(o, SvdPeripheral):
                return icon("peripheral", FLAT_TONES["peripheral"])
            if isinstance(o, SvdCluster):
                return icon("cluster", FLAT_TONES["cluster"])
            if isinstance(o, SvdRegister):
                return icon("register", FLAT_TONES["register"])
            if isinstance(o, SvdField):
                return icon("field", FLAT_TONES["field"])
            if isinstance(o, EnumeratedValues):
                return icon("enum", FLAT_TONES["enum"])
            if o is None and node.label == "Peripherals":
                return icon("peripherals", FLAT_TONES["peripherals"])
            if node.label == "CPU":
                return icon("cpu", FLAT_TONES["cpu"])
            return icon("enum_value", FLAT_TONES["enum_value"])
        if role == Qt.ItemDataRole.ForegroundRole:
            prov = getattr(getattr(node.obj, "meta", None), "provenance", None)
            from PySide6.QtGui import QColor
            prov_value = getattr(prov, "value", prov)
            if prov_value in ("modified", "conflict"):
                return QColor("#b23b45")
            if prov_value in ("inherited", "derived"):
                return QColor("#8a6d3b")
            return None
        if role == Qt.ItemDataRole.ToolTipRole:
            prov = getattr(getattr(node.obj, "meta", None), "provenance", None)
            prov_value = getattr(prov, "value", prov) or "original"
            kind = type(node.obj).__name__ if node.obj is not None else "group"
            return f"{kind} · {prov_value} · {node.label}"
        return None
