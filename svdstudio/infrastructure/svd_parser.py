"""SVD XML -> domain parser (infrastructure, lxml allowed here)."""
from __future__ import annotations

from lxml import etree

from svdstudio.domain.model import *


def _t(node, tag, default=""):
    el = node.find(tag)
    return el.text.strip() if el is not None and el.text else default

def _i(node, tag, default=0):
    txt = _t(node, tag, "")
    if not txt: return default
    try: return int(txt, 0)
    except ValueError: return default

def _parse_dim(node) -> DimInfo:
    d = DimInfo()
    dim = node.find("dim")
    if dim is not None and dim.text:
        d.dim = int(dim.text.strip(), 0)
        d.dim_increment = _i(node, "dimIncrement", 0)
        di = _t(node, "dimIndex", "")
        if di: d.dim_index = [x.strip() for x in di.split(",")]
    return d

def _parse_enum_values(node) -> EnumeratedValues:
    ev = EnumeratedValues(name=_t(node, "name"), usage=_t(node, "usage"))
    ev.derived_from = node.get("derivedFrom", "")
    for e in node.findall("enumeratedValue"):
        v = _t(e, "value", "0")
        try: iv = int(v, 0)
        except ValueError: iv = 0
        ev.values.append(EnumValue(name=_t(e, "name"), description=_t(e, "description"), value=iv))
    return ev

def _parse_field(n) -> SvdField:
    f = SvdField(name=_t(n, "name"), description=_t(n, "description"),
                 access=_t(n, "access"), read_action=_t(n, "readAction"),
                 modified_write_values=_t(n, "modifiedWriteValues"),
                 write_constraint=_t(n, "writeConstraint"))
    f.derived_from = n.get("derivedFrom", "")
    f.dim = _parse_dim(n)
    bo = n.find("bitOffset"); bw = n.find("bitWidth")
    lsb = n.find("lsb"); msb = n.find("msb"); br = n.find("bitRange")
    if bo is not None and bw is not None:
        f.bit_offset = int(bo.text.strip(), 0); f.bit_width = int(bw.text.strip(), 0)
        f.lsb = f.bit_offset; f.msb = f.bit_offset + f.bit_width - 1
    elif lsb is not None and msb is not None:
        f.lsb = int(lsb.text.strip(), 0); f.msb = int(msb.text.strip(), 0)
        f.bit_offset = f.lsb; f.bit_width = f.msb - f.lsb + 1
    elif br is not None and br.text:
        import re
        m = re.match(r"\[(\d+):(\d+)\]", br.text.strip())
        if m:
            f.msb = int(m.group(1)); f.lsb = int(m.group(2))
            f.bit_offset = f.lsb; f.bit_width = f.msb - f.lsb + 1
    if n.find("resetValue") is not None: f.reset_value = _i(n, "resetValue")
    for evn in n.findall("enumeratedValues"):
        f.enumerated_values.append(_parse_enum_values(evn))
    return f

def _parse_register(n) -> SvdRegister:
    r = SvdRegister(name=_t(n, "name"), display_name=_t(n, "displayName"),
                    description=_t(n, "description"), access=_t(n, "access"),
                    protection=_t(n, "protection"), read_action=_t(n, "readAction"),
                    modified_write_values=_t(n, "modifiedWriteValues"),
                    write_constraint=_t(n, "writeConstraint"))
    r.address_offset = _i(n, "addressOffset")
    r.size = _i(n, "size", 32)
    r.reset_value = _i(n, "resetValue", 0); r.reset_mask = _i(n, "resetMask", 0xFFFFFFFF)
    r.derived_from = n.get("derivedFrom", "")
    r.alternate_register = _t(n, "alternateRegister")
    r.dim = _parse_dim(n)
    for fn in n.findall("fields/field"):
        r.fields.append(_parse_field(fn))
    for evn in n.findall("enumeratedValues"):
        r.enumerated_values.append(_parse_enum_values(evn))
    return r

def _parse_cluster(n) -> SvdCluster:
    c = SvdCluster(name=_t(n, "name"), description=_t(n, "description"))
    c.address_offset = _i(n, "addressOffset")
    c.derived_from = n.get("derivedFrom", "")
    c.dim = _parse_dim(n)
    for rn in n.findall("register"):
        c.registers.append(_parse_register(rn))
    for cn in n.findall("cluster"):
        c.clusters.append(_parse_cluster(cn))
    return c

def _parse_peripheral(n) -> SvdPeripheral:
    p = SvdPeripheral(name=_t(n, "name"), display_name=_t(n, "displayName"),
                      description=_t(n, "description"), group_name=_t(n, "groupName"),
                      prepend_to_name=_t(n, "prependToName"), append_to_name=_t(n, "appendToName"),
                      header_struct_name=_t(n, "headerStructName"))
    p.base_address = _i(n, "baseAddress")
    p.derived_from = n.get("derivedFrom", "")
    p.dim = _parse_dim(n)
    for ab in n.findall("addressBlock"):
        p.address_blocks.append(AddressBlock(offset=_i(ab, "offset"), size=_i(ab, "size"), usage=_t(ab, "usage", "registers")))
    regs = n.find("registers")
    if regs is not None:
        for rn in regs.findall("register"): p.registers.append(_parse_register(rn))
        for cn in regs.findall("cluster"): p.clusters.append(_parse_cluster(cn))
    return p

def parse_file(path: str) -> SvdDevice:
    tree = etree.parse(path)
    root = tree.getroot()
    dev = SvdDevice(name=_t(root, "name"), version=_t(root, "version"),
                    description=_t(root, "description"), vendor=_t(root, "vendor"),
                    vendor_id=_t(root, "vendorID"), series=_t(root, "series"))
    dev.address_unit_bits = _i(root, "addressUnitBits", 8)
    dev.width = _i(root, "width", 32); dev.size = _i(root, "size", 32)
    dev.access = _t(root, "access"); dev.reset_value = _i(root, "resetValue", 0)
    cpu = root.find("cpu")
    if cpu is not None:
        dev.cpu = CpuInfo(name=_t(cpu, "name"), revision=_t(cpu, "revision"), endian=_t(cpu, "endian"),
                          mpu_present=_t(cpu, "mpuPresent") == "true", fpu_present=_t(cpu, "fpuPresent") == "true",
                          nvic_prio_bits=_i(cpu, "nvicPrioBits"),
                          vendor_systick_config=_t(cpu, "vendorSystickConfig") == "true")
    for pn in root.findall("peripherals/peripheral"):
        dev.peripherals.append(_parse_peripheral(pn))
    dev.meta.source_file = path
    return dev
