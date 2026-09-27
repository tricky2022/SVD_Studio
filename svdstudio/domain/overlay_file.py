"""Overlay YAML file format + migration report. Pure, no Qt."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


@dataclass
class MigrationReport:
    applied: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    vendor_changes: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        lines = [f"已应用 {len(self.applied)} 项 / 冲突 {len(self.conflicts)} 项"]
        for key in self.applied:
            lines.append(f"  ✓ {key}")
        for key in self.conflicts:
            lines.append(f"  ✗ 冲突: {key}")
        for change in self.vendor_changes:
            lines.append(f"  △ 厂商变更: {change}")
        return "\n".join(lines)


def load_overlay_file(path: str) -> dict[str, object]:
    """YAML format: {overrides: {\"UART1.CR1.TE.access\": \"read-write\"}, meta: {...}}."""
    if yaml is None:
        raise RuntimeError("需要 PyYAML：pip install pyyaml")
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if isinstance(data, dict) and "overrides" in data:
        return dict(data["overrides"])
    if isinstance(data, dict):
        return {str(k): v for k, v in data.items()}
    return {}


def save_overlay_file(overrides: dict[str, object], path: str, meta: dict | None = None):
    if yaml is None:
        raise RuntimeError("需要 PyYAML：pip install pyyaml")
    payload = {"meta": meta or {}, "overrides": dict(overrides)}
    Path(path).write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=True),
                          encoding="utf-8")


def migrate_vendor(old_vendor, new_vendor, overrides: dict[str, object]):
    """Re-apply overrides on top of a new vendor file; report applied/conflicts."""
    from svdstudio.domain.overlay import apply_overlay
    effective, result = apply_overlay(new_vendor, overrides)
    report = MigrationReport(applied=list(result.applied), conflicts=list(result.conflicts))
    old_names = {p.name for p in old_vendor.peripherals}
    new_names = {p.name for p in new_vendor.peripherals}
    for removed in sorted(old_names - new_names):
        report.vendor_changes.append(f"删除外设 {removed}")
    for added in sorted(new_names - old_names):
        report.vendor_changes.append(f"新增外设 {added}")
    return effective, report
