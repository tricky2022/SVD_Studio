"""Central icon system based on qtawesome (FontAwesome). Single source of truth."""
from __future__ import annotations

from functools import lru_cache

try:
    import qtawesome as qta
except ImportError:  # pragma: no cover
    qta = None

_ICONS = {
    "device": "fa5s.microchip",
    "cpu": "fa5s.memory",
    "peripherals": "fa5s.boxes",
    "peripheral": "fa5s.puzzle-piece",
    "cluster": "fa5s.object-group",
    "register": "fa5s.registered",
    "register_map": "fa5s.table",
    "field": "fa5s.sliders-h",
    "enum": "fa5s.list-ol",
    "enum_value": "fa5s.tag",
    "open": "fa5s.folder-open",
    "save": "fa5s.save",
    "validate": "fa5s.check-double",
    "add": "fa5s.plus-circle",
    "duplicate": "fa5s.copy",
    "delete": "fa5s.trash-alt",
    "undo": "fa5s.undo",
    "redo": "fa5s.redo",
    "search": "fa5s.search",
    "address": "fa5s.map-marker-alt",
    "warning": "fa5s.exclamation-triangle",
    "error": "fa5s.times-circle",
    "info": "fa5s.info-circle",
    "theme": "fa5s.adjust",
    "import": "fa5s.file-import",
    "diff": "fa5s.not-equal",
    "bit": "fa5s.th",
    "new": "fa5s.plus",
    "copy": "fa5s.clone",
    "paste": "fa5s.paste",
    "move_up": "fa5s.arrow-up",
    "move_down": "fa5s.arrow-down",
}


COLORS = {
    "device": "#8496b3", "cpu": "#bf8b7d", "peripherals": "#8496b3",
    "peripheral": "#7ba7d4", "cluster": "#c3ac7c", "register": "#82b894",
    "register_map": "#82b894", "field": "#a895c7", "enum": "#c7a06a",
    "enum_value": "#9fb3c8", "open": "#7ba7d4", "save": "#82b894",
    "validate": "#82b894", "add": "#82b894", "duplicate": "#a895c7",
    "delete": "#c08a8a", "undo": "#8b9bb0", "redo": "#8b9bb0",
    "search": "#8b9bb0", "address": "#c3ac7c", "warning": "#c9a45c",
    "error": "#c08a8a", "info": "#7ba7d4", "theme": "#a895c7",
    "import": "#7ba7d4", "diff": "#c3ac7c", "bit": "#a895c7",
    "new": "#82b894", "copy": "#8b9bb0", "paste": "#8b9bb0",
    "move_up": "#8b9bb0", "move_down": "#8b9bb0",
}


@lru_cache(maxsize=128)
def icon(name: str, color: str | None = None):
    from PySide6.QtGui import QIcon
    if qta is None:
        return QIcon()
    try:
        return qta.icon(_ICONS.get(name, "fa5s.cube"), color=color or COLORS.get(name, "#4a6fa5"))
    except Exception:  # noqa: BLE001 - qtawesome raises generic Exception for bad names
        return QIcon()


def validate_all() -> list[str]:
    """Return icon names that fail to load (used by tests to prevent console spam)."""
    bad = []
    icon.cache_clear()
    for name in _ICONS:
        if icon(name).isNull():
            bad.append(name)
    return bad
