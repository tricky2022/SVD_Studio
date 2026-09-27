"""Overlay: vendor device + user overrides -> effective device. Pure, no Qt.

Override keys use dotted paths, e.g. "UART1.CR1.TE.access".
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field


@dataclass
class OverlayResult:
    applied: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    orphaned: list[str] = field(default_factory=list)


def _find(device, parts: list[str]):
    """Return (parent_list_or_obj, attr_or_item). Supports peripheral/register/field + attr."""
    if len(parts) < 1:
        return None, None
    periph = next((p for p in device.peripherals if p.name == parts[0]), None)
    if periph is None:
        return None, None
    if len(parts) == 1:
        return device, periph
    regs = {r.name: r for r in periph.registers}
    for cluster in periph.clusters:
        regs.update({r.name: r for r in cluster.registers})
    reg = regs.get(parts[1])
    if reg is None:
        return None, None
    if len(parts) == 2:
        return periph, reg
    fld = next((f for f in reg.fields if f.name == parts[2]), None)
    if fld is None:
        return None, None
    if len(parts) == 3:
        return reg, fld
    return fld, parts[3]


def apply_overlay(vendor_device, overrides: dict[str, object]) -> tuple[object, OverlayResult]:
    device = copy.deepcopy(vendor_device)
    result = OverlayResult()
    for key, value in overrides.items():
        parts = key.split(".")
        attr = parts[-1]
        # resolve leaf attribute set
        node = None
        if len(parts) >= 4:
            periph = next((p for p in device.peripherals if p.name == parts[0]), None)
            regs = {}
            if periph is not None:
                regs = {r.name: r for r in periph.registers}
                for cluster in periph.clusters:
                    regs.update({r.name: r for r in cluster.registers})
            reg = regs.get(parts[1]) if periph else None
            fld = next((f for f in reg.fields if f.name == parts[2]), None) if reg else None
            node = fld
        elif len(parts) == 3:
            # could be REG.attr or PERIPH.REG.FIELD
            periph = next((p for p in device.peripherals if p.name == parts[0]), None)
            regs = {}
            if periph is not None:
                regs = {r.name: r for r in periph.registers}
                for cluster in periph.clusters:
                    regs.update({r.name: r for r in cluster.registers})
            if parts[1] in regs:
                node = regs[parts[1]]
            elif periph is not None:
                node = periph
                attr = parts[2]
            else:
                node = None
        elif len(parts) == 2:
            node = next((p for p in device.peripherals if p.name == parts[0]), None)
        if node is None or not hasattr(node, attr):
            result.conflicts.append(key)
            continue
        old = getattr(node, attr)
        try:
            new = type(old)(value) if not isinstance(old, str) else str(value)
            if isinstance(old, bool):
                new = str(value).lower() in ("1", "true", "yes")
            elif isinstance(old, int):
                new = int(str(value), 0)
        except (TypeError, ValueError):
            result.conflicts.append(key)
            continue
        setattr(node, attr, new)
        if hasattr(node, "meta"):
            node.meta.provenance = "modified"
        result.applied.append(key)
    return device, result
