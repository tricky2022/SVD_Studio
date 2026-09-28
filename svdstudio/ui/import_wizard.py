"""Table import wizard: file/sheet -> mapping preview -> import. Qt dialog + pure service."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from svdstudio.application import tabular_import as TI


class ImportWizardDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Registers from Table")
        self.resize(860, 560)
        self._rows: list[dict] = []
        self._header: list[str] = []
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.path_label = QLabel("No file selected")
        open_btn = QPushButton("Open CSV / TSV / XLSX…")
        open_btn.clicked.connect(self._open)
        top.addWidget(self.path_label, 1)
        top.addWidget(open_btn)
        layout.addLayout(top)

        opts = QHBoxLayout()
        opts.addWidget(QLabel("Sheet (xlsx):"))
        self.sheet = QComboBox()
        self.sheet.setEditable(True)
        self.sheet.addItem("")
        opts.addWidget(self.sheet, 1)
        opts.addWidget(QLabel("Device:"))
        self.device_edit = QComboBox()
        self.device_edit.setEditable(True)
        self.device_edit.addItem("IMPORTED")
        opts.addWidget(self.device_edit, 1)
        opts.addWidget(QLabel("Preview rows:"))
        self.preview_count = QSpinBox()
        self.preview_count.setRange(5, 200)
        self.preview_count.setValue(30)
        self.preview_count.valueChanged.connect(lambda _v: self._refresh_preview())
        opts.addWidget(self.preview_count)
        layout.addLayout(opts)

        self.summary = QLabel("Select a table file to preview the mapping.")
        layout.addWidget(self.summary)
        self.preview = QTableWidget(0, 0)
        self.preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.preview, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Import")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open table", "", "Tables (*.csv *.tsv *.txt *.xlsx *.xlsm)")
        if not path:
            return
        self.path_label.setText(path)
        try:
            if path.lower().endswith((".xlsx", ".xlsm")):
                sheets = TI.list_excel_sheets(path)
                self.sheet.clear()
                self.sheet.addItems(sheets or [""])
            self._refresh_preview()
        except (OSError, ValueError, RuntimeError) as e:  # keep dialog alive
            self.summary.setText(f"Cannot read file: {type(e).__name__}: {e}")

    def _refresh_preview(self):
        path = self.path_label.text()
        if not path or path == "No file selected":
            return
        try:
            header, rows = TI.preview_table(path, sheet=self.sheet.currentText() or None,
                                            limit=self.preview_count.value())
        except (OSError, ValueError, RuntimeError) as e:
            self.summary.setText(f"Cannot read file: {type(e).__name__}: {e}")
            return
        self._header, self._rows = header, rows
        mapping = TI.suggest_mapping(header)
        self.preview.setColumnCount(len(header))
        self.preview.setRowCount(len(rows))
        self.preview.setHorizontalHeaderLabels(
            [f"{c}\n-> {mapping.get(TI.normalize_header(c), '?')}" for c in header])
        for r, row in enumerate(rows):
            for c, col in enumerate(header):
                self.preview.setItem(r, c, QTableWidgetItem(str(row.get(col, ""))))
        self.summary.setText(f"{len(header)} columns, showing {len(rows)} rows. Headers show auto-mapping.")

    def import_result(self, parent=None):
        """Kept for tests/CLI use: read widget state and import synchronously."""
        request = self.import_request()
        if request is None:
            raise ValueError("no input file selected")
        return TI.import_file(*request)

    def import_request(self) -> tuple | None:
        """Pure snapshot of the import inputs, safe to run off the GUI thread."""
        path = self.path_label.text().strip()
        if not path:
            return None
        device = self.device_edit.currentText().strip() or "IMPORTED"
        sheet = self.sheet.currentText() or ""
        return (path, device, "", sheet)
