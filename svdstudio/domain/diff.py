"""Device diff: structural + property-level comparison. Pure, no Qt."""
from __future__ import annotations

from dataclasses import dataclass, field

from svdstudio.domain.model import CPU_PROPERTIES, CpuInfo


@dataclass
class DiffEntry:
    kind: str  # added/removed/changed
    level: str  # peripheral/register/field/enum/property
    path: str
    old: str = ""
    new: str = ""
    detail: str = ""


@dataclass
class DiffReport:
    entries: list[DiffEntry] = field(default_factory=list)

    @property
    def added(self): return [e for e in self.entries if e.kind == "added"]

    @property
    def removed(self): return [e for e in self.entries if e.kind == "removed"]

    @property
    def changed(self): return [e for e in self.entries if e.kind == "changed"]

    def to_text(self) -> str:
        lines = []
        for e in self.entries:
            if e.kind == "changed" and e.level == "property":
                lines.append(f"~ {e.path}: {e.old} -> {e.new}")
            else:
                lines.append(f"{'+' if e.kind == 'added' else '-' if e.kind == 'removed' else '~'} [{e.level}] {e.path} {e.detail}")
        return "\n".join(lines)


def _regmap(periph):
    regs = {r.name: r for r in periph.registers}
    for cluster in periph.clusters:
        regs.update({r.name: r for r in cluster.registers})
    return regs


def _core_items(device):
    for group in device.core_register_groups:
        group_path = f"coreRegisters.{group.name}"
        yield group_path, "core group", group, ("description",)
        for register in group.registers:
            register_path = f"{group_path}.{register.name}"
            yield register_path, "core register", register, (
                "description", "size", "access", "reset_value", "reset_mask")
            for bit_field in register.fields:
                yield f"{register_path}.{bit_field.name}", "core field", bit_field, (
                    "description", "bit_offset", "bit_width", "access")


def _diff_processor(report, a, b):
    defaults = CpuInfo()
    for tag, attr, _ in CPU_PROPERTIES:
        default = getattr(defaults, attr)
        old, new = getattr(a.cpu, attr), getattr(b.cpu, attr)
        if tag not in a.cpu.meta.present and old == default:
            old = None
        if tag not in b.cpu.meta.present and new == default:
            new = None
        if old != new:
            report.entries.append(DiffEntry("changed", "property", f"cpu.{tag}",
                                            str(old), str(new)))

    old_items = {path: (kind, obj, attrs) for path, kind, obj, attrs in _core_items(a)}
    new_items = {path: (kind, obj, attrs) for path, kind, obj, attrs in _core_items(b)}
    for path in sorted(old_items.keys() - new_items.keys()):
        report.entries.append(DiffEntry("removed", old_items[path][0], path))
    for path in sorted(new_items.keys() - old_items.keys()):
        report.entries.append(DiffEntry("added", new_items[path][0], path))
    for path in sorted(old_items.keys() & new_items.keys()):
        _, old, attrs = old_items[path]
        _, new, _ = new_items[path]
        for attr in attrs:
            before, after = getattr(old, attr), getattr(new, attr)
            if before != after:
                report.entries.append(DiffEntry("changed", "property", f"{path}.{attr}",
                                                str(before), str(after)))


def diff_devices(a, b) -> DiffReport:
    """Compare device A (old) vs B (new)."""
    rep = DiffReport()
    _diff_processor(rep, a, b)
    am = {p.name: p for p in a.peripherals}
    bm = {p.name: p for p in b.peripherals}
    for name in sorted(set(am) - set(bm)):
        rep.entries.append(DiffEntry("removed", "peripheral", name))
    for name in sorted(set(bm) - set(am)):
        rep.entries.append(DiffEntry("added", "peripheral", name))
    for name in sorted(set(am) & set(bm)):
        pa, pb = am[name], bm[name]
        for attr in ("base_address", "description", "group_name"):
            va, vb = getattr(pa, attr, ""), getattr(pb, attr, "")
            if va != vb:
                rep.entries.append(DiffEntry("changed", "property", f"{name}.{attr}",
                                             str(va), str(vb)))
        ra, rb = _regmap(pa), _regmap(pb)
        for rn in sorted(set(ra) - set(rb)):
            rep.entries.append(DiffEntry("removed", "register", f"{name}.{rn}"))
        for rn in sorted(set(rb) - set(ra)):
            rep.entries.append(DiffEntry("added", "register", f"{name}.{rn}"))
        for rn in sorted(set(ra) & set(rb)):
            xa, xb = ra[rn], rb[rn]
            for attr in ("address_offset", "size", "access", "reset_value", "reset_mask",
                         "description", "read_action", "modified_write_values"):
                va, vb = getattr(xa, attr, ""), getattr(xb, attr, "")
                if va != vb:
                    rep.entries.append(DiffEntry("changed", "property", f"{name}.{rn}.{attr}",
                                                 str(va), str(vb)))
            fa = {f.name: f for f in xa.fields}
            fb = {f.name: f for f in xb.fields}
            for fn in sorted(set(fa) - set(fb)):
                rep.entries.append(DiffEntry("removed", "field", f"{name}.{rn}.{fn}"))
            for fn in sorted(set(fb) - set(fa)):
                rep.entries.append(DiffEntry("added", "field", f"{name}.{rn}.{fn}"))
            for fn in sorted(set(fa) & set(fb)):
                ya, yb = fa[fn], fb[fn]
                for attr in ("bit_offset", "bit_width", "access", "description"):
                    va, vb = getattr(ya, attr, ""), getattr(yb, attr, "")
                    if va != vb:
                        rep.entries.append(DiffEntry("changed", "property",
                                                     f"{name}.{rn}.{fn}.{attr}", str(va), str(vb)))
    return rep
