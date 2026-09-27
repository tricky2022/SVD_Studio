"""Domain-backed tree model for the device explorer."""
from __future__ import annotations

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt

from svdstudio.domain.model import (
    EnumeratedValues,
    SvdCluster,
    SvdDevice,
    SvdPeripheral,
    SvdRegister,
)


class _Node:
    def __init__(self, label, obj=None, parent=None):
        self.label = label
        self.obj = obj
        self.parent = parent
        self.children: list[_Node] = []

    def row(self):
        return self.parent.children.index(self) if self.parent else 0


class DeviceTreeModel(QAbstractItemModel):
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
        device_node = _Node(dev.name or "Device", dev, self.root)
        self.root.children.append(device_node)
        device_node.children.append(_Node("CPU", dev.cpu, device_node))
        peripherals_node = _Node("Peripherals", None, device_node)
        device_node.children.append(peripherals_node)
        for peripheral in dev.peripherals:
            self._add_peripheral(peripheral, peripherals_node)
        self.endResetModel()

    def _add_peripheral(self, peripheral: SvdPeripheral, parent: _Node):
        peripheral_node = _Node(peripheral.name, peripheral, parent)
        parent.children.append(peripheral_node)
        for register in peripheral.registers:
            self._add_register(register, peripheral_node)
        for cluster in peripheral.clusters:
            self._add_cluster(cluster, peripheral_node)

    def _add_cluster(self, cluster: SvdCluster, parent: _Node):
        cluster_node = _Node(cluster.name, cluster, parent)
        parent.children.append(cluster_node)
        for register in cluster.registers:
            self._add_register(register, cluster_node)
        for nested in cluster.clusters:
            self._add_cluster(nested, cluster_node)

    def _add_register(self, register: SvdRegister, parent: _Node):
        register_node = _Node(register.name, register, parent)
        parent.children.append(register_node)
        for field in register.fields:
            field_node = _Node(field.name, field, register_node)
            register_node.children.append(field_node)
            for enum_values in field.enumerated_values:
                self._add_enumerations(enum_values, field_node)
        for enum_values in register.enumerated_values:
            self._add_enumerations(enum_values, register_node)

    def _add_enumerations(self, enum_values: EnumeratedValues, parent: _Node):
        enum_node = _Node(enum_values.name or "Enumerated Values", enum_values, parent)
        parent.children.append(enum_node)
        for value in enum_values.values:
            enum_node.children.append(_Node(f"{value.name} = {value.value}", value, enum_node))

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

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        node: _Node = index.internalPointer()
        if role == Qt.ItemDataRole.DisplayRole:
            return node.label
        if role == Qt.ItemDataRole.DecorationRole:
            from svdstudio.domain.model import SvdField
            from svdstudio.ui.icons import icon
            o = node.obj
            if isinstance(o, SvdDevice):
                return icon("device", "#7fb3e8")
            if isinstance(o, SvdPeripheral):
                return icon("peripheral", "#7fb3e8")
            if isinstance(o, SvdCluster):
                return icon("cluster", "#c9a86a")
            if isinstance(o, SvdRegister):
                return icon("register", "#6fd3a7")
            if isinstance(o, SvdField):
                return icon("field", "#b39ddb")
            if isinstance(o, EnumeratedValues):
                return icon("enum", "#e0a458")
            if o is None and node.label == "Peripherals":
                return icon("peripherals", "#7fb3e8")
            if node.label == "CPU":
                return icon("cpu", "#e07a7a")
            return icon("enum_value", "#9fb3c8")
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
