"""Pure domain model. NO Qt, NO lxml imports allowed here."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Provenance(str, Enum):
    ORIGINAL = "original"
    MODIFIED = "modified"
    INHERITED = "inherited"
    DERIVED = "derived"
    GENERATED = "generated"
    CONFLICT = "conflict"

@dataclass
class NodeMeta:
    source_file: str = ""
    provenance: Provenance = Provenance.ORIGINAL
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    verified: str = ""
    # line in the source SVD where this element was parsed from; lets the
    # validator point at the exact spot in the vendor file
    line: int = 0
    # attributes explicitly present in the source document. The writer emits
    # an optional element only when it is in this set (source-preserving
    # save); absent != explicit-default (see domain/model.py tri-state note).
    present: set[str] = field(default_factory=set)

@dataclass
class EnumValue:
    name: str = ""
    description: str = ""
    value: int = 0
    is_default: bool = False
    meta: NodeMeta = field(default_factory=NodeMeta)

@dataclass
class EnumeratedValues:
    name: str = ""
    usage: str = ""  # read/write/read-write
    derived_from: str = ""
    header_enum_name: str = ""
    values: list[EnumValue] = field(default_factory=list)

@dataclass
class DimInfo:
    dim: int = 0
    dim_increment: int = 0
    dim_index: list[str] = field(default_factory=list)

@dataclass
class SvdField:
    name: str = ""
    description: str = ""
    bit_offset: int = 0
    bit_width: int = 1
    lsb: int = 0
    msb: int = 0
    access: str = ""
    reset_value: int | None = None
    read_action: str = ""
    modified_write_values: str = ""
    write_constraint: str = ""  # "" | "writeAsRead" | "useEnumeratedValues" | "range"
    write_constraint_min: int | None = None
    write_constraint_max: int | None = None
    enumerated_values: list[EnumeratedValues] = field(default_factory=list)
    derived_from: str = ""
    dim: DimInfo = field(default_factory=DimInfo)
    # which bit-range form the author used; the canonical lsb/width store is
    # derived from this so a present single-bit `msb=0` or a `bitRange [7:4]`
    # survives without being silently rewritten (see roundtrip strategy).
    source_range_form: str = ""  # "" | "bitOffset" | "lsb_msb" | "bitRange"
    meta: NodeMeta = field(default_factory=NodeMeta)

@dataclass
class SvdRegister:
    # `size`/`reset_value`/`reset_mask` are tri-state: None means the element
    # was ABSENT in the source (or not yet authored). Readers that need the
    # effective value use the `*_value` accessors (schema defaults); writers
    # must not emit a value that was not present (principle: never write
    # effective values back into the source model).
    name: str = ""
    display_name: str = ""
    description: str = ""
    address_offset: int = 0
    size: int | None = None
    access: str = ""
    protection: str = ""
    reset_value: int | None = None
    reset_mask: int | None = None
    read_action: str = ""
    modified_write_values: str = ""
    write_constraint: str = ""  # "" | "writeAsRead" | "useEnumeratedValues" | "range"
    write_constraint_min: int | None = None
    write_constraint_max: int | None = None
    alternate_register: str = ""
    derived_from: str = ""
    dim: DimInfo = field(default_factory=DimInfo)
    fields: list[SvdField] = field(default_factory=list)
    enumerated_values: list[EnumeratedValues] = field(default_factory=list)
    meta: NodeMeta = field(default_factory=NodeMeta)

    # -- effective accessors (schema defaults, never persisted) -----------
    SCHED_SIZE = 32
    SCHED_RESET_VALUE = 0x0
    SCHED_RESET_MASK_FULL = 0xFFFFFFFF

    @property
    def size_value(self) -> int:
        return self.size if self.size is not None else self.SCHED_SIZE

    @property
    def reset_value_value(self) -> int:
        return self.reset_value if self.reset_value is not None else self.SCHED_RESET_VALUE

    @property
    def reset_mask_value(self) -> int:
        if self.reset_mask is not None:
            return self.reset_mask
        return (1 << self.size_value) - 1 if self.size_value < 64 else self.SCHED_RESET_MASK_FULL

@dataclass
class SvdCluster:
    name: str = ""
    description: str = ""
    address_offset: int = 0
    alternate_cluster: str = ""
    derived_from: str = ""
    dim: DimInfo = field(default_factory=DimInfo)
    registers: list[SvdRegister] = field(default_factory=list)
    clusters: list[SvdCluster] = field(default_factory=list)
    meta: NodeMeta = field(default_factory=NodeMeta)

@dataclass
class AddressBlock:
    offset: int = 0
    size: int = 0
    usage: str = "registers"

@dataclass
class SvdInterrupt:
    name: str = ""
    description: str = ""
    value: int = 0
    meta: NodeMeta = field(default_factory=NodeMeta)


@dataclass
class SvdPeripheral:
    name: str = ""
    display_name: str = ""
    description: str = ""
    group_name: str = ""
    base_address: int = 0
    prepend_to_name: str = ""
    append_to_name: str = ""
    header_struct_name: str = ""
    derived_from: str = ""
    disable_condition: str = ""
    dim: DimInfo = field(default_factory=DimInfo)
    address_blocks: list[AddressBlock] = field(default_factory=list)
    interrupts: list[SvdInterrupt] = field(default_factory=list)
    registers: list[SvdRegister] = field(default_factory=list)
    clusters: list[SvdCluster] = field(default_factory=list)
    meta: NodeMeta = field(default_factory=NodeMeta)

@dataclass
class CpuInfo:
    name: str = ""
    revision: str = ""
    endian: str = ""
    mpu_present: bool = False
    fpu_present: bool = False
    nvic_prio_bits: int = 0
    vendor_systick_config: bool = False
    meta: NodeMeta = field(default_factory=NodeMeta)

@dataclass
class SvdDevice:
    name: str = ""
    version: str = ""
    description: str = ""
    vendor: str = ""
    vendor_id: str = ""
    series: str = ""
    license_text: str = ""
    cpu: CpuInfo = field(default_factory=CpuInfo)
    address_unit_bits: int = 8
    width: int = 32
    size: int = 32
    access: str = ""
    protection: str = ""
    reset_value: int = 0
    reset_mask: int = 0xFFFFFFFF
    peripherals: list[SvdPeripheral] = field(default_factory=list)
    meta: NodeMeta = field(default_factory=NodeMeta)

def iter_registers(p: SvdPeripheral):
    yield from p.registers
    for c in p.clusters:
        yield from _iter_cluster_regs(c)

def _iter_cluster_regs(c: SvdCluster):
    yield from c.registers
    for sub in c.clusters:
        yield from _iter_cluster_regs(sub)
