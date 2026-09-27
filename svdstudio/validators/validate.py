"""Validation: L1/L2/L3 returning Issue list. Pure (no Qt)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from lxml import etree

from svdstudio.domain.model import SvdDevice


class Severity(str, Enum):
    ERROR = "error"; WARNING = "warning"; INFO = "info"; HINT = "hint"

@dataclass
class Issue:
    rule_id: str; severity: Severity; path: str; message: str
    suggestion: str = ""; can_autofix: bool = False

def check_wellformed(path: str) -> list[Issue]:
    try:
        etree.parse(path); return []
    except (OSError, ValueError, etree.XMLSyntaxError) as e:
        return [Issue("XML-001", Severity.ERROR, path, f"XML not well-formed: {e}")]

def semantic_check(dev: SvdDevice) -> list[Issue]:
    issues: list[Issue] = []
    names: set[str] = set()
    for p in dev.peripherals:
        pp = f"{dev.name}.{p.name}"
        if p.name in names:
            issues.append(Issue("SVD-DUP-001", Severity.WARNING, pp, f"Duplicate peripheral name {p.name}"))
        names.add(p.name)
        if p.derived_from and p.derived_from not in names and p.derived_from not in [x.name for x in dev.peripherals]:
            issues.append(Issue("SVD-DER-001", Severity.WARNING, pp, f"derivedFrom target missing: {p.derived_from}"))
        seen_off: dict[int, str] = {}
        for r in p.registers:
            rp = f"{pp}.{r.name}"
            if not r.description:
                issues.append(Issue("SVD-DOC-001", Severity.INFO, rp, "Missing description"))
            if r.address_offset in seen_off:
                issues.append(Issue("SVD-ADDR-001", Severity.ERROR, rp, f"Offset collision with {seen_off[r.address_offset]}"))
            seen_off[r.address_offset] = r.name
            used: list[tuple[int, int, str]] = []
            for f in r.fields:
                fp = f"{rp}.{f.name}"
                if f.bit_offset + f.bit_width > r.size:
                    issues.append(Issue("SVD-FIELD-001", Severity.ERROR, fp,
                        f"Field exceeds register width ({f.bit_offset}+{f.bit_width} > {r.size})"))
                for (s, w, n) in used:
                    if not (f.bit_offset + f.bit_width <= s or s + w <= f.bit_offset):
                        issues.append(Issue("SVD-FIELD-002", Severity.ERROR, fp, f"Overlaps field {n}"))
                used.append((f.bit_offset, f.bit_width, f.name))
                for ev in f.enumerated_values:
                    for v in ev.values:
                        if v.value >= (1 << f.bit_width):
                            issues.append(Issue("SVD-ENUM-001", Severity.WARNING, f"{fp}.{v.name}",
                                f"Enum value {v.value:#x} exceeds field width {f.bit_width}"))
    return issues
