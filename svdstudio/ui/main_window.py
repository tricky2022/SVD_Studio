"""Main window controller for the Qt Designer workspace."""
from __future__ import annotations

from pathlib import Path

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
        self.device_tree.doubleClicked.connect(self._rename_at)
        self.model.renameCommitted.connect(self._rename_from_tree)
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
        self._last_issues = []

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
        self.bitview.fieldClicked.connect(self._show_object)
        self.bitview.fieldEdited.connect(self._edit_field_from_legend)
        self.bitview.fieldMoved.connect(self._move_field_geometry)
        self.bitview.canvasMenuRequested.connect(self._bit_canvas_menu)
        self.bitview.legendMenuRequested.connect(self._legend_menu)
        self.bitview.createRequested.connect(self._create_field_at_bit)
        # Eclipse-style problems: double-click jumps, jump icon per row
        self.problems.itemDoubleClicked.connect(lambda _: self._jump_to_problem())
        # lower tabs take less default height; small status icons like Eclipse
        lower = self.findChild(QWidget, "lowerTabs")
        if lower is not None:
            lower.setMaximumHeight(220)
            if hasattr(lower, "setTabIcon"):
                from PySide6.QtCore import QSize
                lower.setTabIcon(0, app_icon("warning"))
                lower.setTabIcon(1, app_icon("info"))
                lower.setIconSize(QSize(12, 12))

    def _configure_layout(self):
        self.workspace_header.hide()
        self.device_tree.setUniformRowHeights(True)
        self.device_tree.setAlternatingRowColors(True)
        # double-click renames (IDE-style); expand via arrows, Enter or menu
        self.device_tree.setExpandsOnDoubleClick(False)
        self.device_tree.setEditTriggers(
            self.device_tree.EditTrigger.DoubleClicked
            | self.device_tree.EditTrigger.EditKeyPressed)
        self.device_tree.setAnimated(True)
        self.device_tree.setIndentation(16)
        self.device_tree.setSelectionMode(self.device_tree.SelectionMode.ExtendedSelection)
        self.device_tree.installEventFilter(self)
        map_view = self.findChild(QWidget, "registerMapView")
        if map_view is not None:
            map_view.installEventFilter(self)
        self.bitview.legend.installEventFilter(self)
        self.props.setAlternatingRowColors(True)
        self.problems.setAlternatingRowColors(True)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 4)
        self.main_splitter.setStretchFactor(2, 2)
        self.main_splitter.setSizes([300, 860, 380])
        # VS-style tree: context menu + keyboard instead of button bar
        self.device_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.device_tree.customContextMenuRequested.connect(self._tree_menu)
        self.device_tree.doubleClicked.connect(self._rename_at)
        self.device_tree.expanded.connect(self._on_tree_expanded)
        self.device_tree.collapsed.connect(self._on_tree_collapsed)
        self._apply_texts()
        self._retranslate_panels()

    def _on_tree_expanded(self, proxy_index):
        self._sync_breadcrumb()
        self._track_expansion(proxy_index, True)

    def _on_tree_collapsed(self, proxy_index):
        self._track_expansion(proxy_index, False)

    def _track_expansion(self, proxy_index, expanded: bool):
        """Remember which objects are expanded so a rebuild can restore them."""
        if not hasattr(self, "_expanded_ids"):
            self._expanded_ids: set[int] = set()
        source = self.proxy.mapToSource(proxy_index)
        node = source.internalPointer() if source.isValid() else None
        if node is None:
            return
        key = id(node.obj if node.obj is not None else node)
        if expanded:
            self._expanded_ids.add(key)
        else:
            self._expanded_ids.discard(key)

    def _apply_texts(self):
        from svdstudio import __version__
        self.setWindowTitle(f"{t('app')} v{__version__}")
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

    def eventFilter(self, watched, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Delete:
            map_view = self.findChild(QWidget, "registerMapView")
            if watched is map_view:
                target = self._map_target()
                view = watched
                rows = sorted({i.row() for i in view.selectedIndexes()}) \
                    if hasattr(view, "selectedIndexes") else []
                if target is not None and rows:
                    self._map_delete_selected(target, rows)
                    return True
            if watched is self.bitview.legend:
                targets = self.bitview.selected_fields()
                if targets:
                    self._delete_fields(targets)
                    return True
        return super().eventFilter(watched, event)

    def _delete_fields(self, targets):
        answer = QMessageBox.question(
            self, t("delete"),
            t("delete_confirm_multi").format(
                count=len(targets),
                names=", ".join(getattr(f, "name", "?") for f in targets[:8])))
        if answer != QMessageBox.StandardButton.Yes:
            return
        reg = self.bitview.reg
        if reg is None:
            return
        self.undo.beginMacro(t("delete"))
        try:
            order = {id(f): i for i, f in enumerate(reg.fields)}
            for field in sorted(targets, key=lambda f: order.get(id(f), -1), reverse=True):
                if field in reg.fields:
                    self.undo.push(C.DeleteCommand(reg.fields, field, "", self._refresh))
        finally:
            self.undo.endMacro()
        self.state.dirty = True

    def _rename_at(self, proxy_index=None):
        """Open the in-place rename editor for a tree node (double-click / F2).

        The current name is pre-selected so the user can retype it outright
        or click again to place the cursor for a partial edit.
        """
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QLineEdit
        index = proxy_index if proxy_index is not None else self.device_tree.currentIndex()
        if not index.isValid():
            return
        source = self.proxy.mapToSource(index)
        node = source.internalPointer() if source.isValid() else None
        if node is None or node.obj is None or not hasattr(node.obj, "name"):
            return
        self.device_tree.edit(index)

        def select_editor_text():
            editor = self.device_tree.viewport().findChild(QLineEdit)
            if editor is not None:
                editor.selectAll()
        QTimer.singleShot(0, select_editor_text)

    def _rename_from_tree(self, obj, new: str):
        """Validate a tree rename and route it through the undo stack."""
        if not new or new == getattr(obj, "name", ""):
            return
        if self._sibling_names(obj) is not None and new in self._sibling_names(obj):
            self.statusBar().showMessage(t("rename_dup"), 4000)
            return
        old = getattr(obj, "name", "")
        self.undo.push(C.SetAttrCommand(obj, "name", new, self._refresh))
        self.state.dirty = True
        self.statusBar().showMessage(t("rename_done").format(old=old, new=new), 4000)

    def _sibling_names(self, obj):
        """Names of objects sharing the same model parent (for rename checks)."""
        from PySide6.QtCore import QModelIndex

        def walk(parent):
            for row in range(self.model.rowCount(parent)):
                idx = self.model.index(row, 0, parent)
                node = idx.internalPointer()
                if node is not None and node.obj is obj and node.parent is not None:
                    return {getattr(sib.obj, "name", "") for sib in node.parent.children
                            if sib.obj is not None and sib.obj is not obj}
                found = walk(idx)
                if found is not None:
                    return found
            return None
        return walk(QModelIndex())

    def _tree_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        index = self.device_tree.indexAt(pos)
        if index.isValid():
            self.device_tree.setCurrentIndex(index)
            self._select(index)
        menu = QMenu(self)
        menu.addAction(t("rename"), self._rename_at)
        if self._selected_node is not None and isinstance(self._selected_node.obj, SvdRegister):
            self.bitview.set_register(self._selected_node.obj)
            menu.addAction(t("field_batch"), self._batch_add_fields)
        menu.addSeparator()
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
            ("new_device", "new", self.new_device, QKeySequence.StandardKey.New),
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
            ("move_up", "move_up", lambda: self.move_selected(-1), None),
            ("move_down", "move_down", lambda: self.move_selected(1), None),
            ("copy", "copy", self.copy_selected, QKeySequence.StandardKey.Copy),
            ("paste", "paste", self.paste_selected, QKeySequence.StandardKey.Paste),
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
        tools_menu.addAction(t("validate_schema"), self.validate_with_schema)
        tools_menu.addAction(t("copy_diagnostics"), self.copy_diagnostics)
        tools_menu.addSeparator()
        tools_menu.addAction(self.actions["import"])
        tools_menu.addAction(self.actions["diff"])
        tools_menu.addAction(self.actions["overlay"])
        tools_menu.addAction(self.actions["batch"])
        help_menu = self.menuBar().addMenu(t("help"))
        help_menu.addAction(t("ai_help"), self.show_ai_help)
        help_menu.addSeparator()
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
        self._retranslate_panels()

    def _retranslate_panels(self):
        """Retranslate every panel so a language switch is truly global."""
        titles = {
            "navigationTitle": "explorer",
            "editorTitle": "register_map",
            "propertiesTitle": "properties",
        }
        for name, key in titles.items():
            label = self.findChild(QLabel, name)
            if label is not None:
                label.setText(t(key))
        lower = self.findChild(QWidget, "lowerTabs")
        if lower is not None and hasattr(lower, "setTabText"):
            lower.setTabText(0, t("problems"))
            lower.setTabText(1, t("output"))
        self.props.refresh()
        self.bitview.retranslate()
        if self._selected_node is not None:
            self._update_register_map(self._selected_node.obj)
            self._update_status(self._selected_node)

    def show_ai_help(self):
        from svdstudio.ui.ai_help import show_ai_help
        show_ai_help(self)

    def show_about(self):
        from svdstudio import __version__
        QMessageBox.about(
            self, t("about"),
            f"SVD Studio v{__version__} — CMSIS-SVD 设备描述工作台\n\n"
            "打开 / 新建 / 编辑 SVD：设备 → 外设 → 寄存器/集群 → 字段 → 枚举值。\n"
            "右侧属性支持 SVD 标准取值的下拉选择；寄存器地图支持批量添加与多选删除；\n"
            "位图双击空白位可新建字段；问题面板双击可跳转定位。\n\n"
            "工具：表格导入（含 Excel 适配）、设备对比 Diff、Overlay 厂商迁移、批量编辑。\n"
            "自动化：帮助 → AI 与自动化接口，含 CLI / Python API / MCP 说明。\n"
            f"SVD Studio v{__version__} — CMSIS-SVD workbench. "
            "See docs/ for architecture and roadmap.")

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
        self._show_object(None)
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
        from svdstudio.ui.load_worker import load_svd_async
        self.statusBar().showMessage(f"Loading {Path(path).name}…")
        load_svd_async(self, path, lambda s, i, e: self._on_open_done(path, s, i, e))

    def _on_open_done(self, path, state, issues, error):
        if error is not None:
            QMessageBox.critical(self, "Open failed", f"{type(error).__name__}: {error}")
            self.statusBar().showMessage("Open failed", 5000)
            return
        if state is None:  # user cancelled
            self.statusBar().showMessage("Open cancelled", 3000)
            return
        self.state = state
        self.model.set_device(self.state.device)
        self._expanded_ids = set()
        self._map_signature_cache = None
        self._clear_detail_panels()
        self._selected_node = None
        self._last_issues = list(issues)
        self._show_issues(issues)
        self.workspace_state.setText(Path(path).stem.upper())
        self.output.appendPlainText(f"Loaded: {path}")
        self.statusBar().showMessage(
            f"Loaded {len(self.state.device.peripherals)} peripheral(s)", 5000)

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
        issues = V.semantic_check(self.state.device)
        self._last_issues = list(issues)
        self._show_issues(issues)

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
        self._issue_objects = list(issues)
        colors = {"ERROR": QColor("#c0392b"), "WARNING": QColor("#b7791f"), "INFO": QColor("#2e6da4")}
        for issue in issues:
            sev = issue.severity.value.upper()
            marker = {"ERROR": "●", "WARNING": "●"}.get(sev, "○")
            location = issue.location() if hasattr(issue, "location") else issue.path
            rule = f"{issue.rule_id}  " if issue.rule_id else ""
            item = QListWidgetItem(f"{marker} {rule}{location}\n     {issue.message}")
            color = colors.get(sev)
            if color is not None:
                item.setForeground(color)
            hint = getattr(issue, "suggestion", "")
            item.setToolTip(f"{issue.message}\n\n建议: {hint}" if hint
                            else "双击定位到对象")
            self.problems.addItem(item)
        errors = sum(1 for i in issues if i.severity.value == "error")
        warns = sum(1 for i in issues if i.severity.value == "warning")
        infos = len(issues) - errors - warns
        self.output.appendPlainText(
            f"Validation: {errors} error(s), {warns} warning(s), {infos} info, "
            f"{len(issues)} total")
        if errors:
            self.statusBar().showMessage(f"Validation failed: {errors} error(s)")
        elif warns:
            self.statusBar().showMessage(f"Validation passed with {warns} warning(s)")
        else:
            self.statusBar().showMessage("Validation passed")

    def _diagnostic_report(self) -> str:
        """Shareable text report: file, tool version and every issue with a line."""
        from svdstudio import __version__
        lines = [
            f"SVD Studio v{__version__} diagnostic report",
            f"file: {self.state.path or '(unsaved)'}",
            f"device: {getattr(self.state.device, 'name', '')}",
            "",
        ]
        for issue in getattr(self, "_issue_objects", []) or self._last_issues:
            lines.append(issue.to_line() if hasattr(issue, "to_line")
                         else f"[{issue.severity.value.upper()}] {issue.path}: {issue.message}")
            hint = getattr(issue, "suggestion", "")
            if hint:
                lines.append(f"    hint: {hint}")
        if len(lines) == 4:
            lines.append("No issues reported.")
        return "\n".join(lines)

    def copy_diagnostics(self):
        from PySide6.QtWidgets import QApplication
        report = self._diagnostic_report()
        QApplication.clipboard().setText(report)
        self.output.appendPlainText(report)
        self.statusBar().showMessage("诊断报告已复制到剪贴板", 4000)

    def validate_with_schema(self):
        """Validate against the official CMSIS-SVD XSD (local copy required)."""
        from PySide6.QtWidgets import QFileDialog

        from svdstudio.validators import xsd as X
        if not self.state.path:
            QMessageBox.information(self, t("validate_schema"),
                                    "请先保存文件，再使用官方 Schema 校验。")
            return
        remembered = self._settings_value("schema_path", "")
        start = remembered or str(Path(self.state.path).parent)
        path, _ = QFileDialog.getOpenFileName(
            self, t("validate_schema"), start, "XML Schema (*.xsd)")
        if not path:
            return
        self._settings_value("schema_path", path, store=True)
        issues = X.validate_xsd(self.state.path, path)
        if not issues:
            self.output.appendPlainText(f"Schema OK: {Path(path).name}")
            QMessageBox.information(self, t("validate_schema"),
                                    f"符合官方 Schema：{Path(path).name}")
            return
        self._show_issues(issues + list(self._last_issues))
        self.problems.setCurrentRow(0)
        QMessageBox.warning(
            self, t("validate_schema"),
            f"Schema 校验发现 {len(issues)} 处不符合，已显示在问题面板。\n"
            "双击问题项可跳转，或使用“复制诊断报告”反馈给厂商。")

    def _settings_value(self, key: str, value=None, store: bool = False):
        from PySide6.QtCore import QSettings
        settings = QSettings("SVD Studio", "SVD Studio")
        if store:
            settings.setValue(key, value)
            return value
        return settings.value(key, value)

    def _select(self, index):
        source_index = self.proxy.mapToSource(index)
        node = source_index.internalPointer() if source_index.isValid() else None
        if node is None:
            return
        if (self._selected_node is not None and self._selected_node.obj is node.obj
                and self._selected_node.obj is not None):
            # same object re-clicked (e.g. second half of a double-click):
            # do NOT rebuild the map/model or the in-place editor never opens
            self._sync_breadcrumb()
            return
        self._selected_node = node
        # keep the path visible without manual scrolling
        parent = index.parent()
        while parent.isValid():
            if not self.device_tree.isExpanded(parent):
                self.device_tree.expand(parent)
            parent = parent.parent()
        self._show_object(node.obj)
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

    @staticmethod
    def _map_signature(target) -> tuple:
        """Cheap fingerprint of the register table; unchanged => no rebuild."""
        return (id(target), target.base_address,
                tuple((r.name, r.address_offset, r.access or "", r.reset_value,
                       r.description or "", len(r.fields))
                      for r in sorted(target.registers, key=lambda x: x.address_offset)))

    def _map_row_for(self, view, obj) -> int:
        """Row of obj in the current map model, or -1."""
        model = view.model()
        if model is None:
            return -1
        for row in range(model.rowCount()):
            item = model.item(row, 1)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) is obj:
                return row
        return -1

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

        signature = self._map_signature(target)
        if signature == getattr(self, "_map_signature_cache", None):
            # same peripheral, same contents: only move the highlighted row.
            # Rebuilding 5 columns x N rows of QStandardItems here was the
            # bulk of the "switch register -> lag" feeling.
            if isinstance(obj, SvdRegister):
                row = self._map_row_for(view, obj)
                if row >= 0:
                    was_loading, self._map_loading = self._map_loading, True
                    try:
                        view.selectRow(row)
                        view.scrollTo(view.model().index(row, 0))
                    finally:
                        self._map_loading = was_loading
            return
        self._map_signature_cache = signature

        from PySide6.QtWidgets import QHeaderView as _HV
        self._map_loading = True
        view.setUpdatesEnabled(False)
        try:
            model = QStandardItemModel(0, 5)
            model.setHorizontalHeaderLabels([t("offset"), t("name"), t("access"), t("reset"), t("description")])
            for reg in sorted(target.registers, key=lambda r: r.address_offset):
                abs_addr = target.base_address + reg.address_offset
                cells = [
                    QStandardItem(f"{reg.address_offset:#06x}  ({abs_addr:#010x})"),
                    QStandardItem(reg.name),
                    QStandardItem(reg.access or "—"),
                    QStandardItem(f"{reg.reset_value:#010x}"),
                    QStandardItem(reg.description or ""),
                ]
                for cell in cells:
                    cell.setEditable(True)
                    cell.setData(reg, Qt.ItemDataRole.UserRole)
                cells[0].setToolTip(t("map_tip_offset"))
                cells[1].setToolTip(t("map_tip_name"))
                cells[2].setToolTip(t("map_tip_access"))
                cells[3].setToolTip(t("map_tip_reset"))
                model.appendRow(cells)
            view.setModel(model)
            model.itemChanged.connect(self._on_map_item_changed)
            view.setAlternatingRowColors(True)
            view.setSelectionBehavior(view.SelectionBehavior.SelectRows)
            view.setSelectionMode(view.SelectionMode.ExtendedSelection)
            view.setEditTriggers(view.EditTrigger.DoubleClicked
                                 | view.EditTrigger.EditKeyPressed
                                 | view.EditTrigger.AnyKeyPressed)
            from svdstudio.ui.delegates import AccessDelegate
            if not getattr(view, "_svd_access_delegate", False):
                view.setItemDelegateForColumn(2, AccessDelegate(view))
                view._svd_access_delegate = True
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
                row = self._map_row_for(view, obj)
                if row >= 0:
                    view.selectRow(row)
                    view.scrollTo(model.index(row, 0))
        finally:
            self._map_loading = False
            view.setUpdatesEnabled(True)

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

    def _on_map_item_changed(self, item):
        """Commit an in-place register-map edit through the undo stack."""
        if getattr(self, "_map_loading", False):
            return
        reg = item.data(Qt.ItemDataRole.UserRole)
        if reg is None:
            return
        col = item.column()
        text = item.text().strip()
        target = self._map_target()
        try:
            if col == 0:
                new = int(text.split()[0], 0)
                if new != reg.address_offset:
                    self.undo.push(C.SetAttrCommand(reg, "address_offset", new, self._refresh))
                    self.state.dirty = True
            elif col == 1:
                if not text:
                    raise ValueError(t("map_err_empty_name"))
                if any(r is not reg and r.name == text for r in (target.registers if target else [])):
                    raise ValueError(t("map_err_dup_name"))
                if text != reg.name:
                    self.undo.push(C.SetAttrCommand(reg, "name", text, self._refresh))
                    self.state.dirty = True
            elif col == 2:
                value = "" if text in ("—", "-", "") else text
                if value != (reg.access or ""):
                    self.undo.push(C.SetAttrCommand(reg, "access", value, self._refresh))
                    self.state.dirty = True
                elif item.text() != (reg.access or "—"):
                    self._refresh()  # normalize the "—" display, no undo step
            elif col == 3:
                new = int(text, 0)
                if new != reg.reset_value:
                    self.undo.push(C.SetAttrCommand(reg, "reset_value", new, self._refresh))
                    self.state.dirty = True
            elif col == 4:
                if text != (reg.description or ""):
                    self.undo.push(C.SetAttrCommand(reg, "description", text, self._refresh))
                    self.state.dirty = True
        except ValueError as error:
            # revert the cell; _refresh rebuilds the map from the domain anyway
            self._refresh()
            self.statusBar().showMessage(str(error), 4000)

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
        from svdstudio.domain.svd_defaults import new_register
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
        reg = new_register(name, offset, description=desc, size=size,
                           access=access or "read-write", reset_value=reset)
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
            from svdstudio.domain.svd_defaults import new_register
            self.undo.push(C.append_command(
                peripheral.registers, new_register(name, base + i * stride),
                f"新建寄存器 {name}", self._refresh))
            existing.add(name)
            added += 1
        self.state.dirty = True
        self.output.appendPlainText(f"批量添加寄存器 {added} 个")

    def _map_edit_selected(self, peripheral, rows):
        regs = sorted(peripheral.registers, key=lambda r: r.address_offset)
        targets = [regs[r] for r in rows if 0 <= r < len(regs)]
        if not targets:
            return
        self._select_object(targets[0])
        view = self.findChild(QWidget, "registerMapView")
        if view is not None and hasattr(view, "model"):
            model = view.model()
            for row in range(model.rowCount()):
                item = model.item(row, 1)
                if item is not None and item.data(Qt.ItemDataRole.UserRole) is targets[0]:
                    view.setCurrentIndex(model.index(row, 1))
                    view.edit(model.index(row, 1))
                    break

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
        """Find obj in the tree model and select it (tree<->map<->bitview sync).

        Uses the model's object index, so the cost is O(depth) instead of a
        full recursive walk on every map click.
        """
        source = self.model.source_index_for(obj)
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
        # read widget state on the GUI thread, then run the heavy import
        # (CSV/XLSX parsing + domain build) in the background
        request = dialog.import_request()
        if request is None:
            return
        from svdstudio.application.tabular_import import import_file
        from svdstudio.ui.load_worker import run_async

        run_async(self, lambda: import_file(*request), self._on_import_done,
                  "Importing table…", "Import table")

    def _on_import_done(self, result, error):
        if error is not None:
            QMessageBox.critical(self, "Import failed",
                                 f"{type(error).__name__}: {error}")
            return
        if result is None:  # cancelled
            self.statusBar().showMessage("Import cancelled", 3000)
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
        if result.device.peripherals:
            self.undo.push(CM.InsertCommand(result.device.peripherals,
                                            result.device.peripherals[0],
                                            0, "Import table", self._refresh))
            self.undo.pop()
        self._refresh()
        self.output.appendPlainText(
            f"Imported: {result.peripherals_created} peripheral(s), "
            f"{result.registers_created} register(s), {result.fields_created} field(s)")
        self.statusBar().showMessage(
            f"Import done: {len(result.device.peripherals)} peripheral(s)", 5000)

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
        path, _ = QFileDialog.getOpenFileName(self, "Compare with SVD", "", "SVD (*.svd *.xml)")
        if not path or self.state.device is None:
            return
        from svdstudio.ui.load_worker import load_svd_async
        self.statusBar().showMessage(f"Loading {Path(path).name} for diff…")
        load_svd_async(self, path, lambda s, i, e: self._on_diff_done(path, s, e))

    def _on_diff_done(self, path, state, error):
        if error is not None:
            QMessageBox.critical(self, "Diff failed", f"{type(error).__name__}: {error}")
            return
        if state is None:  # user cancelled
            return
        from svdstudio.domain import diff as DD
        other = state.device
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

    def _show_object(self, obj):
        """Single funnel for the property panel so every selection path stays in sync."""
        self.props.set_object(obj)

    def _edit(self, obj, attr, new):
        old = getattr(obj, attr, "")
        self.undo.push(C.SetAttrCommand(obj, attr, new, self._refresh))
        self.state.dirty = True
        shown_old = f"{old:#x}" if isinstance(old, int) else old
        shown_new = f"{new:#x}" if isinstance(new, int) else new
        self.statusBar().showMessage(f"已更新 {attr}: {shown_old} → {shown_new}", 4000)

    def _edit_field_from_legend(self, field, attr, new):
        self.undo.push(C.SetAttrCommand(field, attr, new, self._refresh))
        self.state.dirty = True

    def _move_field_geometry(self, field, lsb: int, width: int):
        reg = self.bitview.reg
        if reg is None or field not in reg.fields:
            return
        size = reg.size or 32
        if lsb < 0 or width < 1 or lsb + width > size:
            self.statusBar().showMessage(t("field_err_range").format(size=size), 4000)
            self.bitview.set_register(reg)
            return
        for other in reg.fields:
            if other is not field and not (lsb + width <= other.bit_offset
                                           or other.bit_offset + other.bit_width <= lsb):
                self.statusBar().showMessage(
                    t("field_err_overlap").format(name=other.name), 4000)
                self.bitview.set_register(reg)
                return
        self.undo.beginMacro(t("field_move").format(name=field.name))
        try:
            self.undo.push(C.SetAttrCommand(field, "bit_offset", lsb, self._refresh))
            self.undo.push(C.SetAttrCommand(field, "bit_width", width, self._refresh))
            self.undo.push(C.SetAttrCommand(field, "lsb", lsb, self._refresh))
            self.undo.push(C.SetAttrCommand(
                field, "msb", lsb + width - 1, self._refresh))
        finally:
            self.undo.endMacro()
        self.state.dirty = True

    def _bit_canvas_menu(self, bit: int, global_pos):
        from PySide6.QtWidgets import QMenu
        reg = self.bitview.reg
        if reg is None:
            return
        menu = QMenu(self)
        hit = None
        if bit >= 0:
            for field in reg.fields:
                if field.bit_offset <= bit < field.bit_offset + field.bit_width:
                    hit = field
                    break
        if hit is not None:
            self._show_object(hit)
            menu.addAction(t("rename"), self._rename_field_from_menu)
            menu.addAction(t("delete"), lambda: self._delete_fields([hit]))
            menu.addSeparator()
        if bit >= 0 and hit is None:
            menu.addAction(t("field_new_here").format(bit=bit),
                           lambda: self._create_field_at_bit(bit))
        menu.addAction(t("field_batch"), self._batch_add_fields)
        menu.exec(global_pos)

    def _legend_menu(self, global_pos):
        from PySide6.QtWidgets import QMenu
        reg = self.bitview.reg
        if reg is None:
            return
        picked = self.bitview.selected_fields()
        menu = QMenu(self)
        menu.addAction(t("field_batch"), self._batch_add_fields)
        if picked:
            menu.addSeparator()
            menu.addAction(t("field_delete_multi").format(count=len(picked)),
                           lambda: self._delete_fields(picked))
            if len(picked) == 1:
                menu.addAction(t("rename"), self._rename_field_from_menu)
        menu.exec(global_pos)

    def _rename_field_from_menu(self):
        # _bit_canvas_menu already funneled the field through _show_object;
        # mirror it into the tree so the rename editor opens on the right node
        from svdstudio.domain.model import SvdField
        shown = self.props.current_object()
        if isinstance(shown, SvdField):
            self._select_object(shown)
        self.device_tree.edit(self.device_tree.currentIndex())

    def _batch_add_fields(self):
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit
        reg = self.bitview.reg
        if reg is None:
            return
        size = reg.size or 32
        dialog = QDialog(self)
        dialog.setWindowTitle(t("field_batch_title"))
        layout = QFormLayout(dialog)
        prefix, start, width, count = (QLineEdit("F"), QLineEdit("0"),
                                      QLineEdit("1"), QLineEdit("8"))
        layout.addRow(t("field_batch_prefix"), prefix)
        layout.addRow(t("field_batch_start"), start)
        layout.addRow(t("field_batch_width"), width)
        layout.addRow(t("field_batch_count"), count)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            start_v, width_v, count_v = (int(start.text().strip(), 0),
                                        int(width.text().strip(), 0),
                                        int(count.text().strip(), 0))
        except ValueError:
            QMessageBox.warning(self, t("field_batch_title"), t("field_err_numbers"))
            return
        if width_v < 1 or count_v < 1 or start_v < 0 \
                or start_v + count_v * width_v > size:
            QMessageBox.warning(self, t("field_batch_title"),
                                t("field_err_range").format(size=size))
            return
        existing = {f.name for f in reg.fields}
        occupied = [(f.bit_offset, f.bit_offset + f.bit_width) for f in reg.fields]
        plan = []
        for i in range(count_v):
            name = f"{prefix.text().strip() or 'F'}{i}"
            lsb = start_v + i * width_v
            if name in existing:
                continue
            if any(not (lsb + width_v <= a or b <= lsb) for a, b in occupied):
                QMessageBox.warning(self, t("field_batch_title"),
                                    t("field_err_overlap").format(name=name))
                return
            plan.append((name, lsb))
            existing.add(name)
            occupied.append((lsb, lsb + width_v))
        if not plan:
            return
        from svdstudio.domain.svd_defaults import new_field
        self.undo.beginMacro(t("field_batch_title"))
        try:
            for name, lsb in plan:
                self.undo.push(C.append_command(
                    reg.fields, new_field(name, lsb, width_v, parent_access=reg.access),
                    "", self._refresh))
        finally:
            self.undo.endMacro()
        self.state.dirty = True
        self.statusBar().showMessage(t("field_batch_done").format(count=len(plan)), 4000)

    def _refresh(self):
        if not self.state.device or getattr(self, "_refreshing", False):
            # coalesce: a rebuild triggered from inside a rebuild must not
            # recurse (that was the register-switch lag and the undo spam)
            self._refresh_pending = True
            return
        self._refreshing = True
        try:
            self._rebuild_views()
        finally:
            self._refreshing = False
        if getattr(self, "_refresh_pending", False):
            self._refresh_pending = False
            self._refresh()

    def _rebuild_views(self):
        selected_obj = self._selected_node.obj if self._selected_node else None
        # expansion is tracked incrementally by the expanded/collapsed signals,
        # so restoring costs O(expanded) instead of a walk over every node
        expanded_ids = set(getattr(self, "_expanded_ids", ()))
        self.model.set_device(self.state.device)
        self._expanded_ids = set()
        if selected_obj is not None:
            source = self.model.source_index_for(selected_obj)
            if source.isValid():
                self._selected_node = source.internalPointer()
        self._restore_expansion(expanded_ids)
        if self._selected_node is not None:
            proxy_idx = self.proxy.mapFromSource(
                self.model.source_index_for(self._selected_node.obj))
            if proxy_idx.isValid():
                self.device_tree.setCurrentIndex(proxy_idx)
            self._show_object(self._selected_node.obj)
            from svdstudio.domain.model import SvdRegister as _SR
            self.bitview.set_register(
                self._selected_node.obj if isinstance(self._selected_node.obj, _SR) else None)
            self._update_register_map(self._selected_node.obj)
            self._update_status(self._selected_node)

    def _restore_expansion(self, expanded_ids: set[int]):
        """Re-expand only the paths that were open before the rebuild."""
        if not expanded_ids:
            return
        from PySide6.QtCore import QModelIndex

        def walk(parent_index, node):
            for row in range(self.model.rowCount(parent_index)):
                child_index = self.model.index(row, 0, parent_index)
                child = child_index.internalPointer()
                if child is None:
                    continue
                if id(child.obj) in expanded_ids:
                    proxy_index = self.proxy.mapFromSource(child_index)
                    if proxy_index.isValid():
                        self.device_tree.expand(proxy_index)
                        self._expanded_ids.add(id(child.obj))
                        walk(child_index, child)

        walk(QModelIndex(), self.model.root)

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
        from svdstudio.domain.model import SvdCluster, SvdPeripheral, SvdRegister
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
                from svdstudio.domain.svd_defaults import new_register
                item = new_register(name, offset, size=size, access=access or "read-write",
                                    reset_value=reset, description=desc)
                self.undo.push(C.append_command(obj.registers, item,
                                                f"新建寄存器 {name}", self._refresh))
            elif isinstance(obj, SvdCluster):
                dialog = RegisterDialog(self)
                if dialog.exec() != dialog.DialogCode.Accepted:
                    return
                name, offset, size, access, reset, desc = dialog.parsed()
                item = new_register(name, offset, size=size, access=access or "read-write",
                                    reset_value=reset, description=desc)
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

    def _tree_deletables(self):
        """All selected tree nodes that can be deleted, as (items, obj) pairs.

        Ctrl+click / Shift+click multi-selection is supported; children of a
        selected parent are skipped so each object is deleted exactly once.
        """
        from svdstudio.domain.model import SvdCluster, SvdField, SvdPeripheral, SvdRegister
        selected = self.device_tree.selectionModel().selectedRows()
        nodes = []
        for proxy_idx in selected:
            source = self.proxy.mapToSource(proxy_idx)
            node = source.internalPointer() if source.isValid() else None
            if node is not None and node.obj is not None:
                nodes.append(node)
        if self._selected_node is not None and not nodes:
            nodes = [self._selected_node]
        node_ids = {id(n) for n in nodes}
        pairs = []
        for node in nodes:
            ancestor_selected = False
            cursor = node.parent
            while cursor is not None:
                if id(cursor) in node_ids:
                    ancestor_selected = True
                    break
                cursor = cursor.parent
            if ancestor_selected:
                continue
            items = None
            if isinstance(node.obj, SvdPeripheral):
                items = self.state.device.peripherals if self.state.device else None
            elif isinstance(node.obj, SvdCluster) and node.parent is not None:
                parent_obj = node.parent.obj
                if isinstance(parent_obj, (SvdPeripheral, SvdCluster)):
                    items = parent_obj.clusters
            elif isinstance(node.obj, SvdRegister) and node.parent is not None:
                parent_obj = node.parent.obj
                if isinstance(parent_obj, (SvdPeripheral, SvdCluster)):
                    items = parent_obj.registers
            elif isinstance(node.obj, SvdField) and node.parent is not None \
                    and isinstance(node.parent.obj, SvdRegister):
                items = node.parent.obj.fields
            if items is not None and node.obj in items:
                pairs.append((items, node.obj))
        return pairs

    def delete_selected(self):
        # Delete is context-aware: map/legend handle their own rows via eventFilter
        map_view = self.findChild(QWidget, "registerMapView")
        if map_view is not None and map_view.hasFocus() and hasattr(map_view, "selectedIndexes") \
                and map_view.selectedIndexes():
            return
        if self.bitview.legend.hasFocus() and self.bitview.legend.selectedIndexes():
            return
        pairs = self._tree_deletables()
        if not pairs:
            return
        names = [getattr(obj, "name", "?") for _, obj in pairs]
        answer = QMessageBox.question(
            self, t("delete"),
            t("delete_confirm_multi").format(count=len(pairs), names=", ".join(names[:8])))
        if answer != QMessageBox.StandardButton.Yes:
            return
        deleted = {id(obj) for _, obj in pairs}
        self.undo.beginMacro(t("delete"))
        try:
            by_list: dict[int, tuple[list, list]] = {}
            for items, obj in pairs:
                by_list.setdefault(id(items), (items, []))[1].append(obj)
            for items, objs in by_list.values():
                order = {id(o): i for i, o in enumerate(items)}
                for obj in sorted(objs, key=lambda o: order.get(id(o), -1), reverse=True):
                    if obj in items:
                        self.undo.push(C.DeleteCommand(items, obj, "", self._refresh))
        finally:
            self.undo.endMacro()
        self.state.dirty = True
        if self._selected_node is not None and id(self._selected_node.obj) in deleted:
            self._selected_node = None
            self._show_object(None)
            self.bitview.set_register(None)

