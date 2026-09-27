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
}


COLORS = {
    "device": "#4a7ab0", "cpu": "#c26a5a", "peripherals": "#4a7ab0",
    "peripheral": "#4a7ab0", "cluster": "#b98a3e", "register": "#3f9e6b",
    "register_map": "#3f9e6b", "field": "#8b6fc0", "enum": "#c07f35",
    "enum_value": "#8fa0b3", "open": "#4a7ab0", "save": "#3f9e6b",
    "validate": "#3f9e6b", "add": "#3f9e6b", "duplicate": "#8b6fc0",
    "delete": "#c0392b", "undo": "#5a7a99", "redo": "#5a7a99",
    "search": "#5a7a99", "address": "#b98a3e", "warning": "#b7791f",
    "error": "#c0392b", "info": "#2e6da4", "theme": "#8b6fc0",
    "import": "#4a7ab0", "diff": "#b98a3e", "bit": "#8b6fc0",
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
