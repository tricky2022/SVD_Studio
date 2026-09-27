"""Creation dialogs: peripheral / cluster / register / field / enum. All validated."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
)


def _non_empty(edit: QLineEdit, what: str) -> str:
    name = edit.text().strip()
    if not name:
        raise ValueError(f"{what} 名称不能为空")
    if any(ch.isspace() for ch in name):
        raise ValueError(f"{what} 名称不能含空格")
    return name


def _parse_int(text: str, what: str) -> int:
    try:
        return int(text.strip(), 0)
    except ValueError:
        raise ValueError(f"{what} 必须是数字（支持 0x）") from None


class PeripheralDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建外设 / New Peripheral")
        layout = QFormLayout(self)
        self.name = QLineEdit("UART1")
        self.base = QLineEdit("0x40013800")
        self.desc = QLineEdit("")
        layout.addRow("名称", self.name)
        layout.addRow("基地址", self.base)
        layout.addRow("描述", self.desc)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def parsed(self):
        return _non_empty(self.name, "外设"), _parse_int(self.base.text(), "基地址"), \
            self.desc.text().strip()


class ClusterDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建集群 / New Cluster")
        layout = QFormLayout(self)
        self.name = QLineEdit("CH")
        self.offset = QLineEdit("0x0")
        self.desc = QLineEdit("")
        layout.addRow("名称", self.name)
        layout.addRow("偏移", self.offset)
        layout.addRow("描述", self.desc)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def parsed(self):
        return _non_empty(self.name, "集群"), _parse_int(self.offset.text(), "偏移"), \
            self.desc.text().strip()


class RegisterDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建寄存器 / New Register")
        layout = QFormLayout(self)
        self.name = QLineEdit("CR1")
        self.offset = QLineEdit("0x0")
        self.size = QComboBox()
        self.size.addItems(["8", "16", "32", "64"])
        self.size.setCurrentText("32")
        self.access = QComboBox()
        self.access.addItems(["read-only", "write-only", "read-write", "writeOnce", "read-clear"])
        self.access.setCurrentText("read-write")
        self.reset = QLineEdit("0x0")
        self.desc = QLineEdit("")
        layout.addRow("名称", self.name)
        layout.addRow("偏移", self.offset)
        layout.addRow("位宽", self.size)
        layout.addRow("访问", self.access)
        layout.addRow("复位值", self.reset)
        layout.addRow("描述", self.desc)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def parsed(self):
        return (_non_empty(self.name, "寄存器"), _parse_int(self.offset.text(), "偏移"),
                int(self.size.currentText()), self.access.currentText(),
                _parse_int(self.reset.text(), "复位值"), self.desc.text().strip())


class FieldDialog(QDialog):
    def __init__(self, size: int = 32, parent=None):
        super().__init__(parent)
        self._size = size
        self.setWindowTitle("新建字段 / New Field")
        layout = QFormLayout(self)
        self.name = QLineEdit("EN")
        self.lsb = QLineEdit("0")
        self.width = QLineEdit("1")
        self.access = QComboBox()
        self.access.addItems(["", "read-only", "write-only", "read-write"])
        self.desc = QLineEdit("")
        layout.addRow("名称", self.name)
        layout.addRow("LSB", self.lsb)
        layout.addRow("位宽", self.width)
        layout.addRow("访问", self.access)
        layout.addRow("描述", self.desc)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def parsed(self):
        name = _non_empty(self.name, "字段")
        lsb = _parse_int(self.lsb.text(), "LSB")
        width = _parse_int(self.width.text(), "位宽")
        if lsb < 0 or width < 1 or lsb + width > self._size:
            QMessageBox.warning(self, "范围错误", f"字段必须在 0..{self._size - 1} 范围内")
            raise ValueError("field range")
        return name, lsb, width, self.access.currentText(), self.desc.text().strip()
