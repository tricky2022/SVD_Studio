"""Validation: L1/L2/L3 returning Issue list. Pure (no Qt)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from svdstudio.domain.model import MAX_CORE_REGISTER_BITS, SvdDevice
from svdstudio.infrastructure import svd_parser


class Severity(str, Enum):
    ERROR = "error"; WARNING = "warning"; INFO = "info"; HINT = "hint"

@dataclass
class Issue:
    rule_id: str; severity: Severity; path: str; message: str
    suggestion: str = ""; can_autofix: bool = False
    line: int = 0; column: int = 0; source: str = ""

    def location(self) -> str:
        """Human-readable location for panels, CLI output and bug reports."""
        where = self.source or self.path
        if self.line:
            where = f"{where}:{self.line}"
            if self.column:
                where = f"{where}:{self.column}"
        return where

    def to_line(self) -> str:
        return f"[{self.severity.value.upper()}] {self.rule_id} {self.location()}: {self.message}"

    def to_dict(self) -> dict:
        return {"severity": self.severity.value, "rule": self.rule_id, "path": self.path,
                "line": self.line, "column": self.column, "source": self.source,
                "message": self.message, "suggestion": self.suggestion,
                "autofix": self.can_autofix}


def check_wellformed(path: str) -> list[Issue]:
    """Structural pre-check used by the CLI and the loader.

    Uses the same hardened parser as the loader (no network, no entity
    expansion, size-capped) so a hostile file cannot hang this call, and
    keeps the line/column of the XML error so the report is actionable.
    """
    try:
        svd_parser.parse_file(path)
        return []
    except (OSError, ValueError) as e:
        line, column = svd_parser.parse_error_position(e)
        return [Issue("XML-001", Severity.ERROR, path, f"XML not well-formed: {e}",
                      line=line, column=column, source=path)]

def _line_of(obj) -> int:
    return int(getattr(getattr(obj, "meta", None), "line", 0) or 0)


def semantic_check(dev: SvdDevice) -> list[Issue]:
    """Document-level rules with the source line of the offending element."""
    issues: list[Issue] = []
    source = getattr(dev.meta, "source_file", "") or ""
    names: set[str] = {p.name for p in dev.peripherals}

    def add(rule_id, severity, path, message, obj=None, suggestion=""):
        issues.append(Issue(rule_id, severity, path, message, suggestion=suggestion,
                            line=_line_of(obj) if obj is not None else 0,
                            source=source))

    if not (dev.name or "").strip():
        add("SVD-DEV-001", Severity.ERROR, "device",
            "Device has no <name> element; every tool (svdconv, CMSIS packs) "
            "rejects this", dev, suggestion="Set the device name in Properties.")
    if not dev.peripherals:
        add("SVD-DEV-002", Severity.WARNING, dev.name or "device",
            "Device declares no peripherals", dev)

    seen_peripherals: set[str] = set()
    for p in dev.peripherals:
        pp = f"{dev.name}.{p.name}"
        if p.name in seen_peripherals:
            add("SVD-DUP-001", Severity.ERROR, pp,
                f"Duplicate peripheral name {p.name}", p,
                suggestion="Rename one of the peripherals.")
        seen_peripherals.add(p.name)
        if p.derived_from and p.derived_from not in names:
            add("SVD-DER-001", Severity.ERROR, pp,
                f"derivedFrom target {p.derived_from!r} does not exist", p,
                suggestion="Fix the derivedFrom attribute or define the base peripheral.")
        if not p.base_address and p.derived_from == "":
            add("SVD-ADDR-002", Severity.WARNING, pp,
                "baseAddress is 0x0 and no derivedFrom is set", p)
        if not p.address_blocks:
            add("SVD-ADDR-003", Severity.INFO, pp,
                "No addressBlock declared; debuggers may not flash this peripheral "
                "correctly", p)
        seen_off: dict[int, str] = {}
        for r in p.registers:
            rp = f"{pp}.{r.name}"
            if not r.name:
                add("SVD-REG-001", Severity.ERROR, rp, "Register has no name", r)
            if not r.description:
                add("SVD-DOC-001", Severity.INFO, rp, "Missing description", r)
            if r.address_offset in seen_off:
                add("SVD-ADDR-001", Severity.ERROR, rp,
                    f"Offset {r.address_offset:#x} collides with {seen_off[r.address_offset]}",
                    r, suggestion="Registers in a peripheral must have unique offsets.")
            seen_off[r.address_offset] = r.name
            if r.size_value not in (8, 16, 32, 64):
                add("SVD-REG-002", Severity.WARNING, rp,
                    f"Unusual register size {r.size_value}; CMSIS expects 8/16/32/64", r)
            if r.derived_from and not (p.derived_from or ""):
                add("SVD-DER-002", Severity.WARNING, rp,
                    f"derivedFrom {r.derived_from!r} used but the base peripheral "
                    "is not resolvable", r)
            used: list[tuple[int, int, str]] = []
            for f in r.fields:
                fp = f"{rp}.{f.name}"
                if not f.name:
                    add("SVD-FIELD-003", Severity.ERROR, fp, "Field has no name", f)
                if f.bit_width < 1:
                    add("SVD-FIELD-004", Severity.ERROR, fp,
                        f"Field width is {f.bit_width}; bitWidth must be >= 1", f)
                if f.bit_offset + f.bit_width > r.size_value:
                    add("SVD-FIELD-001", Severity.ERROR, fp,
                        f"Field [{f.msb}:{f.lsb}] exceeds the {r.size_value}-bit register", f,
                        suggestion="Widen the register or shrink the field.")
                for (start, width, other) in used:
                    if not (f.bit_offset + f.bit_width <= start or start + width <= f.bit_offset):
                        add("SVD-FIELD-002", Severity.ERROR, fp,
                            f"Bits [{f.msb}:{f.lsb}] overlap field {other}", f)
                used.append((f.bit_offset, f.bit_width, f.name))
                for ev in f.enumerated_values:
                    if not ev.name and not ev.derived_from:
                        add("SVD-ENUM-002", Severity.WARNING, fp,
                            "enumeratedValues needs either a name or derivedFrom", f)
                    for v in ev.values:
                        if v.value >= (1 << max(1, f.bit_width)):
                            add("SVD-ENUM-001", Severity.WARNING, f"{fp}.{v.name}",
                                f"Enum value {v.value:#x} does not fit field width "
                                f"{f.bit_width}", f)
    issues.extend(core_register_issues(dev))
    return issues


def core_register_issues(dev: SvdDevice) -> list[Issue]:
    """Validate register IDs and field geometry independently of memory addresses."""
    issues: list[Issue] = []
    source = dev.meta.source_file or ""

    def add(rule: str, path: str, message: str, obj) -> None:
        issues.append(Issue(rule, Severity.ERROR, path, message,
                            line=_line_of(obj), source=source))

    def check_name(name: str, seen: set[str], path: str, obj) -> None:
        if not name.strip():
            add("SVD-CORE-001", path, "Core register group, register and field IDs are required", obj)
        elif name in seen:
            add("SVD-CORE-002", path, f"Duplicate ID {name!r} in this group or register", obj)
        seen.add(name)

    groups: set[str] = set()
    for group in dev.core_register_groups:
        group_path = f"{dev.name}.coreRegisters.{group.name}"
        check_name(group.name, groups, group_path, group)
        registers: set[str] = set()
        for reg in group.registers:
            reg_path = f"{group_path}.{reg.name}"
            check_name(reg.name, registers, reg_path, reg)
            if not 1 <= reg.size <= MAX_CORE_REGISTER_BITS:
                add("SVD-CORE-003", reg_path,
                    f"Register size must be between 1 and {MAX_CORE_REGISTER_BITS} bits", reg)
                continue
            for value in (reg.reset_value, reg.reset_mask):
                if value is not None and not 0 <= value < 1 << reg.size:
                    add("SVD-CORE-004", reg_path, "Reset value or mask exceeds register size", reg)
            fields: set[str] = set()
            for field in reg.fields:
                field_path = f"{reg_path}.{field.name}"
                check_name(field.name, fields, field_path, field)
                if (field.bit_offset < 0 or field.bit_width < 1
                        or field.bit_offset + field.bit_width > reg.size):
                    add("SVD-CORE-005", field_path, "Field exceeds the register bit range", field)
    return issues
