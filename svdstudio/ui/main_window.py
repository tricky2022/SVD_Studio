"""Main window controller for the Qt Designer workspace."""
from __future__ import annotations

from pathlib import Path

from lxml import etree
from PySide6.QtCore import QFile, QIODevice, QSettings, QSortFilterProxyModel, Qt
from PySide6.QtGui import QAction, QKeySequence, QUndoStack
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QToolBar,
    QTreeView,
    QWidget,
)

from svdstudio.application import commands as C
from svdstudio.application import project as P
from svdstudio.domain.model import SvdDevice, SvdField, SvdPeripheral, SvdRegister
from svdstudio.resources import resource_path
from svdstudio.ui.app_icon import make_app_icon
from svdstudio.ui.bitview import BitView
from svdstudio.ui.i18n import current_language, set_language, t
from svdstudio.ui.icons import icon as app_icon
from svdstudio.ui.properties import PropertyEditor
from svdstudio.ui.theme import apply_theme, current_mode
from svdstudio.ui.tree_model import DeviceTreeModel
from svdstudio.validators import validate as V

UI_FILE = resource_path("resources", "ui", "main_window.ui")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(make_app_icon())
        self.setWindowTitle(t("app"))
        self._load_designer_ui()
        self.state = P.ProjectState()
        self.undo = QUndoStack(self)
        self.model = DeviceTreeModel()
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setRecursiveFilteringEnabled(True)
        self.device_tree.setModel(self.proxy)
        self.device_tree.clicked.connect(self._select)
        self.device_tree.setIconSize(self.device_tree.iconSize() * 0.9)
        self.search.textChanged.connect(self._on_search_text)
        self.search.returnPressed.connect(self._on_search_return)
        self.search.setPlaceholderText("Search peripheral.register.field or 0xaddress — Ctrl+F")
        self._selected_node = None
        self._create_actions()
        self._configure_layout()
        self._settings = QSettings("SVD Studio", "SVD Studio")
        self._restore_workspace()

    def _restore_workspace(self):
        geometry = self._settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        splitter_state = self._settings.value("mainSplitter")
        if splitter_state:
            self.main_splitter.restoreState(splitter_state)
        saved_theme = self._settings.value("theme", "light")
        if saved_theme in ("light", "dark"):
            self.set_theme(saved_theme)
        saved_language = self._settings.value("language", current_language())
        if saved_language in ("zh", "en") and saved_language != current_language():
            self.switch_language(saved_language)

    def closeEvent(self, event):
        if self.state.dirty:
            answer = QMessageBox.question(
                self, "未保存的修改", "当前设备有未保存的修改，是否保存？",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if answer == QMessageBox.StandardButton.Save:
                self.save()
                if self.state.dirty:
                    event.ignore()
                    return
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("mainSplitter", self.main_splitter.saveState())
        self._settings.setValue("theme", current_mode())
        self._settings.setValue("language", current_language())
        event.accept()

    def _load_designer_ui(self):
        loader = QUiLoader(self)
        file = QFile(str(UI_FILE))
        if not file.open(QIODevice.OpenModeFlag.ReadOnly):
            raise RuntimeError(f"Cannot open UI file: {UI_FILE}")
        loaded = loader.load(file, self)
        file.close()
        if loaded is None:
            raise RuntimeError(loader.errorString())
        central_widget = loaded.centralWidget()
        status_bar = loaded.statusBar()
        self.setWindowTitle(loaded.windowTitle())
        self.resize(loaded.size())
        self.setStatusBar(status_bar)
        self.setCentralWidget(central_widget)

        self.device_tree = self.findChild(QTreeView, "deviceTree")
        self.search = self.findChild(QLineEdit, "searchLine")
        self.workspace_header = self.findChild(QWidget, "workspaceHeader")
        self.property_placeholder = self.findChild(QTableWidget, "propertyEditor")
        self.bit_placeholder = self.findChild(QWidget, "bitViewPlaceholder")
        self.bit_layout = self.findChild(QWidget, "bitViewPlaceholder").layout()
        self.problems = self.findChild(QListWidget, "problemsList")
        self.output = self.findChild(QPlainTextEdit, "outputText")
        self.workspace_state = self.findChild(QLabel, "workspaceState")
        self.main_splitter = self.findChild(QSplitter, "mainSplitter")
        if not all((self.device_tree, self.search, self.property_placeholder, self.bit_layout,
                    self.problems, self.output)):
            raise RuntimeError("main_window.ui is missing a required named widget")

        self.props = PropertyEditor()
        property_layout = self.property_placeholder.parentWidget().layout()
        property_layout.replaceWidget(self.property_placeholder, self.props)
        self.property_placeholder.deleteLater()

        self.bitview = BitView()
        self.bit_layout.addWidget(self.bitview)
        # remove redundant inner titles: outer group titles stay in the .ui
        for title_name in ("registerMapTitle", "bitViewTitle"):
            title = self.findChild(QWidget, title_name)
            if title is not None:
                title.hide()
        # slim map header: creation lives in the map/tree context menus
        map_layout = self.findChild(QWidget, "registerMapPlaceholder")
        if map_layout is not None and map_layout.layout() is not None:
            map_layout.layout().setContentsMargins(4, 1, 4, 1)
            map_layout.layout().setSpacing(1)
        self.props.valueEdited.connect(self._edit)
        self.bitview.fieldClicked.connect(self.props.set_object)
        self.bitview.createRequested.connect(self._create_field_at_bit)
        # Eclipse-style problems: double-click jumps, jump icon per row
        self.problems.itemDoubleClicked.connect(lambda _: self._jump_to_problem())
        # lower tabs take less default height
        lower = self.findChild(QWidget, "lowerTabs")
        if lower is not None:
            lower.setMaximumHeight(220)

    def _configure_layout(self):
        self.workspace_header.hide()
        self.device_tree.setUniformRowHeights(True)
        self.device_tree.setAlternatingRowColors(True)
        self.device_tree.setExpandsOnDoubleClick(True)
        self.device_tree.setAnimated(True)
        self.device_tree.setIndentation(16)
        self.props.setAlternatingRowColors(True)
        self.problems.setAlternatingRowColors(True)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 4)
        self.main_splitter.setStretchFactor(2, 2)
        self.main_splitter.setSizes([300, 860, 380])
        # VS-style tree: context menu + keyboard instead of button bar
        self.device_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.device_tree.customContextMenuRequested.connect(self._tree_menu)
        self.device_tree.expanded.connect(lambda _: self._sync_breadcrumb())
        self._apply_texts()

    def _apply_texts(self):
        self.setWindowTitle(t("app"))
        self.search.setPlaceholderText(t("search_ph"))
        self.output.appendPlainText(t("ready"))

    def _reveal_selection(self):
        index = self.device_tree.currentIndex()
        if index.isValid():
            self.device_tree.scrollTo(index, self.device_tree.ScrollHint.PositionAtCenter)

    def _go_to_top(self):
        from PySide6.QtCore import QModelIndex
        top = self.proxy.index(0, 0, QModelIndex())
        if top.isValid():
            self.device_tree.scrollToTop()
            self.device_tree.setCurrentIndex(top)

    def _sync_breadcrumb(self):
        node = self._selected_node
        if node is None:
            return
        parts = []
        cursor = node
        while cursor is not None and cursor.obj is not None:
            parts.append(getattr(cursor.obj, "name", type(cursor.obj).__name__))
            cursor = cursor.parent
        self.statusBar().showMessage("  /  ".join(reversed([p for p in parts if p])))

    def _tree_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        index = self.device_tree.indexAt(pos)
        if index.isValid():
            self.device_tree.setCurrentIndex(index)
            self._select(index)
        menu = QMenu(self)
        menu.addAction(t("add"), self.add_selected_child)
        menu.addAction(t("duplicate"), self.duplicate_selected)
        menu.addAction(t("delete"), self.delete_selected)
        menu.addSeparator()
        menu.addAction(t("expand_all"), self.device_tree.expandAll)
        menu.addAction(t("collapse_all"), self.device_tree.collapseAll)
        menu.addSeparator()
        menu.addAction(t("locate"), self._reveal_selection)
        menu.addAction(t("top"), self._go_to_top)
        menu.exec(self.device_tree.viewport().mapToGlobal(pos))

    def _create_actions(self):
        from PySide6.QtCore import Qt as _Qt
        toolbar = QToolBar("Main", self)
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        from PySide6.QtCore import QSize as _QSize
        toolbar.setIconSize(_QSize(15, 15))
        toolbar.setToolButtonStyle(_Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.layout().setSpacing(0)
        toolbar.layout().setContentsMargins(2, 1, 2, 1)
        toolbar.setStyleSheet(
            "QToolBar{padding:1px 3px} QToolButton{padding:2px 4px;font-size:9pt}")
        self.addToolBar(toolbar)
        actions = (
            ("open", "open", self.open, QKeySequence.StandardKey.Open),
            ("save", "save", self.save, QKeySequence.StandardKey.Save),
            ("new_device", None, self.new_device, QKeySequence.StandardKey.New),
            ("validate", "validate", self.revalidate, QKeySequence(Qt.Key.Key_F5)),
            ("__group_break__", None, None, None),
            ("undo", "undo", self.undo.undo, QKeySequence.StandardKey.Undo),
            ("redo", "redo", self.undo.redo, QKeySequence.StandardKey.Redo),
            ("add", "add", self.add_selected_child, None),
            ("duplicate", "duplicate", self.duplicate_selected, QKeySequence("Ctrl+D")),
            ("delete", "delete", self.delete_selected, QKeySequence(_Qt.Key.Key_Delete)),
            ("import", "import", self.run_import_wizard, None),
            ("enums", "enum", self.edit_enums, None),
            ("diff", "diff", self.run_diff, None),
            ("overlay", "validate", self.run_overlay, None),
            ("batch", "register_map", self.run_batch, None),
            ("move_up", None, lambda: self.move_selected(-1), None),
            ("move_down", None, lambda: self.move_selected(1), None),
            ("copy", None, self.copy_selected, QKeySequence.StandardKey.Copy),
            ("paste", None, self.paste_selected, QKeySequence.StandardKey.Paste),
            ("theme", "theme", self.toggle_theme, None),
        )
        self.actions = {}
        # order defines visual groups: file | undo | create | tools; theme stays in View menu
        order = ("open", "save", "new_device", "|", "undo", "redo", "|", "add",
                 "duplicate", "delete", "copy", "paste", "|", "validate", "import",
                 "enums", "diff", "overlay", "batch")
        by_key = {}
        for key, icon_name, slot, shortcut in actions:
            if key == "__group_break__":
                continue
            by_key[key] = (icon_name, slot, shortcut)
        # keep move/theme actions registered but off the bar
        for key in ("move_up", "move_down", "theme"):
            if key in by_key:
                icon_name, slot, shortcut = by_key[key]
                text = t(key)
                action = QAction(text, self)
                if slot is not None:
                    action.triggered.connect(slot)
                self.addAction(action)
                self.actions[key] = action
        for key in order:
            if key == "|":
                toolbar.addSeparator()
                continue
            if key not in by_key:
                continue
            icon_name, slot, shortcut = by_key[key]
            text = t(key)
            action = QAction(app_icon(icon_name or "device"), text, self) if icon_name else QAction(text, self)
            action.triggered.connect(slot)
            if shortcut:
                action.setShortcut(shortcut)
            action.setToolTip(text)
            toolbar.addAction(action)
            self.addAction(action)
            self.actions[key] = action

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        self.search.setMinimumWidth(280)
        self.search.setMaximumWidth(420)
        toolbar.addWidget(self.search)

        search_action = QAction("Focus Search", self)
        search_action.setShortcut(QKeySequence("Ctrl+F"))
        search_action.triggered.connect(self.search.setFocus)
        self.addAction(search_action)
        self.actions["focus search"] = search_action

        self._rebuild_menus()

    def _rebuild_menus(self):
        file_menu = self.menuBar().addMenu(t("file"))
        file_menu.addAction(self.actions["open"])
        file_menu.addAction(self.actions["save"])
        file_menu.addAction("另存为… / Save As…", self.save_as, QKeySequence.StandardKey.SaveAs)
        file_menu.addAction(self.actions["new_device"])
        file_menu.addSeparator()
        file_menu.addAction(t("exit"), self.close, QKeySequence.StandardKey.Quit)
        edit_menu = self.menuBar().addMenu(t("edit"))
        edit_menu.addAction(self.actions["undo"])
        edit_menu.addAction(self.actions["redo"])
        edit_menu.addSeparator()
        edit_menu.addAction(self.actions["add"])
        edit_menu.addAction(self.actions["duplicate"])
        edit_menu.addAction(self.actions["delete"])
        view_menu = self.menuBar().addMenu(t("view"))
        view_menu.addAction(self.actions["focus search"])
        from PySide6.QtGui import QActionGroup
        theme_menu = view_menu.addMenu(t("theme"))
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        self._theme_actions = {}
        for mode, label in (("light", "浅色 / Light"), ("dark", "深色 / Dark")):
            action = QAction(label, self, checkable=True, checked=current_mode() == mode)
            action.triggered.connect(lambda checked=False, m=mode: self.set_theme(m))
            theme_group.addAction(action)
            theme_menu.addAction(action)
            self._theme_actions[mode] = action
        view_menu.addSeparator()
        lang_menu = view_menu.addMenu("语言 / Language")
        lang_group = QActionGroup(self)
        lang_group.setExclusive(True)
        self._lang_actions = {}
        for lang, label in (("zh", "中文"), ("en", "English")):
            action = QAction(label, self, checkable=True,
                             checked=current_language() == lang)
            action.triggered.connect(lambda checked=False, code=lang: self.switch_language(code))
            lang_group.addAction(action)
            lang_menu.addAction(action)
            self._lang_actions[lang] = action
        tools_menu = self.menuBar().addMenu(t("tools"))
        tools_menu.addAction(self.actions["validate"])
        tools_menu.addAction(self.actions["import"])
        tools_menu.addAction(self.actions["diff"])
        tools_menu.addAction(self.actions["overlay"])
        tools_menu.addAction(self.actions["batch"])
        help_menu = self.menuBar().addMenu(t("help"))
        help_menu.addAction(t("about"), self.show_about)

    def switch_language(self, lang: str):
        set_language(lang)
        for key, action in self.actions.items():
            try:
                action.setText(t(key))
            except RuntimeError:
                pass
        if hasattr(self, "_lang_actions") and lang in self._lang_actions:
            self._lang_actions[lang].setChecked(True)
        self.menuBar().clear()
        self._rebuild_menus()
        self._apply_texts()

    def show_about(self):
        QMessageBox.about(
            self, t("about"),
            "SVD Studio v0.2 — CMSIS-SVD 设备描述工作台\n\n"
            "打开 / 新建 / 编辑 SVD：设备 → 外设 → 寄存器/集群 → 字段 → 枚举值。\n"
            "右侧属性支持 SVD 标准取值的下拉选择；寄存器地图支持批量添加与多选删除；\n"
            "位图双击空白位可新建字段；问题面板双击可跳转定位。\n\n"
            "工具：表格导入（含 Excel 适配）、设备对比 Diff、Overlay 厂商迁移、批量编辑。\n"
            "SVD Studio v0.2 — CMSIS-SVD workbench. See docs/ for architecture and roadmap.")

    def new_device(self):
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout
        from PySide6.QtWidgets import QLineEdit as _LE

        from svdstudio.domain.model import CpuInfo
        dialog = QDialog(self)
        dialog.setWindowTitle(t("new_device"))
        layout = QFormLayout(dialog)
        name_edit, vendor_edit, desc_edit = _LE("NEWDEV"), _LE("Vendor"), _LE("")
        layout.addRow("设备名称 / Name", name_edit)
        layout.addRow("厂商 / Vendor", vendor_edit)
        layout.addRow("描述 / Description", desc_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        device = SvdDevice(name=name_edit.text().strip() or "NEWDEV",
                           vendor=vendor_edit.text().strip(),
                           description=desc_edit.text().strip(),
                           cpu=CpuInfo(name="CM4"))
        self.state.device = device
        self.state.path = ""
        self.state.dirty = True
        self.model.set_device(device)
        self._clear_detail_panels()
        self._selected_node = None
        self.output.appendPlainText(f"已新建设备 / New device: {device.name}")

    def toggle_theme(self):
        self.set_theme("light" if current_mode() == "dark" else "dark")

    def _clear_detail_panels(self):
        """Empty map/bitview/props/problems when the device context changes."""
        self.props.set_object(None)
        self.bitview.set_register(None)
        view = self.findChild(QWidget, "registerMapView")
        if view is not None and hasattr(view, "setModel"):
            from PySide6.QtGui import QStandardItemModel
            view.setModel(QStandardItemModel(0, 0))
        self.problems.clear()

    def set_theme(self, mode: str):
        from PySide6.QtWidgets import QApplication
        apply_theme(QApplication.instance(), mode)
        if hasattr(self, "_theme_actions") and mode in self._theme_actions:
            self._theme_actions[mode].setChecked(True)
        self.props.refresh()
        self.bitview.update()
        self.output.appendPlainText(f"主题 / Theme: {current_mode()}")

    def open(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open SVD", "", "SVD (*.svd *.xml)")
        if not path:
            return
        try:
            self.state, issues = P.open_svd(path)
            self.model.set_device(self.state.device)
            self._clear_detail_panels()
            self._selected_node = None
            self._show_issues(issues)
            self.workspace_state.setText(Path(path).stem.upper())
            self.output.appendPlainText(f"Loaded: {path}")
        except (OSError, ValueError, etree.XMLSyntaxError) as error:
            QMessageBox.critical(self, "Open failed", f"{type(error).__name__}: {error}")

    def save(self):
        if not self.state.device:
            return
        if not self.state.path:
            self.save_as()
            return
        try:
            P.save_svd(self.state)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "保存失败", f"{type(error).__name__}: {error}")
            return
        self.statusBar().showMessage(f"已保存 {self.state.path}")
        self.output.appendPlainText(f"Saved: {self.state.path}")
        self.workspace_state.setText(Path(self.state.path).stem.upper())

    def save_as(self):
        if not self.state.device:
            return
        path, _ = QFileDialog.getSaveFileName(self, "另存 SVD", "", "SVD (*.svd)")
        if not path:
            return
        if not path.lower().endswith(".svd"):
            path += ".svd"
        try:
            P.save_svd(self.state, path)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "保存失败", f"{type(error).__name__}: {error}")
            return
        self.statusBar().showMessage(f"已保存 {self.state.path}")
        self.output.appendPlainText(f"Saved: {self.state.path}")
        self.workspace_state.setText(Path(self.state.path).stem.upper())

    def revalidate(self):
        if not self.state.device:
            return
        self._show_issues(V.semantic_check(self.state.device))

    def _on_search_text(self, text: str):
        from svdstudio.domain import search_utils as SU
        if self.state.device is None:
            self.proxy.setFilterRegularExpression(text)
            return
        try:
            addr = int(text.strip(), 0)
        except (TypeError, ValueError):
            addr = None
        if addr is not None:
            hits = SU.address_lookup(self.state.device, addr)
            if hits:
                paths = {h.path.split(".")[0] for h in hits}
                self.proxy.setFilterRegularExpression("|".join(sorted(paths)))
                self.statusBar().showMessage(f"Address {addr:#x}: " + "; ".join(h.label for h in hits[:4]))
                return
        self.proxy.setFilterRegularExpression(text)

    def _on_search_return(self):
        from svdstudio.domain import search_utils as SU
        if self.state.device is None:
            return
        hits = SU.search(self.state.device, self.search.text(), limit=10)
        if hits:
            self.statusBar().showMessage(" / ".join(h.label for h in hits[:5]))
            self.output.appendPlainText("Search hits:\n" + "\n".join(f"  {h.kind}: {h.label}" for h in hits[:10]))
        else:
            self.statusBar().showMessage("No matches")

    def _create_field_at_bit(self, bit: int):
        from svdstudio.domain.model import SvdRegister
        node = self._selected_node
        reg = None
        if node is not None and isinstance(node.obj, SvdRegister):
            reg = node.obj
        elif self.bitview.reg is not None:
            reg = self.bitview.reg
        if reg is None:
            return
        from svdstudio.ui.create_dialogs import FieldDialog
        dialog = FieldDialog(reg.size, self)
        dialog.lsb.setText(str(bit))
        dialog.width.setText("1")
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            name, lsb, width, access, desc = dialog.parsed()
        except ValueError as error:
            QMessageBox.warning(self, "新建字段", str(error))
            return
        if any(f.name == name for f in reg.fields):
            QMessageBox.warning(self, "新建字段", f"字段 {name} 已存在")
            return
        from svdstudio.domain.svd_defaults import new_field
        field_obj = new_field(name, lsb, width, parent_access=reg.access,
                              access=access, description=desc)
        self.undo.push(C.append_command(reg.fields, field_obj, f"新建字段 {name}", self._refresh))
        self.state.dirty = True

    def _jump_to_problem(self):
        item = self.problems.currentItem()
        if item is None:
            return
        text = item.text()
        # path is embedded as "RULE path: message" — extract dotted path
        import re
        match = re.search(r"([A-Za-z_][\w]*\.[A-Za-z_][\w.]*?)(?::|\s)", text)
        if not match:
            return
        self._select_by_path(match.group(1))

    def _select_by_path(self, path: str) -> bool:
        parts = path.split(".")
        def walk(parent, depth=0):
            for r in range(self.model.rowCount(parent)):
                idx = self.model.index(r, 0, parent)
                node = idx.internalPointer()
                label = getattr(node.obj, "name", node.label) if node else ""
                if label == parts[depth] or (depth == 0 and node.label == parts[depth]):
                    if depth == len(parts) - 1:
                        return idx
                    found = walk(idx, depth + 1)
                    if found is not None and found.isValid():
                        return found
            return None
        from PySide6.QtCore import QModelIndex
        source = walk(QModelIndex())
        if source is not None and source.isValid():
            proxy_idx = self.proxy.mapFromSource(source)
            self.device_tree.setCurrentIndex(proxy_idx)
            self.device_tree.scrollTo(proxy_idx, self.device_tree.ScrollHint.PositionAtCenter)
            self._select(proxy_idx)
            return True
        return False

    def _show_issues(self, issues):
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QListWidgetItem
        self.problems.clear()
        colors = {"ERROR": QColor("#c0392b"), "WARNING": QColor("#b7791f"), "INFO": QColor("#2e6da4")}
        for issue in issues:
            sev = issue.severity.value.upper()
            marker = {"ERROR": "●", "WARNING": "●"}.get(sev, "○")
            item = QListWidgetItem(f"{marker} {issue.rule_id}  {issue.path}: {issue.message}")
            color = colors.get(sev)
            if color is not None:
                item.setForeground(color)
            item.setToolTip("双击定位到对象")
            self.problems.addItem(item)
        errors = sum(1 for i in issues if i.severity.value == "error")
        warns = sum(1 for i in issues if i.severity.value == "warning")
        self.output.appendPlainText(f"Validation: {errors} error(s), {warns} warning(s), {len(issues)} total")
        if errors:
            self.statusBar().showMessage(f"Validation failed: {errors} error(s)")
        elif warns:
            self.statusBar().showMessage(f"Validation passed with {warns} warning(s)")
        else:
            self.statusBar().showMessage("Validation passed")

    def _select(self, index):
        source_index = self.proxy.mapToSource(index)
        node = source_index.internalPointer() if source_index.isValid() else None
        if node is None:
            return
        self._selected_node = node
        # keep the path visible without manual scrolling
        parent = index.parent()
        while parent.isValid():
            if not self.device_tree.isExpanded(parent):
                self.device_tree.expand(parent)
            parent = parent.parent()
        self.props.set_object(node.obj)
        self.bitview.set_register(node.obj if isinstance(node.obj, SvdRegister) else None)
        self._update_register_map(node.obj)
        self._update_status(node)
        self._sync_breadcrumb()

    def _update_status(self, obj):
        from svdstudio.domain.model import SvdField, SvdRegister
        node = self._selected_node
        parts = []
        cursor = node
        while cursor is not None and cursor.obj is not None:
            parts.append(getattr(cursor.obj, "name", ""))
            cursor = cursor.parent
        path = ".".join(reversed([p for p in parts if p]))
        if isinstance(obj, SvdRegister) and self.state.device is not None:
            self.statusBar().showMessage(f"{path}  size={obj.size}  reset={obj.reset_value:#x}")
        elif isinstance(obj, SvdField):
            label = str(obj.lsb) if obj.bit_width == 1 else f"{obj.msb}:{obj.lsb}"
            self.statusBar().showMessage(f"{path}  bits {label}")
        elif path:
            self.statusBar().showMessage(path)

    def _update_register_map(self, obj):
        from PySide6.QtGui import QStandardItem, QStandardItemModel

        from svdstudio.domain.model import SvdPeripheral, SvdRegister
        view = self.findChild(QWidget, "registerMapView")
        if view is None:
            return
        target = None
        if isinstance(obj, SvdPeripheral):
            target = obj
        elif isinstance(obj, SvdRegister) and self._selected_node.parent is not None:
            parent_obj = self._selected_node.parent.obj
            if isinstance(parent_obj, SvdPeripheral):
                target = parent_obj
        if target is None:
            return
        from PySide6.QtWidgets import QHeaderView as _HV
        model = QStandardItemModel(0, 5)
        model.setHorizontalHeaderLabels([t("offset"), t("name"), t("access"), t("reset"), t("description")])
        for reg in sorted(target.registers, key=lambda r: r.address_offset):
            abs_addr = target.base_address + reg.address_offset
            model.appendRow([
                QStandardItem(f"{reg.address_offset:#06x}  ({abs_addr:#010x})"),
                QStandardItem(reg.name),
                QStandardItem(reg.access or "—"),
                QStandardItem(f"{reg.reset_value:#010x}"),
                QStandardItem(reg.description or ""),
            ])
        view.setModel(model)
        view.setAlternatingRowColors(True)
        view.setSelectionBehavior(view.SelectionBehavior.SelectRows)
        view.setSelectionMode(view.SelectionMode.ExtendedSelection)
        view.setEditTriggers(view.EditTrigger.NoEditTriggers)
        header = view.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, _HV.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, _HV.ResizeMode.Interactive)
        header.setSectionResizeMode(2, _HV.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, _HV.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, _HV.ResizeMode.Stretch)
        header.setMinimumSectionSize(70)
        view.setColumnWidth(0, 190)
        view.setColumnWidth(1, 210)
        view.setColumnWidth(2, 120)
        view.setColumnWidth(3, 140)
        view.verticalHeader().setVisible(False)
        # bidirectional link: click a map row -> select register in tree.
        # Connected exactly once per view (guard flag: blind disconnect()
        # emits RuntimeWarning spam on the PyCharm console).
        view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        if not getattr(view, "_svd_wired", False):
            view.clicked.connect(self._on_map_clicked)
            view.customContextMenuRequested.connect(self._on_map_menu)
            view._svd_wired = True
        view.setProperty("svd_target", target.name)
        # highlight the currently selected register row
        if isinstance(obj, SvdRegister):
            for row in range(model.rowCount()):
                if model.item(row, 1) is not None and model.item(row, 1).text() == obj.name:
                    view.selectRow(row)
                    break

    def _on_map_clicked(self, index):
        view = self.findChild(QWidget, "registerMapView")
        target = self._map_target()
        if view is None or target is None or not index.isValid():
            return
        self._select_register_from_map(target, index.row())

    def _on_map_menu(self, pos):
        view = self.findChild(QWidget, "registerMapView")
        target = self._map_target()
        if view is None or target is None:
            return
        self._register_map_menu(target, view.mapToGlobal(pos))

    def _map_target(self):
        from svdstudio.domain.model import SvdPeripheral
        node = self._selected_node
        if node is not None:
            if isinstance(node.obj, SvdPeripheral):
                self._map_peripheral = node.obj
                return node.obj
            cursor = node
            while cursor is not None:
                if isinstance(cursor.obj, SvdPeripheral):
                    self._map_peripheral = cursor.obj
                    return cursor.obj
                cursor = cursor.parent
        return getattr(self, "_map_peripheral", None)

    def _map_add(self):
        target = self._map_target()
        if target is None:
            QMessageBox.information(self, "寄存器地图", "请先在左侧选中一个外设或其寄存器。")
            return
        from svdstudio.ui.create_dialogs import RegisterDialog
        dialog = RegisterDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            name, offset, size, access, reset, desc = dialog.parsed()
        except ValueError as error:
            QMessageBox.warning(self, "新建寄存器", str(error))
            return
        if any(r.name == name for r in target.registers):
            QMessageBox.warning(self, "新建寄存器", f"寄存器 {name} 已存在")
            return
        from svdstudio.domain.svd_defaults import new_register
        reg = new_register(name, offset, description=desc, size=size,
                           access=access or "read-write", reset_value=reset)
        self.undo.push(C.append_command(target.registers, reg, f"新建寄存器 {name}", self._refresh))
        self.state.dirty = True

    def _map_batch_add(self):
        target = self._map_target()
        if target is None:
            QMessageBox.information(self, "寄存器地图", "请先在左侧选中一个外设或其寄存器。")
            return
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit
        dialog = QDialog(self)
        dialog.setWindowTitle("批量添加寄存器")
        layout = QFormLayout(dialog)
        prefix, start, step, count = QLineEdit("REG"), QLineEdit("0x0"), QLineEdit("0x4"), QLineEdit("4")
        layout.addRow("前缀", prefix)
        layout.addRow("起始偏移", start)
        layout.addRow("步进", step)
        layout.addRow("数量", count)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            start_v, step_v, count_v = int(start.text().strip(), 0), int(step.text().strip(), 0), \
                int(count.text().strip(), 0)
        except ValueError:
            QMessageBox.warning(self, "批量添加", "偏移/步进/数量必须是数字")
            return
        added = 0
        for i in range(max(1, min(count_v, 256))):
            name = f"{prefix.text().strip() or 'REG'}{i}"
            if any(r.name == name for r in target.registers):
                continue
            from svdstudio.domain.svd_defaults import new_register as _new_reg
            self.undo.push(C.append_command(
                target.registers, _new_reg(name, start_v + i * step_v),
                f"新建寄存器 {name}", self._refresh))
            added += 1
        self.state.dirty = True
        self.statusBar().showMessage(f"批量添加 {added} 个寄存器")

    def _map_delete_selected(self):
        target = self._map_target()
        view = self.findChild(QWidget, "registerMapView")
        if target is None or view is None or not hasattr(view, "selectionModel"):
            return
        rows = sorted({idx.row() for idx in view.selectionModel().selectedRows()}, reverse=True)
        if not rows:
            QMessageBox.information(self, "寄存器地图", "请先在地图中选中要删除的行（支持多选）。")
            return
        regs = sorted(target.registers, key=lambda r: r.address_offset)
        names = [regs[r].name for r in rows if 0 <= r < len(regs)]
        answer = QMessageBox.question(self, "删除", f"删除 {len(names)} 个寄存器？\n" + ", ".join(names[:8]))
        if answer != QMessageBox.StandardButton.Yes:
            return
        for r in rows:
            if 0 <= r < len(regs):
                self.undo.push(C.DeleteCommand(target.registers, regs[r],
                                               f"删除 {regs[r].name}", self._refresh))
        self.state.dirty = True

    def _select_register_from_map(self, peripheral, row: int):
        regs = sorted(peripheral.registers, key=lambda r: r.address_offset)
        if 0 <= row < len(regs):
            self._select_object(regs[row])

    def _register_map_menu(self, peripheral, global_pos):
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.addAction("新建寄存器…", lambda: self._map_add_register(peripheral))
        menu.addAction("批量添加…", lambda: self._map_batch_add(peripheral))
        view = self.findChild(QWidget, "registerMapView")
        rows = sorted({i.row() for i in view.selectedIndexes()}) if view else []
        if rows:
            menu.addSeparator()
            menu.addAction(f"编辑选中 ({len(rows)} 行)…", lambda: self._map_edit_selected(peripheral, rows))
            menu.addAction(f"删除选中 ({len(rows)} 行)", lambda: self._map_delete_selected(peripheral, rows))
        menu.exec(global_pos)

    def _map_add_register(self, peripheral):
        from svdstudio.domain.model import SvdRegister
        from svdstudio.ui.create_dialogs import RegisterDialog
        dialog = RegisterDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            name, offset, size, access, reset, desc = dialog.parsed()
        except ValueError as error:
            QMessageBox.warning(self, "新建寄存器", str(error))
            return
        if any(r.name == name for r in peripheral.registers):
            QMessageBox.warning(self, "新建寄存器", f"寄存器 {name} 已存在")
            return
        reg = SvdRegister(name=name, description=desc, address_offset=offset, size=size,
                          access=access, reset_value=reset)
        self.undo.push(C.append_command(peripheral.registers, reg, f"新建寄存器 {name}", self._refresh))
        self.state.dirty = True
        self._select_object(reg)

    def _map_batch_add(self, peripheral):
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QSpinBox
        dialog = QDialog(self)
        dialog.setWindowTitle("批量添加寄存器")
        layout = QFormLayout(dialog)
        prefix, start, step, count = QLineEdit("REG"), QLineEdit("0x0"), QLineEdit("0x4"), QSpinBox()
        count.setRange(1, 256)
        count.setValue(4)
        layout.addRow("名称前缀", prefix)
        layout.addRow("起始偏移", start)
        layout.addRow("步进", step)
        layout.addRow("数量", count)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            base = int(start.text().strip(), 0)
            stride = int(step.text().strip(), 0)
        except ValueError:
            QMessageBox.warning(self, "批量添加", "偏移/步进必须是数字")
            return
        existing = {r.name for r in peripheral.registers}
        added = 0
        for i in range(count.value()):
            name = f"{prefix.text().strip() or 'REG'}{i}"
            if name in existing:
                continue
            from svdstudio.domain.model import SvdRegister
            self.undo.push(C.append_command(
                peripheral.registers, SvdRegister(name=name, address_offset=base + i * stride),
                f"新建寄存器 {name}", self._refresh))
            existing.add(name)
            added += 1
        self.state.dirty = True
        self.output.appendPlainText(f"批量添加寄存器 {added} 个")

    def _map_edit_selected(self, peripheral, rows):
        regs = sorted(peripheral.registers, key=lambda r: r.address_offset)
        targets = [regs[r] for r in rows if 0 <= r < len(regs)]
        if targets:
            self._select_object(targets[0])
            self.props.setFocus()

    def _map_delete_selected(self, peripheral, rows):
        regs = sorted(peripheral.registers, key=lambda r: r.address_offset)
        targets = [regs[r] for r in rows if 0 <= r < len(regs)]
        if not targets:
            return
        answer = QMessageBox.question(self, "删除寄存器",
                                      f"删除 {len(targets)} 个寄存器？")
        if answer != QMessageBox.StandardButton.Yes:
            return
        for reg in targets:
            self.undo.push(C.DeleteCommand(peripheral.registers, reg, f"删除 {reg.name}", self._refresh))
        self.state.dirty = True

    def _select_object(self, obj):
        """Find obj in the tree model and select it (tree<->map<->bitview sync)."""
        def walk(parent):
            for r in range(self.model.rowCount(parent)):
                idx = self.model.index(r, 0, parent)
                node = idx.internalPointer()
                if node is not None and node.obj is obj:
                    return idx
                found = walk(idx)
                if found is not None and found.isValid():
                    return found
            return None
        from PySide6.QtCore import QModelIndex
        source = walk(QModelIndex())
        if source is not None and source.isValid():
            proxy_idx = self.proxy.mapFromSource(source)
            self.device_tree.setCurrentIndex(proxy_idx)
            self.device_tree.scrollTo(proxy_idx, self.device_tree.ScrollHint.PositionAtCenter)
            self._select(proxy_idx)

    def run_import_wizard(self):
        from svdstudio.ui.import_wizard import ImportWizardDialog
        dialog = ImportWizardDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            result = dialog.import_result(self)
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.critical(self, "Import failed", f"{type(error).__name__}: {error}")
            return
        if not result.valid:
            self.output.appendPlainText("Import issues:\n" + "\n".join(
                f"  [{i.severity}] row {i.row}: {i.message}" for i in result.issues))
            QMessageBox.warning(self, "Import has errors",
                                "Import produced errors. See Output panel.")
            return
        from svdstudio.application import commands as CM
        self.state.device = result.device
        self.state.path = ""
        self.state.dirty = True
        self.model.set_device(result.device)
        self.undo.push(CM.InsertCommand(result.device.peripherals, result.device.peripherals[0],
                                        0, "Import table", self._refresh))
        self.undo.pop()
        self._refresh()
        self.output.appendPlainText(
            f"Imported: {result.peripherals_created} peripheral(s), "
            f"{result.registers_created} register(s), {result.fields_created} field(s)")

    def edit_enums(self):
        from svdstudio.domain.model import SvdField
        from svdstudio.ui.enum_dialog import EnumEditorDialog
        node = self._selected_node
        if node is None or not isinstance(node.obj, SvdField):
            QMessageBox.information(self, "Enumerations", "Select a field first.")
            return
        field_obj = node.obj
        dialog = EnumEditorDialog(field_obj, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            values = dialog.result_values()
        except ValueError:
            return
        from svdstudio.application import commands as CM
        from svdstudio.domain.model import EnumeratedValues, EnumValue
        old_groups = field_obj.enumerated_values
        group = EnumeratedValues(name=field_obj.name)
        group.values = [EnumValue(name=n, value=v, description=d) for n, v, d in values]
        self.undo.push(CM.SetAttrCommand(field_obj, "enumerated_values", [group], self._refresh))
        self.state.dirty = True
        self.output.appendPlainText(f"Updated enums for {field_obj.name}: {len(values)} value(s)")
        _ = old_groups

    def run_diff(self):
        from svdstudio.domain import diff as DD
        path, _ = QFileDialog.getOpenFileName(self, "Compare with SVD", "", "SVD (*.svd *.xml)")
        if not path or self.state.device is None:
            return
        try:
            from svdstudio.infrastructure import svd_parser
            other = svd_parser.parse_file(path)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Diff failed", f"{type(error).__name__}: {error}")
            return
        report = DD.diff_devices(self.state.device, other)
        self.output.appendPlainText(f"Diff vs {path} ({len(report.entries)} entries):\n"
                                    + (report.to_text() or "(no differences)"))
        self.problems.clear()
        for entry in report.entries[:500]:
            self.problems.addItem(f"[{entry.kind.upper()}] {entry.level} {entry.path}"
                                  + (f": {entry.old} -> {entry.new}" if entry.old or entry.new else ""))
        from svdstudio.ui.edit_dialogs import DiffTreeDialog
        DiffTreeDialog(report, self).exec()

    def run_overlay(self):
        from svdstudio.domain.overlay import apply_overlay
        from svdstudio.ui.edit_dialogs import OverlayDialog
        dialog = OverlayDialog(self)
        dialog.exec()
        if not dialog.overrides:
            return
        effective, result = apply_overlay(self.state.device, dialog.overrides)
        self.state.device = effective
        self.state.dirty = True
        self._refresh()
        self.output.appendPlainText(
            f"Overlay：已应用 {len(result.applied)}，冲突 {len(result.conflicts)}\n"
            + "\n".join(f"  ✓ {k}" for k in result.applied)
            + ("\n" if result.applied else "")
            + "\n".join(f"  ✗ {k}" for k in result.conflicts))

    def _siblings_of_selected(self):
        items = self._selected_collection()
        node = self._selected_node
        if items is None or node is None:
            return None, None, None
        from svdstudio.domain.model import SvdField, SvdPeripheral, SvdRegister
        if isinstance(node.obj, SvdPeripheral):
            return items, "peripheral", list(items)
        if isinstance(node.obj, SvdRegister):
            parent = node.parent.obj if node.parent else None
            regs = getattr(parent, "registers", items)
            return regs, "register", list(regs)
        if isinstance(node.obj, SvdField):
            parent = node.parent.obj if node.parent else None
            flds = getattr(parent, "fields", items)
            return flds, "field", list(flds)
        return None, None, None

    def run_batch(self):
        from svdstudio.application import commands as CM
        from svdstudio.ui.edit_dialogs import BatchEditDialog
        items, kind, _ = self._siblings_of_selected()
        if not items or kind not in ("register", "field"):
            QMessageBox.information(self, "批量编辑", "请先选中一个寄存器或字段，同级批量修改。")
            return
        dialog = BatchEditDialog(kind, len(items), self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            attr, new = dialog.parsed()
        except ValueError:
            QMessageBox.warning(self, "批量编辑", "数值格式无效。")
            return
        self.undo.push(CM.BatchAttrCommand(items, attr, new, self._refresh,
                                           f"批量编辑 {attr} ×{len(items)}"))
        self.state.dirty = True

    def move_selected(self, direction: int):
        from svdstudio.application import commands as CM
        items = self._selected_collection()
        if items is None or self._selected_node is None:
            return
        self.undo.push(CM.MoveCommand(items, self._selected_node.obj, direction, self._refresh))
        self.state.dirty = True

    def copy_selected(self):
        from copy import deepcopy
        if self._selected_node is None or self._selected_node.obj is None:
            return
        self._clipboard = deepcopy(self._selected_node.obj)
        self.statusBar().showMessage(f"已复制 {getattr(self._clipboard, 'name', '')}")

    def paste_selected(self):
        from copy import deepcopy

        from svdstudio.application import commands as CM
        from svdstudio.domain.model import SvdField, SvdPeripheral, SvdRegister
        if getattr(self, "_clipboard", None) is None or self._selected_node is None:
            return
        node = self._selected_node
        item = deepcopy(self._clipboard)
        item.name = f"{item.name}_COPY"
        if isinstance(item, SvdPeripheral) and hasattr(node.obj, "peripherals"):
            self.undo.push(CM.append_command(node.obj.peripherals, item,
                                             f"粘贴 {item.name}", self._refresh))
        elif isinstance(item, SvdRegister) and isinstance(node.obj, SvdPeripheral):
            self.undo.push(CM.append_command(node.obj.registers, item,
                                             f"粘贴 {item.name}", self._refresh))
        elif isinstance(item, SvdField) and isinstance(node.obj, SvdRegister):
            self.undo.push(CM.append_command(node.obj.fields, item,
                                             f"粘贴 {item.name}", self._refresh))
        else:
            QMessageBox.information(self, "粘贴", "类型与选中位置不匹配，无法粘贴。")
            return
        self.state.dirty = True
        self._refresh_register_map(node.obj)
        # dotted-path search: jump when user typed Periph.Reg.Field
        self._update_status(node)

    def _update_status(self, node):
        from svdstudio.domain.model import SvdField
        chain = []
        n = node
        while n is not None and getattr(n, "obj", None) is not None:
            if getattr(n.obj, "name", ""):
                chain.append(n.obj.name)
            n = n.parent
        chain = ".".join(reversed([c for c in chain if c and c not in ("CPU", "Peripherals")]))
        extra = ""
        if isinstance(node.obj, SvdField):
            extra = f"  bit {node.obj.lsb}" if node.obj.bit_width == 1 else f"  bits {node.obj.msb}:{node.obj.lsb}"
        self.statusBar().showMessage(f"{chain}{extra}" if chain else "Ready")

    def _edit(self, obj, attr, new):
        self.undo.push(C.SetAttrCommand(obj, attr, new, self._refresh))
        self.state.dirty = True

    def _refresh(self):
        if not self.state.device:
            return
        # preserve expansion + selection across CRUD so the tree never collapses
        expanded: set[int] = set()
        def collect(parent, prefix=""):
            for r in range(self.model.rowCount(parent)):
                idx = self.model.index(r, 0, parent)
                node = idx.internalPointer()
                key = f"{prefix}/{getattr(node.obj, 'name', node.label) if node else ''}"
                if self.device_tree.isExpanded(self.proxy.mapFromSource(idx)):
                    expanded.add(key)
                collect(idx, key)
        from PySide6.QtCore import QModelIndex
        collect(QModelIndex())
        selected_obj = self._selected_node.obj if self._selected_node else None
        self.model.set_device(self.state.device)
        def restore(parent, prefix=""):
            for r in range(self.model.rowCount(parent)):
                idx = self.model.index(r, 0, parent)
                node = idx.internalPointer()
                key = f"{prefix}/{getattr(node.obj, 'name', node.label) if node else ''}"
                if key in expanded:
                    self.device_tree.expand(self.proxy.mapFromSource(idx))
                if node is not None and node.obj is selected_obj:
                    proxy_idx = self.proxy.mapFromSource(idx)
                    self.device_tree.setCurrentIndex(proxy_idx)
                    self._selected_node = node
                restore(idx, key)
        restore(QModelIndex())
        # re-sync detail panels so map/bitview/props follow the mutation
        if self._selected_node is not None:
            self.props.set_object(self._selected_node.obj)
            from svdstudio.domain.model import SvdRegister as _SR
            self.bitview.set_register(
                self._selected_node.obj if isinstance(self._selected_node.obj, _SR) else None)
            self._update_register_map(self._selected_node.obj)
            self._update_status(self._selected_node)

    def _selected_collection(self):
        node = self._selected_node
        if node is None or node.parent is None:
            return None
        if isinstance(node.obj, SvdPeripheral):
            return self.state.device.peripherals
        if isinstance(node.obj, SvdRegister) and isinstance(node.parent.obj, SvdPeripheral):
            return node.parent.obj.registers
        if isinstance(node.obj, SvdField) and isinstance(node.parent.obj, SvdRegister):
            return node.parent.obj.fields
        return None

    def _ask_name(self, title, default):
        name, accepted = QInputDialog.getText(self, title, "Name:", text=default)
        return name.strip() if accepted and name.strip() else None

    def add_selected_child(self):
        """Context-aware creation: device->peripheral, peripheral->register/cluster,
        cluster->register, register->field, field->enum. All validated + undoable."""
        from svdstudio.domain.model import (
            SvdCluster,
            SvdPeripheral,
            SvdRegister,
        )
        from svdstudio.ui.create_dialogs import (
            FieldDialog,
            PeripheralDialog,
            RegisterDialog,
        )
        if self.state.device is None:
            QMessageBox.information(self, t("add"), "请先新建或打开设备。")
            return
        node = self._selected_node
        obj = node.obj if node is not None else self.state.device
        try:
            if isinstance(obj, SvdDevice) or obj is None:
                dialog = PeripheralDialog(self)
                if dialog.exec() != dialog.DialogCode.Accepted:
                    return
                name, base, desc = dialog.parsed()
                item = SvdPeripheral(name=name, base_address=base, description=desc)
                self.undo.push(C.append_command(self.state.device.peripherals, item,
                                                f"新建外设 {name}", self._refresh))
            elif isinstance(obj, SvdPeripheral):
                dialog = RegisterDialog(self)
                if dialog.exec() != dialog.DialogCode.Accepted:
                    return
                name, offset, size, access, reset, desc = dialog.parsed()
                if any(r.name == name for r in obj.registers):
                    QMessageBox.warning(self, t("add"), f"寄存器 {name} 已存在。")
                    return
                item = SvdRegister(name=name, address_offset=offset, size=size,
                                   access=access, reset_value=reset, description=desc)
                self.undo.push(C.append_command(obj.registers, item,
                                                f"新建寄存器 {name}", self._refresh))
            elif isinstance(obj, SvdCluster):
                dialog = RegisterDialog(self)
                if dialog.exec() != dialog.DialogCode.Accepted:
                    return
                name, offset, size, access, reset, desc = dialog.parsed()
                item = SvdRegister(name=name, address_offset=offset, size=size,
                                   access=access, reset_value=reset, description=desc)
                self.undo.push(C.append_command(obj.registers, item,
                                                f"新建寄存器 {name}", self._refresh))
            elif isinstance(obj, SvdRegister):
                dialog = FieldDialog(obj.size, self)
                if dialog.exec() != dialog.DialogCode.Accepted:
                    return
                name, lsb, width, access, desc = dialog.parsed()
                if any(f.name == name for f in obj.fields):
                    QMessageBox.warning(self, t("add"), f"字段 {name} 已存在。")
                    return
                for other in obj.fields:
                    if not (lsb + width <= other.bit_offset
                            or other.bit_offset + other.bit_width <= lsb):
                        answer = QMessageBox.question(
                            self, t("add"),
                            f"字段 {name} [{lsb + width - 1}:{lsb}] 与 {other.name} 重叠，仍要创建？")
                        if answer != QMessageBox.StandardButton.Yes:
                            return
                        break
                from svdstudio.domain.svd_defaults import new_field
                item = new_field(name, lsb, width, parent_access=obj.access,
                               access=access, description=desc)
                self.undo.push(C.append_command(obj.fields, item,
                                                f"新建字段 {name}", self._refresh))
            else:
                self.edit_enums()
                return
        except ValueError as error:
            QMessageBox.warning(self, t("add"), str(error))
            return
        self.state.dirty = True
        self._refresh()
        self._reveal_selection()

    def add_cluster_to_selected(self):
        from svdstudio.domain.model import SvdCluster, SvdPeripheral
        from svdstudio.ui.create_dialogs import ClusterDialog
        node = self._selected_node
        if node is None or not isinstance(node.obj, SvdPeripheral):
            QMessageBox.information(self, "新建集群", "请先选中一个外设。")
            return
        dialog = ClusterDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            name, offset, desc = dialog.parsed()
        except ValueError as error:
            QMessageBox.warning(self, "新建集群", str(error))
            return
        item = SvdCluster(name=name, address_offset=offset, description=desc)
        self.undo.push(C.append_command(node.obj.clusters, item,
                                        f"新建集群 {name}", self._refresh))
        self.state.dirty = True
        self._refresh()

    def duplicate_selected(self):
        items = self._selected_collection()
        if items is None:
            return
        item = C.clone_item(self._selected_node.obj)
        self.undo.push(C.InsertCommand(items, item, len(items), f"Duplicate {item.name}", self._refresh))
        self.state.dirty = True

    def delete_selected(self):
        items = self._selected_collection()
        if items is None:
            return
        item = self._selected_node.obj
        answer = QMessageBox.question(self, "Delete object", f"Delete {item.name}?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.undo.push(C.DeleteCommand(items, item, f"Delete {item.name}", self._refresh))
        self.state.dirty = True

