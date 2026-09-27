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

@dataclass
class EnumValue:
    name: str = ""
    description: str = ""
    value: int = 0
    meta: NodeMeta = field(default_factory=NodeMeta)

@dataclass
class EnumeratedValues:
    name: str = ""
    usage: str = ""  # read/write/read-write
    derived_from: str = ""
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
    write_constraint: str = ""
    enumerated_values: list[EnumeratedValues] = field(default_factory=list)
    derived_from: str = ""
    dim: DimInfo = field(default_factory=DimInfo)
    meta: NodeMeta = field(default_factory=NodeMeta)
    def __post_init__(self):
        if self.msb == 0 and self.bit_width:
            self.msb = self.bit_offset + self.bit_width - 1
            self.lsb = self.bit_offset

@dataclass
class SvdRegister:
    name: str = ""
    display_name: str = ""
    description: str = ""
    address_offset: int = 0
    size: int = 32
    access: str = ""
    protection: str = ""
    reset_value: int = 0
    reset_mask: int = 0xFFFFFFFF
    read_action: str = ""
    modified_write_values: str = ""
    write_constraint: str = ""
    alternate_register: str = ""
    derived_from: str = ""
    dim: DimInfo = field(default_factory=DimInfo)
    fields: list[SvdField] = field(default_factory=list)
    enumerated_values: list[EnumeratedValues] = field(default_factory=list)
    meta: NodeMeta = field(default_factory=NodeMeta)

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
    dim: DimInfo = field(default_factory=DimInfo)
    address_blocks: list[AddressBlock] = field(default_factory=list)
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
