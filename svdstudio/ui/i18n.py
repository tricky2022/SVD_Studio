"""Minimal Chinese/English strings. Default zh. SVD content stays as-is."""
from __future__ import annotations

STRINGS = {
    "zh": {
        "app": "SVD Studio",
        "file": "文件(&F)",
        "edit": "编辑(&E)",
        "view": "视图(&V)",
        "tools": "工具(&T)",
        "open": "打开",
        "save": "保存",
        "validate": "校验",
        "undo": "撤销",
        "redo": "重做",
        "add": "新建",
        "duplicate": "复制",
        "delete": "删除",
        "import": "导入表格",
        "enums": "枚举值",
        "diff": "对比",
        "theme": "主题",
        "exit": "退出",
        "focus_search": "聚焦搜索",
        "search_ph": "搜索 外设.寄存器.字段 或 0x地址 — Ctrl+F",
        "explorer": "设备资源管理器",
        "register_map": "寄存器地图",
        "bit_layout": "位布局",
        "properties": "属性",
        "problems": "问题",
        "output": "输出",
        "offset": "偏移",
        "name": "名称",
        "access": "访问",
        "reset": "复位值",
        "description": "描述",
        "ready": "就绪：打开 SVD 文件开始",
        "new_device": "新建设备",
        "collapse_all": "全部折叠",
        "expand_all": "全部展开",
        "locate": "定位选中项",
        "top": "回到顶部",
        "overlay": "Overlay 迁移",
        "batch": "批量编辑",
        "help": "帮助(&H)",
        "about": "关于 SVD Studio",
        "move_up": "上移",
        "move_down": "下移",
        "copy": "复制对象",
        "paste": "粘贴",
    },
    "en": {
        "app": "SVD Studio",
        "file": "&File",
        "edit": "&Edit",
        "view": "&View",
        "tools": "&Tools",
        "open": "Open",
        "save": "Save",
        "validate": "Validate",
        "undo": "Undo",
        "redo": "Redo",
        "add": "Add",
        "duplicate": "Duplicate",
        "delete": "Delete",
        "import": "Import",
        "enums": "Enums",
        "diff": "Diff",
        "theme": "Theme",
        "exit": "Exit",
        "focus_search": "Focus Search",
        "search_ph": "Search peripheral.register.field or 0xaddress — Ctrl+F",
        "explorer": "Device Explorer",
        "register_map": "Register Map",
        "bit_layout": "Bit Layout",
        "properties": "Properties",
        "problems": "Problems",
        "output": "Output",
        "offset": "Offset",
        "name": "Name",
        "access": "Access",
        "reset": "Reset",
        "description": "Description",
        "ready": "Ready. Open an SVD file to begin.",
        "new_device": "New Device",
        "collapse_all": "Collapse All",
        "expand_all": "Expand All",
        "locate": "Reveal Selection",
        "top": "Go to Top",
        "overlay": "Overlay",
        "batch": "Batch Edit",
        "help": "&Help",
        "about": "About SVD Studio",
        "move_up": "Move Up",
        "move_down": "Move Down",
        "copy": "Copy",
        "paste": "Paste",
    },
}

_lang = "zh"


def set_language(lang: str):
    global _lang
    _lang = "en" if lang == "en" else "zh"


def current_language() -> str:
    return _lang


def t(key: str) -> str:
    return STRINGS[_lang].get(key, STRINGS["en"].get(key, key))
