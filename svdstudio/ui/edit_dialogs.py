"""Tree diff + overlay migration + batch edit dialogs."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)


class DiffTreeDialog(QDialog):
    def __init__(self, report, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设备对比 / Device Diff")
        self.resize(720, 520)
        layout = QVBoxLayout(self)
        summary = QLabel(f"共 {len(report.entries)} 项："
                         f"+{len(report.added)}  −{len(report.removed)}  ~{len(report.changed)}")
        layout.addWidget(summary)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["变更", "层级", "路径", "旧值 → 新值"])
        self.tree.setAlternatingRowColors(True)
        layout.addWidget(self.tree)
        colors = {"added": "✓", "removed": "✗", "changed": "~"}
        for entry in report.entries:
            old_new = f"{entry.old} → {entry.new}" if entry.kind == "changed" else entry.detail
            QTreeWidgetItem(self.tree, [f"{colors.get(entry.kind, '?')} {entry.kind}",
                                       entry.level, entry.path, old_new])
        self.tree.resizeColumnToContents(0)
        self.tree.resizeColumnToContents(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class BatchEditDialog(QDialog):
    """Batch modify offset/access/description/rename for registers or fields."""

    def __init__(self, kind: str, count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"批量编辑 / Batch ({kind} × {count})")
        layout = QFormLayout(self)
        self.attr = QComboBox()
        if kind == "register":
            self.attr.addItems(["access", "description", "address_offset"])
        else:
            self.attr.addItems(["access", "description", "bit_offset"])
        self.value = QLineEdit()
        self.value.setPlaceholderText("例如 access=read-write；offset 支持 0x20")
        layout.addRow("属性", self.attr)
        layout.addRow("新值", self.value)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def parsed(self):
        attr = self.attr.currentText()
        text = self.value.text().strip()
        if attr in ("address_offset", "bit_offset"):
            return attr, int(text, 0)
        return attr, text


class OverlayDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Overlay / 厂商更新迁移")
        self.resize(680, 480)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("选择 overlay YAML 文件…")
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.path_edit)
        row.addWidget(browse)
        layout.addLayout(row)
        self.report_view = QPlainTextEdit()
        self.report_view.setReadOnly(True)
        layout.addWidget(self.report_view)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._overrides: dict = {}

    def _browse(self):
        from svdstudio.domain import overlay_file as OF
        path, _ = QFileDialog.getOpenFileName(self, "打开 Overlay YAML", "",
                                              "YAML (*.yaml *.yml)")
        if not path:
            return
        try:
            self._overrides = OF.load_overlay_file(path)
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.critical(self, "读取失败", str(error))
            return
        self.path_edit.setText(path)
        parent = self.parent()
        if parent is not None and getattr(parent, "state", None) is not None \
                and parent.state.device is not None:
            from svdstudio.domain.overlay import apply_overlay
            _, result = apply_overlay(parent.state.device, self._overrides)
            self.report_view.setPlainText(
                f"预览：可应用 {len(result.applied)}，冲突 {len(result.conflicts)}\n"
                + "\n".join(f"✓ {k}" for k in result.applied[:50])
                + ("\n" if result.applied else "")
                + "\n".join(f"✗ {k}" for k in result.conflicts[:50]))

    @property
    def overrides(self):
        return self._overrides
